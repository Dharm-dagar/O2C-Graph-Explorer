import sqlite3
import json
import glob
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "sap-o2c-data")
DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")


def load_jsonl(pattern):
    records = []
    for path in glob.glob(pattern):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def create_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sales_order_headers (
        salesOrder TEXT PRIMARY KEY,
        salesOrderType TEXT,
        salesOrganization TEXT,
        distributionChannel TEXT,
        soldToParty TEXT,
        creationDate TEXT,
        totalNetAmount REAL,
        overallDeliveryStatus TEXT,
        overallOrdReltdBillgStatus TEXT,
        transactionCurrency TEXT,
        requestedDeliveryDate TEXT,
        customerPaymentTerms TEXT
    );

    CREATE TABLE IF NOT EXISTS sales_order_items (
        salesOrder TEXT,
        salesOrderItem TEXT,
        material TEXT,
        requestedQuantity REAL,
        requestedQuantityUnit TEXT,
        netAmount REAL,
        transactionCurrency TEXT,
        productionPlant TEXT,
        storageLocation TEXT,
        PRIMARY KEY (salesOrder, salesOrderItem)
    );

    CREATE TABLE IF NOT EXISTS billing_document_headers (
        billingDocument TEXT PRIMARY KEY,
        billingDocumentType TEXT,
        creationDate TEXT,
        billingDocumentDate TEXT,
        billingDocumentIsCancelled INTEGER,
        cancelledBillingDocument TEXT,
        totalNetAmount REAL,
        transactionCurrency TEXT,
        companyCode TEXT,
        fiscalYear TEXT,
        accountingDocument TEXT,
        soldToParty TEXT
    );

    CREATE TABLE IF NOT EXISTS billing_document_items (
        billingDocument TEXT,
        billingDocumentItem TEXT,
        material TEXT,
        billingQuantity REAL,
        billingQuantityUnit TEXT,
        netAmount REAL,
        transactionCurrency TEXT,
        referenceSdDocument TEXT,
        referenceSdDocumentItem TEXT,
        PRIMARY KEY (billingDocument, billingDocumentItem)
    );

    CREATE TABLE IF NOT EXISTS outbound_delivery_headers (
        deliveryDocument TEXT PRIMARY KEY,
        actualGoodsMovementDate TEXT,
        creationDate TEXT,
        overallGoodsMovementStatus TEXT,
        overallPickingStatus TEXT,
        shippingPoint TEXT
    );

    CREATE TABLE IF NOT EXISTS outbound_delivery_items (
        deliveryDocument TEXT,
        deliveryDocumentItem TEXT,
        actualDeliveryQuantity REAL,
        deliveryQuantityUnit TEXT,
        plant TEXT,
        referenceSdDocument TEXT,
        referenceSdDocumentItem TEXT,
        storageLocation TEXT,
        PRIMARY KEY (deliveryDocument, deliveryDocumentItem)
    );

    CREATE TABLE IF NOT EXISTS journal_entry_items (
        accountingDocument TEXT,
        accountingDocumentItem TEXT,
        companyCode TEXT,
        fiscalYear TEXT,
        glAccount TEXT,
        referenceDocument TEXT,
        transactionCurrency TEXT,
        amountInTransactionCurrency REAL,
        companyCodeCurrency TEXT,
        amountInCompanyCodeCurrency REAL,
        postingDate TEXT,
        documentDate TEXT,
        accountingDocumentType TEXT,
        customer TEXT,
        financialAccountType TEXT,
        clearingDate TEXT,
        clearingAccountingDocument TEXT,
        PRIMARY KEY (accountingDocument, accountingDocumentItem)
    );

    CREATE TABLE IF NOT EXISTS payments (
        accountingDocument TEXT,
        accountingDocumentItem TEXT,
        companyCode TEXT,
        fiscalYear TEXT,
        clearingDate TEXT,
        clearingAccountingDocument TEXT,
        amountInTransactionCurrency REAL,
        transactionCurrency TEXT,
        amountInCompanyCodeCurrency REAL,
        companyCodeCurrency TEXT,
        customer TEXT,
        invoiceReference TEXT,
        salesDocument TEXT,
        postingDate TEXT,
        PRIMARY KEY (accountingDocument, accountingDocumentItem)
    );

    CREATE TABLE IF NOT EXISTS business_partners (
        businessPartner TEXT PRIMARY KEY,
        customer TEXT,
        businessPartnerCategory TEXT,
        businessPartnerFullName TEXT,
        businessPartnerName TEXT,
        firstName TEXT,
        lastName TEXT,
        organizationBpName1 TEXT,
        industry TEXT,
        creationDate TEXT
    );

    CREATE TABLE IF NOT EXISTS products (
        product TEXT PRIMARY KEY,
        productType TEXT,
        baseUnit TEXT,
        productGroup TEXT,
        grossWeight REAL,
        netWeight REAL,
        weightUnit TEXT
    );

    CREATE TABLE IF NOT EXISTS product_descriptions (
        product TEXT,
        language TEXT,
        productDescription TEXT,
        PRIMARY KEY (product, language)
    );

    CREATE TABLE IF NOT EXISTS plants (
        plant TEXT PRIMARY KEY,
        plantName TEXT,
        cityName TEXT,
        country TEXT
    );

    CREATE TABLE IF NOT EXISTS billing_document_cancellations (
        billingDocument TEXT PRIMARY KEY,
        billingDocumentType TEXT,
        cancelledBillingDocument TEXT,
        creationDate TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_soi_salesorder ON sales_order_items(salesOrder);
    CREATE INDEX IF NOT EXISTS idx_soi_material ON sales_order_items(material);
    CREATE INDEX IF NOT EXISTS idx_bdi_billdoc ON billing_document_items(billingDocument);
    CREATE INDEX IF NOT EXISTS idx_bdi_refso ON billing_document_items(referenceSdDocument);
    CREATE INDEX IF NOT EXISTS idx_odi_deliv ON outbound_delivery_items(deliveryDocument);
    CREATE INDEX IF NOT EXISTS idx_odi_refso ON outbound_delivery_items(referenceSdDocument);
    CREATE INDEX IF NOT EXISTS idx_jei_doc ON journal_entry_items(accountingDocument);
    CREATE INDEX IF NOT EXISTS idx_jei_ref ON journal_entry_items(referenceDocument);
    CREATE INDEX IF NOT EXISTS idx_pay_clearing ON payments(clearingAccountingDocument);
    CREATE INDEX IF NOT EXISTS idx_bdh_accdoc ON billing_document_headers(accountingDocument);
    CREATE INDEX IF NOT EXISTS idx_bp_customer ON business_partners(customer);
    """)
    conn.commit()


def insert_records(conn, table, records, field_map):
    if not records:
        return
    cols = list(field_map.keys())
    placeholders = ", ".join(["?" for _ in cols])
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"
    data = []
    for r in records:
        row = []
        for col, src in field_map.items():
            val = r.get(src) if src else None
            if isinstance(val, str) and val == "":
                val = None
            row.append(val)
        data.append(row)
    conn.executemany(sql, data)
    conn.commit()


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)

    # Sales order headers
    records = load_jsonl(f"{DATA_DIR}/sales_order_headers/part-*.jsonl")
    insert_records(conn, "sales_order_headers", records, {
        "salesOrder": "salesOrder", "salesOrderType": "salesOrderType",
        "salesOrganization": "salesOrganization", "distributionChannel": "distributionChannel",
        "soldToParty": "soldToParty", "creationDate": "creationDate",
        "totalNetAmount": "totalNetAmount", "overallDeliveryStatus": "overallDeliveryStatus",
        "overallOrdReltdBillgStatus": "overallOrdReltdBillgStatus",
        "transactionCurrency": "transactionCurrency", "requestedDeliveryDate": "requestedDeliveryDate",
        "customerPaymentTerms": "customerPaymentTerms"
    })
    print(f"Loaded {len(records)} sales_order_headers")

    # Sales order items
    records = load_jsonl(f"{DATA_DIR}/sales_order_items/part-*.jsonl")
    insert_records(conn, "sales_order_items", records, {
        "salesOrder": "salesOrder", "salesOrderItem": "salesOrderItem",
        "material": "material", "requestedQuantity": "requestedQuantity",
        "requestedQuantityUnit": "requestedQuantityUnit", "netAmount": "netAmount",
        "transactionCurrency": "transactionCurrency", "productionPlant": "productionPlant",
        "storageLocation": "storageLocation"
    })
    print(f"Loaded {len(records)} sales_order_items")

    # Billing document headers
    records = load_jsonl(f"{DATA_DIR}/billing_document_headers/part-*.jsonl")
    insert_records(conn, "billing_document_headers", records, {
        "billingDocument": "billingDocument", "billingDocumentType": "billingDocumentType",
        "creationDate": "creationDate", "billingDocumentDate": "billingDocumentDate",
        "billingDocumentIsCancelled": "billingDocumentIsCancelled",
        "cancelledBillingDocument": "cancelledBillingDocument",
        "totalNetAmount": "totalNetAmount", "transactionCurrency": "transactionCurrency",
        "companyCode": "companyCode", "fiscalYear": "fiscalYear",
        "accountingDocument": "accountingDocument", "soldToParty": "soldToParty"
    })
    print(f"Loaded {len(records)} billing_document_headers")

    # Billing document items
    records = load_jsonl(f"{DATA_DIR}/billing_document_items/part-*.jsonl")
    insert_records(conn, "billing_document_items", records, {
        "billingDocument": "billingDocument", "billingDocumentItem": "billingDocumentItem",
        "material": "material", "billingQuantity": "billingQuantity",
        "billingQuantityUnit": "billingQuantityUnit", "netAmount": "netAmount",
        "transactionCurrency": "transactionCurrency", "referenceSdDocument": "referenceSdDocument",
        "referenceSdDocumentItem": "referenceSdDocumentItem"
    })
    print(f"Loaded {len(records)} billing_document_items")

    # Outbound delivery headers
    records = load_jsonl(f"{DATA_DIR}/outbound_delivery_headers/part-*.jsonl")
    insert_records(conn, "outbound_delivery_headers", records, {
        "deliveryDocument": "deliveryDocument", "actualGoodsMovementDate": "actualGoodsMovementDate",
        "creationDate": "creationDate", "overallGoodsMovementStatus": "overallGoodsMovementStatus",
        "overallPickingStatus": "overallPickingStatus", "shippingPoint": "shippingPoint"
    })
    print(f"Loaded {len(records)} outbound_delivery_headers")

    # Outbound delivery items
    records = load_jsonl(f"{DATA_DIR}/outbound_delivery_items/part-*.jsonl")
    insert_records(conn, "outbound_delivery_items", records, {
        "deliveryDocument": "deliveryDocument", "deliveryDocumentItem": "deliveryDocumentItem",
        "actualDeliveryQuantity": "actualDeliveryQuantity", "deliveryQuantityUnit": "deliveryQuantityUnit",
        "plant": "plant", "referenceSdDocument": "referenceSdDocument",
        "referenceSdDocumentItem": "referenceSdDocumentItem", "storageLocation": "storageLocation"
    })
    print(f"Loaded {len(records)} outbound_delivery_items")

    # Journal entry items
    records = load_jsonl(f"{DATA_DIR}/journal_entry_items_accounts_receivable/part-*.jsonl")
    insert_records(conn, "journal_entry_items", records, {
        "accountingDocument": "accountingDocument", "accountingDocumentItem": "accountingDocumentItem",
        "companyCode": "companyCode", "fiscalYear": "fiscalYear",
        "glAccount": "glAccount", "referenceDocument": "referenceDocument",
        "transactionCurrency": "transactionCurrency",
        "amountInTransactionCurrency": "amountInTransactionCurrency",
        "companyCodeCurrency": "companyCodeCurrency",
        "amountInCompanyCodeCurrency": "amountInCompanyCodeCurrency",
        "postingDate": "postingDate", "documentDate": "documentDate",
        "accountingDocumentType": "accountingDocumentType",
        "customer": "customer", "financialAccountType": "financialAccountType",
        "clearingDate": "clearingDate", "clearingAccountingDocument": "clearingAccountingDocument"
    })
    print(f"Loaded {len(records)} journal_entry_items")

    # Payments
    records = load_jsonl(f"{DATA_DIR}/payments_accounts_receivable/part-*.jsonl")
    insert_records(conn, "payments", records, {
        "accountingDocument": "accountingDocument", "accountingDocumentItem": "accountingDocumentItem",
        "companyCode": "companyCode", "fiscalYear": "fiscalYear",
        "clearingDate": "clearingDate", "clearingAccountingDocument": "clearingAccountingDocument",
        "amountInTransactionCurrency": "amountInTransactionCurrency",
        "transactionCurrency": "transactionCurrency",
        "amountInCompanyCodeCurrency": "amountInCompanyCodeCurrency",
        "companyCodeCurrency": "companyCodeCurrency",
        "customer": "customer", "invoiceReference": "invoiceReference",
        "salesDocument": "salesDocument", "postingDate": "postingDate"
    })
    print(f"Loaded {len(records)} payments")

    # Business partners
    records = load_jsonl(f"{DATA_DIR}/business_partners/part-*.jsonl")
    insert_records(conn, "business_partners", records, {
        "businessPartner": "businessPartner", "customer": "customer",
        "businessPartnerCategory": "businessPartnerCategory",
        "businessPartnerFullName": "businessPartnerFullName",
        "businessPartnerName": "businessPartnerName",
        "firstName": "firstName", "lastName": "lastName",
        "organizationBpName1": "organizationBpName1", "industry": "industry",
        "creationDate": "creationDate"
    })
    print(f"Loaded {len(records)} business_partners")

    # Products
    records = load_jsonl(f"{DATA_DIR}/products/part-*.jsonl")
    insert_records(conn, "products", records, {
        "product": "product", "productType": "productType",
        "baseUnit": "baseUnit", "productGroup": "productGroup",
        "grossWeight": "grossWeight", "netWeight": "netWeight",
        "weightUnit": "weightUnit"
    })
    print(f"Loaded {len(records)} products")

    # Product descriptions
    records = load_jsonl(f"{DATA_DIR}/product_descriptions/part-*.jsonl")
    insert_records(conn, "product_descriptions", records, {
        "product": "product", "language": "language",
        "productDescription": "productDescription"
    })
    print(f"Loaded {len(records)} product_descriptions")

    # Plants
    records = load_jsonl(f"{DATA_DIR}/plants/part-*.jsonl")
    insert_records(conn, "plants", records, {
        "plant": "plant", "plantName": "plantName",
        "cityName": "cityName", "country": "country"
    })
    print(f"Loaded {len(records)} plants")

    # Billing document cancellations
    records = load_jsonl(f"{DATA_DIR}/billing_document_cancellations/part-*.jsonl")
    insert_records(conn, "billing_document_cancellations", records, {
        "billingDocument": "billingDocument", "billingDocumentType": "billingDocumentType",
        "cancelledBillingDocument": "cancelledBillingDocument", "creationDate": "creationDate"
    })
    print(f"Loaded {len(records)} billing_document_cancellations")

    conn.close()
    print(f"\nDatabase created at: {DB_PATH}")


if __name__ == "__main__":
    main()
