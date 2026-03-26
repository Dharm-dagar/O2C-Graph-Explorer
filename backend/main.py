import os
import sqlite3
import json
import re
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq

DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")
# FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTEND_BUILD = os.path.join(BASE_DIR, "frontend", "dist")

# ── .env loader ───────────────────────────────────────────────────────────────
def _load_dotenv():
    for path in [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]:
        if os.path.exists(path):
            with open(path) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
                        if _k not in os.environ:
                            os.environ[_k] = _v
            break

_load_dotenv()

app = FastAPI(title="Order-to-Cash Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini client
def _make_groq():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return None
    return Groq(api_key=key)



def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Graph Endpoint ───────────────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph():
    conn = get_conn()
    nodes = []
    edges = []
    node_ids = set()

    def add_node(node_id, node_type, label, properties=None):
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append({
                "id": node_id,
                "type": node_type,
                "label": label,
                "properties": properties or {}
            })

    # Sales Orders
    rows = conn.execute("SELECT salesOrder, soldToParty, totalNetAmount, overallDeliveryStatus, transactionCurrency, creationDate FROM sales_order_headers LIMIT 100").fetchall()
    for r in rows:
        add_node(f"SO-{r['salesOrder']}", "SalesOrder", r['salesOrder'], dict(r))

    # Billing Documents
    rows = conn.execute("SELECT billingDocument, soldToParty, totalNetAmount, billingDocumentDate, accountingDocument, transactionCurrency, billingDocumentIsCancelled FROM billing_document_headers LIMIT 163").fetchall()
    for r in rows:
        add_node(f"BD-{r['billingDocument']}", "BillingDocument", r['billingDocument'], dict(r))

    # Outbound Deliveries
    rows = conn.execute("SELECT deliveryDocument, actualGoodsMovementDate, overallGoodsMovementStatus, shippingPoint FROM outbound_delivery_headers LIMIT 100").fetchall()
    for r in rows:
        add_node(f"OD-{r['deliveryDocument']}", "Delivery", r['deliveryDocument'], dict(r))

    # Journal Entries (unique accounting docs)
    rows = conn.execute("""
        SELECT accountingDocument, companyCode, fiscalYear, postingDate, accountingDocumentType,
               referenceDocument, amountInCompanyCodeCurrency, companyCodeCurrency
        FROM journal_entry_items
        GROUP BY accountingDocument LIMIT 100
    """).fetchall()
    for r in rows:
        add_node(f"JE-{r['accountingDocument']}", "JournalEntry", r['accountingDocument'], dict(r))

    # Payments (unique)
    rows = conn.execute("""
        SELECT accountingDocument, clearingDate, amountInCompanyCodeCurrency, companyCodeCurrency, customer
        FROM payments
        GROUP BY accountingDocument LIMIT 50
    """).fetchall()
    for r in rows:
        add_node(f"PAY-{r['accountingDocument']}", "Payment", r['accountingDocument'], dict(r))

    # Customers (business partners)
    rows = conn.execute("""
        SELECT DISTINCT bp.businessPartner, bp.customer, bp.businessPartnerFullName, bp.organizationBpName1, bp.industry
        FROM business_partners bp
        INNER JOIN sales_order_headers soh ON soh.soldToParty = bp.customer
        LIMIT 30
    """).fetchall()
    for r in rows:
        name = r['businessPartnerFullName'] or r['organizationBpName1'] or r['customer']
        add_node(f"CUST-{r['customer']}", "Customer", name, dict(r))

    # Products (top materials used)
    rows = conn.execute("""
        SELECT p.product, pd.productDescription, p.productGroup, p.baseUnit
        FROM products p
        LEFT JOIN product_descriptions pd ON pd.product = p.product AND pd.language = 'EN'
        LIMIT 30
    """).fetchall()
    for r in rows:
        label = r['productDescription'] or r['product']
        add_node(f"PROD-{r['product']}", "Product", label[:30], dict(r))

    # Plants
    rows = conn.execute("SELECT plant, plantName, cityName FROM plants LIMIT 20").fetchall()
    for r in rows:
        label = r['plantName'] or r['plant']
        add_node(f"PLT-{r['plant']}", "Plant", label, dict(r))

    # ─── Edges ─────────────────────────────────────────────────────────────────

    # SalesOrder → Delivery (via outbound_delivery_items.referenceSdDocument = salesOrder)
    rows = conn.execute("""
        SELECT DISTINCT odi.referenceSdDocument, odi.deliveryDocument
        FROM outbound_delivery_items odi
        INNER JOIN sales_order_headers soh ON soh.salesOrder = odi.referenceSdDocument
        LIMIT 200
    """).fetchall()
    for r in rows:
        s, t = f"SO-{r['referenceSdDocument']}", f"OD-{r['deliveryDocument']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "HAS_DELIVERY"})

    # Delivery → BillingDocument (via billing_document_items.referenceSdDocument = deliveryDocument)
    rows = conn.execute("""
        SELECT DISTINCT bdi.referenceSdDocument, bdi.billingDocument
        FROM billing_document_items bdi
        INNER JOIN outbound_delivery_headers odh ON odh.deliveryDocument = bdi.referenceSdDocument
        LIMIT 300
    """).fetchall()
    for r in rows:
        s, t = f"OD-{r['referenceSdDocument']}", f"BD-{r['billingDocument']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "HAS_BILLING"})

    # BillingDocument → JournalEntry (via accountingDocument)
    rows = conn.execute("""
        SELECT bdh.billingDocument, bdh.accountingDocument
        FROM billing_document_headers bdh
        WHERE bdh.accountingDocument IS NOT NULL
        LIMIT 163
    """).fetchall()
    for r in rows:
        s, t = f"BD-{r['billingDocument']}", f"JE-{r['accountingDocument']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "HAS_JOURNAL_ENTRY"})

    # JournalEntry → Payment (via clearingAccountingDocument)
    rows = conn.execute("""
        SELECT DISTINCT jei.accountingDocument, pay.accountingDocument as payDoc
        FROM journal_entry_items jei
        INNER JOIN payments pay ON pay.clearingAccountingDocument = jei.accountingDocument
        LIMIT 100
    """).fetchall()
    for r in rows:
        s, t = f"JE-{r['accountingDocument']}", f"PAY-{r['payDoc']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "CLEARED_BY"})

    # SalesOrder → Customer
    rows = conn.execute("""
        SELECT soh.salesOrder, soh.soldToParty
        FROM sales_order_headers soh
        WHERE soh.soldToParty IS NOT NULL
        LIMIT 100
    """).fetchall()
    for r in rows:
        s, t = f"SO-{r['salesOrder']}", f"CUST-{r['soldToParty']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "SOLD_TO"})

    # SalesOrder → Product
    rows = conn.execute("""
        SELECT DISTINCT soi.salesOrder, soi.material
        FROM sales_order_items soi
        INNER JOIN products p ON p.product = soi.material
        INNER JOIN sales_order_headers soh ON soh.salesOrder = soi.salesOrder
        LIMIT 100
    """).fetchall()
    for r in rows:
        s, t = f"SO-{r['salesOrder']}", f"PROD-{r['material']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "CONTAINS_PRODUCT"})

    # Delivery → Plant
    rows = conn.execute("""
        SELECT DISTINCT odi.deliveryDocument, odi.plant
        FROM outbound_delivery_items odi
        INNER JOIN plants p ON p.plant = odi.plant
        INNER JOIN outbound_delivery_headers odh ON odh.deliveryDocument = odi.deliveryDocument
        LIMIT 100
    """).fetchall()
    for r in rows:
        s, t = f"OD-{r['deliveryDocument']}", f"PLT-{r['plant']}"
        if s in node_ids and t in node_ids:
            edges.append({"source": s, "target": t, "type": "SHIPPED_FROM"})

    conn.close()
    return {"nodes": nodes, "edges": edges}


# ─── Node Detail Endpoint ─────────────────────────────────────────────────────

@app.get("/api/node/{node_type}/{node_id}")
def get_node_detail(node_type: str, node_id: str):
    conn = get_conn()
    result = {}

    if node_type == "SalesOrder":
        header = conn.execute("SELECT * FROM sales_order_headers WHERE salesOrder=?", (node_id,)).fetchone()
        items = conn.execute("SELECT * FROM sales_order_items WHERE salesOrder=?", (node_id,)).fetchall()
        result = {
            "header": dict(header) if header else {},
            "items": [dict(i) for i in items]
        }
    elif node_type == "BillingDocument":
        header = conn.execute("SELECT * FROM billing_document_headers WHERE billingDocument=?", (node_id,)).fetchone()
        items = conn.execute("SELECT * FROM billing_document_items WHERE billingDocument=?", (node_id,)).fetchall()
        result = {
            "header": dict(header) if header else {},
            "items": [dict(i) for i in items]
        }
    elif node_type == "Delivery":
        header = conn.execute("SELECT * FROM outbound_delivery_headers WHERE deliveryDocument=?", (node_id,)).fetchone()
        items = conn.execute("SELECT * FROM outbound_delivery_items WHERE deliveryDocument=?", (node_id,)).fetchall()
        result = {
            "header": dict(header) if header else {},
            "items": [dict(i) for i in items]
        }
    elif node_type == "JournalEntry":
        items = conn.execute("SELECT * FROM journal_entry_items WHERE accountingDocument=?", (node_id,)).fetchall()
        result = {"items": [dict(i) for i in items]}
    elif node_type == "Payment":
        items = conn.execute("SELECT * FROM payments WHERE accountingDocument=?", (node_id,)).fetchall()
        result = {"items": [dict(i) for i in items]}
    elif node_type == "Customer":
        partner = conn.execute("SELECT * FROM business_partners WHERE customer=?", (node_id,)).fetchone()
        result = {"partner": dict(partner) if partner else {}}
    elif node_type == "Product":
        product = conn.execute("SELECT * FROM products WHERE product=?", (node_id,)).fetchone()
        desc = conn.execute("SELECT * FROM product_descriptions WHERE product=? AND language='EN'", (node_id,)).fetchone()
        result = {
            "product": dict(product) if product else {},
            "description": dict(desc) if desc else {}
        }
    elif node_type == "Plant":
        plant = conn.execute("SELECT * FROM plants WHERE plant=?", (node_id,)).fetchone()
        result = {"plant": dict(plant) if plant else {}}

    conn.close()
    return result


# ─── Schema for NL-to-SQL ─────────────────────────────────────────────────────

DB_SCHEMA = """
SQLite tables (SAP Order-to-Cash):
sales_order_headers: salesOrder PK, soldToParty, totalNetAmount, overallDeliveryStatus(C=done/A=partial), overallOrdReltdBillgStatus(C=billed/A=partial), transactionCurrency, creationDate
sales_order_items: salesOrder, salesOrderItem, material, requestedQuantity, netAmount, productionPlant, storageLocation
billing_document_headers: billingDocument PK, billingDocumentType, totalNetAmount, billingDocumentDate, billingDocumentIsCancelled(1=yes), accountingDocument, soldToParty, companyCode, fiscalYear
billing_document_items: billingDocument, billingDocumentItem, material, billingQuantity, netAmount, referenceSdDocument(=deliveryDocument), referenceSdDocumentItem
outbound_delivery_headers: deliveryDocument PK, actualGoodsMovementDate, overallGoodsMovementStatus, shippingPoint
outbound_delivery_items: deliveryDocument, deliveryDocumentItem, actualDeliveryQuantity, plant, referenceSdDocument(=salesOrder), storageLocation
journal_entry_items: accountingDocument PK, accountingDocumentItem, referenceDocument(=billingDocument), glAccount, amountInCompanyCodeCurrency, companyCodeCurrency, postingDate, accountingDocumentType, customer, clearingDate, clearingAccountingDocument
payments: accountingDocument PK, accountingDocumentItem, clearingAccountingDocument(=journal accountingDocument), amountInCompanyCodeCurrency, transactionCurrency, customer, salesDocument, postingDate
business_partners: businessPartner PK, customer, businessPartnerFullName, organizationBpName1, industry
products: product PK (NOTE: join via products.product = *.material), productType, baseUnit, productGroup
product_descriptions: product, language, productDescription (use language='EN')
plants: plant PK, plantName, cityName, country
billing_document_cancellations: billingDocument PK, cancelledBillingDocument, creationDate

JOINS (critical):
SO→Delivery: outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
Delivery→Billing: billing_document_items.referenceSdDocument = outbound_delivery_headers.deliveryDocument
Billing→Journal: billing_document_headers.accountingDocument = journal_entry_items.accountingDocument
Journal→Payment: payments.clearingAccountingDocument = journal_entry_items.accountingDocument
SO→Customer: sales_order_headers.soldToParty = business_partners.customer
Item→Product: sales_order_items.material = products.product  AND  billing_document_items.material = products.product  (products has NO column named material — join key is products.product)
DeliveryItem→Plant: outbound_delivery_items.plant = plants.plant

ID ranges: salesOrder~740xxx, deliveryDocument~80738xxx, billingDocument~9050xxxx, accountingDocument~9400xxxxxx
"""

# ── Gemini model (initialised here so SYSTEM_PROMPT is in scope) ────────────
# (defined below after SYSTEM_PROMPT)

SQL_GENERATION_PROMPT = f"""You are a SQLite expert for an SAP Order-to-Cash system.
Given a user question, output ONLY a single valid SQLite SELECT query — no explanation, no markdown, no prose.
Just the raw SQL ending with a semicolon.

{DB_SCHEMA}

RULES:
- Output ONLY the SQL query, nothing else
- Always use correct column names exactly as listed above
- products table has column "product" (PK), NOT "material". Join: products.product = billing_document_items.material
- For product names use: JOIN product_descriptions pd ON pd.product = <table>.material AND pd.language = 'EN'
- LIMIT results to 20 rows unless the question asks for all
- Only SELECT statements — never INSERT/UPDATE/DELETE

FEW-SHOT EXAMPLES (follow these patterns exactly):

Q: Which products have the highest number of billing documents?
A: SELECT pd.productDescription, COUNT(DISTINCT bdi.billingDocument) AS num_billing_docs FROM billing_document_items bdi JOIN product_descriptions pd ON pd.product = bdi.material AND pd.language = 'EN' GROUP BY bdi.material ORDER BY num_billing_docs DESC LIMIT 10;

Q: Trace the full O2C flow of billing document 91150187
A: SELECT soh.salesOrder, odi.deliveryDocument, bdi.billingDocument, bdh.accountingDocument AS journalEntry FROM billing_document_items bdi JOIN outbound_delivery_headers odi ON odi.deliveryDocument = bdi.referenceSdDocument JOIN outbound_delivery_items odi2 ON odi2.deliveryDocument = odi.deliveryDocument JOIN sales_order_headers soh ON soh.salesOrder = odi2.referenceSdDocument JOIN billing_document_headers bdh ON bdh.billingDocument = bdi.billingDocument WHERE bdi.billingDocument = '91150187' LIMIT 1;

Q: Show top 5 customers by total revenue
A: SELECT bp.businessPartnerFullName, COUNT(DISTINCT bdh.billingDocument) AS total_bills, ROUND(SUM(bdh.totalNetAmount), 2) AS total_revenue, bdh.transactionCurrency FROM billing_document_headers bdh JOIN business_partners bp ON bp.customer = bdh.soldToParty GROUP BY bdh.soldToParty ORDER BY total_revenue DESC LIMIT 5;

Q: Find sales orders that have no delivery at all
A: SELECT soh.salesOrder, soh.totalNetAmount, soh.transactionCurrency, soh.creationDate FROM sales_order_headers soh WHERE NOT EXISTS (SELECT 1 FROM outbound_delivery_items odi WHERE odi.referenceSdDocument = soh.salesOrder) LIMIT 20;

Q: List all cancelled billing documents
A: SELECT bdc.billingDocument, bdc.cancelledBillingDocument, bdc.billingDocumentType, bdc.creationDate FROM billing_document_cancellations bdc ORDER BY bdc.creationDate DESC LIMIT 20;

Q: Which plants handle the most deliveries?
A: SELECT p.plantName, p.cityName, COUNT(DISTINCT odi.deliveryDocument) AS delivery_count FROM outbound_delivery_items odi JOIN plants p ON p.plant = odi.plant GROUP BY odi.plant ORDER BY delivery_count DESC LIMIT 10;

Q: Find sales orders delivered but not billed
A: SELECT soh.salesOrder, soh.totalNetAmount, soh.transactionCurrency FROM sales_order_headers soh WHERE soh.overallDeliveryStatus = 'C' AND (soh.overallOrdReltdBillgStatus IS NULL OR soh.overallOrdReltdBillgStatus = '') LIMIT 20;
"""

SYSTEM_PROMPT = f"""You are a data analyst assistant for an SAP Order-to-Cash (O2C) system.

{DB_SCHEMA}

YOUR ROLE:
- Answer questions ONLY about the provided Order-to-Cash dataset
- You will be given the user question AND the actual SQL query results already executed
- Interpret and explain the results clearly and concisely
- Never say "without executing" or "I cannot run" — the results are already provided to you

GUARDRAILS:
- If the user asks about anything NOT related to this Order-to-Cash dataset, respond ONLY with:
  "This system is designed to answer questions related to the Order-to-Cash dataset only."
- Base your answer strictly on the query results provided — do not invent data

RESPONSE FORMAT:
- Lead with the direct answer (e.g. "The top product is X with Y billing documents")
- Then briefly explain the pattern or insight
- For flow traces: list each step in order (SO → Delivery → Billing → Journal → Payment)
- Keep responses concise
"""



# Now that SYSTEM_PROMPT is defined, init Gemini
groq_client = _make_groq()

class ChatRequest(BaseModel):
    message: str
    history: list = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    client = groq_client or _make_groq()
    if not client:
        return {
            "response": "⚠️ No API key configured. Please set GROQ_API_KEY in backend/.env and restart the server. Get a free key at https://console.groq.com",
            "query_results": [],
            "highlighted_nodes": []
        }

    # ── Guardrail: reject off-topic questions before any LLM call ────────────
    off_topic_keywords = ["weather", "recipe", "joke", "poem", "write a story",
                          "capital of", "who is president", "explain quantum",
                          "translate", "movie", "sports score"]
    msg_lower = req.message.lower()
    if any(k in msg_lower for k in off_topic_keywords):
        return {
            "response": "This system is designed to answer questions related to the Order-to-Cash dataset only. Please ask questions about sales orders, deliveries, billing documents, payments, customers, or products.",
            "query_results": [],
            "highlighted_nodes": []
        }

    def call_groq(system: str, messages: list, max_tokens: int = 500) -> str:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system}] + messages,
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    time.sleep(10 * (attempt + 1))
                    continue
                raise e
        return ""

    # ── PASS 1: Generate SQL ──────────────────────────────────────────────────
    history_msgs = []
    for h in req.history[-6:]:
        role = h["role"] if h["role"] in ("user", "assistant") else "user"
        history_msgs.append({"role": role, "content": h["content"]})

    sql_raw = call_groq(
        system=SQL_GENERATION_PROMPT,
        messages=history_msgs + [{"role": "user", "content": req.message}],
        max_tokens=300
    )

    # Clean up SQL — strip markdown fences if model added them anyway
    sql = re.sub(r"```(?:sql)?\s*", "", sql_raw, flags=re.IGNORECASE).strip().rstrip("`").strip()

    # ── Execute SQL ───────────────────────────────────────────────────────────
    query_results = []
    results_text = ""
    conn = get_conn()
    try:
        if sql.upper().startswith("SELECT"):
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            data_rows = [list(r) for r in rows[:50]]
            query_results = {
                "columns": cols,
                "rows": data_rows,
                "total": len(rows),
                "sql": sql
            }
            # Format results as text for pass 2
            if rows:
                header = " | ".join(cols)
                lines = [header, "-" * len(header)]
                for row in rows[:20]:
                    lines.append(" | ".join(str(v) if v is not None else "NULL" for v in row))
                if len(rows) > 20:
                    lines.append(f"... ({len(rows)} total rows)")
                results_text = "\n".join(lines)
            else:
                results_text = "(query returned 0 rows)"
    except Exception as e:
        query_results = {"error": str(e), "sql": sql}
        results_text = f"SQL ERROR: {e}"
    finally:
        conn.close()

    # ── PASS 2: Explain results ───────────────────────────────────────────────
    explanation_prompt = f"""The user asked: {req.message}

I ran this SQL query:
{sql}

Results:
{results_text}

Now answer the user's question based on these actual results."""

    assistant_text = call_groq(
        system=SYSTEM_PROMPT,
        messages=history_msgs + [{"role": "user", "content": explanation_prompt}],
        max_tokens=600
    )

    if not assistant_text:
        assistant_text = "⚠️ Rate limit hit. Please wait a moment and try again."

    highlighted = extract_highlighted_nodes(assistant_text, query_results)
    return {
        "response": assistant_text,
        "query_results": query_results,
        "highlighted_nodes": highlighted
    }


