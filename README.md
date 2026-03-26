# Order-to-Cash Graph Explorer

A context graph system with LLM-powered query interface for exploring SAP Order-to-Cash process data.

![Graph Explorer Screenshot](docs/screenshot.png)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│  ┌─────────────────────────┐  ┌───────────────────────┐ │
│  │  D3 Force-Directed Graph │  │   Chat Panel (Claude) │ │
│  │  - Zoom / Pan            │  │   - NL → SQL          │ │
│  │  - Click tooltips        │  │   - Result tables     │ │
│  │  - Node highlighting     │  │   - Guardrails        │ │
│  └─────────────────────────┘  └───────────────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / REST
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend                        │
│  GET  /api/graph      → nodes + edges (557 / 526)        │
│  GET  /api/stats      → entity counts                    │
│  GET  /api/node/:t/:id→ node detail                      │
│  POST /api/chat       → Claude NL-to-SQL                 │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   SQLite Database                        │
│  13 tables: sales_order_headers, billing_document_*,     │
│  outbound_delivery_*, journal_entry_items, payments,      │
│  business_partners, products, product_descriptions,      │
│  plants, billing_document_cancellations                  │
└─────────────────────────────────────────────────────────┘
```

## Graph Model

### Nodes (8 types)
| Type | Color | Key Field |
|------|-------|-----------|
| SalesOrder | Blue | salesOrder |
| Delivery | Amber | deliveryDocument |
| BillingDocument | Purple | billingDocument |
| JournalEntry | Green | accountingDocument |
| Payment | Pink | accountingDocument |
| Customer | Red | customer |
| Product | Indigo | product |
| Plant | Teal | plant |

### Edges (4 types)
```
SalesOrder ──HAS_DELIVERY──▶ Delivery
Delivery   ──HAS_BILLING───▶ BillingDocument
BillingDoc ──HAS_JOURNAL───▶ JournalEntry
JournalEntry──CLEARED_BY──▶ Payment
SalesOrder ──SOLD_TO───────▶ Customer
SalesOrder ──CONTAINS_PROD─▶ Product
Delivery   ──SHIPPED_FROM──▶ Plant
```

## Database Choice: SQLite

**Why SQLite over Neo4j or PostgreSQL?**

- **Zero setup** — single file, no server process, perfect for interview demo
- **Rich SQL** — complex O2C flow queries need multi-hop JOINs, which SQL handles elegantly
- **LLM-friendly** — Claude can reason about SQL schemas much better than Cypher
- **Fast enough** — 13 tables, ~2000 total rows, all in-memory for query purposes

The graph is constructed in Python from the relational data and served as JSON to D3.js — we get the best of both worlds: SQL's query power and graph visualization.

## LLM Prompting Strategy

The system prompt gives Claude:
1. **Full schema** with all 13 tables, column names, and types
2. **Key relationships** — the actual join keys discovered by data inspection (e.g. `billing_document_items.referenceSdDocument` points to `deliveryDocument`, not `salesOrder`)
3. **Document ID ranges** — so Claude knows ~740xxx = SalesOrder, ~80738xxx = Delivery, etc.
4. **Response format** — SQL in code fences, then natural language explanation
5. **Guardrails** — explicit instruction to reject off-topic queries

### Guardrails Implementation

The system prompt instructs Claude to respond with a fixed rejection message for off-topic queries. This is enforced at the prompt level (fast, no additional API calls). The rejection message is:

> "This system is designed to answer questions related to the Order-to-Cash dataset only."

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+ (only needed to rebuild frontend)
- An Anthropic API key

### 1. Configure API Key

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and add your ANTHROPIC_API_KEY
```

### 2. Load Data

```bash
pip install -r backend/requirements.txt
python backend/load_data.py
```

### 3. Start Server

```bash
# Option A: use the start script
./start.sh

# Option B: manual
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 4. Open App

Navigate to **http://localhost:8000**

## Development (Hot Reload)

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev   # runs on :5173, proxies /api to :8000
```

## Example Queries

The chat interface can answer questions like:

- *"Which products are associated with the highest number of billing documents?"*
- *"Trace the full flow of billing document 90504298"*
- *"Find sales orders that were delivered but never billed"*
- *"What is the total revenue per customer?"*
- *"Show me all cancelled billing documents"*
- *"Which plants handle the most deliveries?"*

## Project Structure

```
project/
├── backend/
│   ├── main.py          # FastAPI app — graph, chat, node detail endpoints
│   ├── load_data.py     # JSONL → SQLite ETL
│   ├── requirements.txt
│   ├── .env             # Your API key (git-ignored)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Main layout
│   │   ├── components/
│   │   │   ├── GraphView.jsx     # D3 force graph
│   │   │   └── ChatPanel.jsx     # Claude chat UI
│   │   └── index.css
│   ├── dist/            # Built frontend (served by FastAPI)
│   └── package.json
├── sap-o2c-data/        # Raw JSONL dataset
├── start.sh
└── README.md
```