# ID prefix map: detect entity type from numeric ID range
def _id_to_node_id(val: str) -> str | None:
    """Convert a raw document ID to a graph node ID like SO-740506."""
    s = str(val).strip()
    if not s.isdigit():
        return None
    n = int(s)
    if 740000 <= n <= 749999:
        return f"SO-{s}"
    if 80700000 <= n <= 80799999:
        return f"OD-{s}"
    if 90000000 <= n <= 99999999:
        return f"BD-{s}"
    if 9400000000 <= n <= 9499999999:
        return f"JE-{s}"
    if 320000000 <= n <= 329999999 or 310000000 <= n <= 319999999:
        return f"CUST-{s}"
    return None


def extract_highlighted_nodes(text: str, query_results: dict | list = None) -> list:
    """
    Extract graph node IDs to highlight from:
    1. query_results rows (most reliable — actual DB values)
    2. Text mentions as fallback
    """
    seen = set()
    nodes = []

    def add(node_id: str):
        if node_id and node_id not in seen:
            seen.add(node_id)
            nodes.append(node_id)

    # ── Primary: scan every cell in query results ────────────────────────────
    if isinstance(query_results, dict) and "rows" in query_results:
        cols = query_results.get("columns", [])
        for row in query_results["rows"]:
            for i, cell in enumerate(row):
                if cell is None:
                    continue
                col_name = cols[i].lower() if i < len(cols) else ""
                cell_str = str(cell).strip()

                # Column-name hints
                if "salesorder" in col_name or col_name == "referencesdocument":
                    add(f"SO-{cell_str}")
                elif "billingdocument" in col_name or "billdoc" in col_name:
                    add(f"BD-{cell_str}")
                elif "deliverydocument" in col_name or "delivery" in col_name:
                    add(f"OD-{cell_str}")
                elif "accountingdocument" in col_name or "journaldoc" in col_name:
                    add(f"JE-{cell_str}")
                elif "customer" in col_name or "soldtoparty" in col_name:
                    add(f"CUST-{cell_str}")
                elif "product" in col_name or "material" in col_name:
                    add(f"PROD-{cell_str}")
                elif "plant" in col_name:
                    add(f"PLT-{cell_str}")
                else:
                    # Fallback: guess from ID range
                    nid = _id_to_node_id(cell_str)
                    if nid:
                        add(nid)

    # ── Secondary: parse numbers from response text ──────────────────────────
    # Extract bare numbers 6-10 digits
    for m in re.findall(r'\b(\d{6,10})\b', text):
        nid = _id_to_node_id(m)
        if nid:
            add(nid)

    # Also check for explicit ID mentions in text
    for m in re.findall(r'(?:sales order|SO)[:\s#]*([78]?\d{5,7})', text, re.IGNORECASE):
        add(f"SO-{m}")
    for m in re.findall(r'(?:billing document|billing doc|BD)[:\s#]*(9\d{7,8})', text, re.IGNORECASE):
        add(f"BD-{m}")
    for m in re.findall(r'(?:delivery|OD)[:\s#]*(8\d{7,8})', text, re.IGNORECASE):
        add(f"OD-{m}")
    for m in re.findall(r'(?:journal entry|accounting document|JE)[:\s#]*(9[34]\d{8,9})', text, re.IGNORECASE):
        add(f"JE-{m}")

    return nodes[:20]  # cap at 20 highlighted nodes


# ─── Stats Endpoint ───────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    stats = {}
    for table, label in [
        ("sales_order_headers", "Sales Orders"),
        ("billing_document_headers", "Billing Documents"),
        ("outbound_delivery_headers", "Deliveries"),
        ("journal_entry_items", "Journal Entries"),
        ("payments", "Payments"),
        ("business_partners", "Customers"),
        ("products", "Products"),
        ("plants", "Plants"),
    ]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[label] = count
    conn.close()
    return stats


# ─── Serve Frontend ───────────────────────────────────────────────────────────

if os.path.exists(FRONTEND_BUILD):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_BUILD, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_BUILD, full_path)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))
else:
    @app.get("/")
    def root_fallback():
        return {"message": "Frontend not built. Please run npm run build."}
