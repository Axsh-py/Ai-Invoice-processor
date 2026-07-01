# OTM AI Invoice Preprocessor

A **production-grade mock demo** for AI-driven logistics invoice automation using Oracle OTM (Transportation Management) patterns. Built to show how an AI bot can receive incomplete vendor invoices, enrich missing fields, match them with shipment reference data, validate tolerance and VAT, and create complete OTM-ready invoice drafts — all while keeping originals immutable.

---

## Business Problem

Logistics companies receive hundreds of vendor invoices every day. Many are **incomplete** — a vendor submits only a charge code and amount, with no shipment ID, no route, no OTM field mapping. Finance teams manually look up shipments, fill in missing fields, validate amounts, and key data into Oracle OTM. This is slow, error-prone, and expensive.

**This system automates that entire process.**

---

## Solution Architecture

```
Invoice Sources
  Vendor email (PDF attachment)    →  Gmail/Outlook API (production)
  SFTP/FTP drop folder             →  Paramiko polling (production)
  Vendor portal                    →  REST webhook (production)
  SharePoint / OneDrive            →  Microsoft Graph API (production)
  Demo: manual upload or sample_email_inbox/
         ↓
Invoice Collector Bot
         ↓
Immutable Original Storage  →  storage/originals/YYYY/MM/  [SHA-256 hash]
         ↓
Working Copy Creation       →  storage/working_copies/YYYY/MM/
         ↓
OCR Layer                   →  PyPDF (text PDF) or OCR.space API (scanned)
         ↓
OpenAI GPT-4o-mini Parser   →  Structured JSON + Pydantic validation
         ↓
Charge Code Mapping         →  AFRT=Air Freight | DFRT=Delivery | CUST=Customs | WHSE=Warehouse | TRANS=Transport
         ↓
Shipment / SP Enrichment    →  Match mock_shipments.json + service_providers.json
         ↓
VAT Calculation & Check     →  5% default | configurable | VAT_MATCHED / VAT_MISMATCH
         ↓
Tolerance Validation        →  MATCHED | MATCHED_IN_TOLERANCE | REVIEW_REQUIRED | DUPLICATE | MISSING_DATA
         ↓
OTM-Ready Draft Payload     →  invoice_header + line_items + summary
         ↓
Auto-create OTM Draft  OR  Send to Human Review Queue
```

---

## How Original Invoice Safety Works

The system enforces a strict **immutable original** pattern:

1. When a PDF is received, it is saved to `storage/originals/YYYY/MM/` — this file is **never touched again**.
2. A SHA-256 hash of the original is computed and stored in the database for legal/audit proof.
3. A working copy is created in `storage/working_copies/YYYY/MM/`.
4. All OCR, AI parsing, enrichment, and validation happens **only on the working copy**.
5. If reprocessing is needed, a new working copy is created — the original is always preserved.

---

## How the OCR Layer Works

- **pdf_text mode** (default): Uses `pypdf` to extract embedded text from digital PDFs. Fast, works offline, no API needed.
- **ocr_space mode**: Calls OCR.space REST API, which works on scanned/image-based PDFs. Uses the free `helloworld` key for demo.
- Production upgrade options: Azure Document Intelligence, Google Document AI, AWS Textract, PaddleOCR.

---

## How the OpenAI Parser Works

1. OCR text is passed to GPT-4o-mini with a **production-grade system prompt** (`src/prompts/invoice_parser_prompt.py`).
2. The model returns only valid JSON — enforced via `response_format={"type": "json_object"}`.
3. The JSON is validated against a **Pydantic schema** (`src/schemas.py`) — invalid values are coerced or nulled.
4. If the JSON is malformed, a **repair prompt** is sent once. If still invalid, the mock parser is used as fallback.
5. Mock parser uses deterministic regex extraction — works 100% offline with no API key.

---

## How AFRT Mapping Works

AFRT is a common logistics charge code meaning **Air Freight Charge**. When the AI or regex parser finds `AFRT` in the OCR text, the system:

1. Looks it up in `data/charge_code_master.json`.
2. Fills in: `cost_type = Freight`, `description = Air Freight Charge`, `category = freight`, `tax_rate = 5%`.
3. Maps `accessorial_code = AFRT` in the OTM line item.
4. The same logic applies to DFRT, CUST, WHSE, TRANS, FUEL.

---

## How Matching and Tolerance Works

After AI extraction, the **matcher** (`src/matcher.py`) scores all mock shipments:

| Signal | Score |
|--------|-------|
| Exact shipment ID match | +50 |
| Invoice number hint match | +30 |
| Charge code match | +25 |
| Service provider ID match | +20 |
| Vendor name match | +10 |
| Route keyword match | +10 |
| Amount within tolerance | +20 |

The highest-scored shipment wins. The **validator** (`src/validator.py`) then checks:

- Is the invoice a **duplicate** (same number + vendor + amount already in DB)?
- Are critical fields **missing** (invoice number, vendor, amount)?
- Is the **currency** correct?
- Is the **amount within tolerance**? (configured per charge code in `data/tolerance_rules.json`)
- Does the **VAT** match the calculated 5%?

**Validation status codes:**
- `PASSED` — all checks pass, OTM draft auto-created
- `MATCHED_IN_TOLERANCE` — amount differs but within tolerance
- `REVIEW_REQUIRED` — warnings present (amount mismatch, currency issue, low confidence)
- `DUPLICATE` — same invoice already in system
- `MISSING_DATA` — critical fields absent
- `FAILED` — unknown charge code or hard errors

---

## How the Mock OTM Draft Works

`src/otm_payload.py` builds an OTM-style invoice payload:

```json
{
  "erp_status": "ERP_DRAFT_CREATED",
  "erp_invoice_id": "OTM-DRAFT-20260301120000",
  "invoice_header": {
    "invoice_number": "1338/25-26",
    "financial_consolidation_type": "STANDARD",
    "service_provider_id": "TW.300001490621360",
    "service_provider_alias_qualifier": "GLOG",
    "invoice_source": "AI_PREPROCESSOR",
    "invoice_bill_rule_id": "INVOICE PER LINE",
    "currency": "AED",
    "amount_due": 73000.00,
    "vat_amount": 3650.00,
    "amount_due_with_vat": 76650.00
  },
  "line_items": [{
    "line_item_sequence": 1,
    "cost_type": "Freight",
    "description": "Air Freight Charge",
    "accessorial_code": "AFRT",
    "preprocess_status": "MATCHED_IN_TOLERANCE"
  }]
}
```

This payload can be POSTed to Oracle OTM's REST API in production.

---

## Project Structure

```
otm_ai_invoice_preprocessor/
├── app.py                          # Home / KPI dashboard (Streamlit entry point)
├── generate_samples.py             # Generates 40 varied sample PDFs
├── requirements.txt
├── .env.example
├── README.md
├── DEMO_SCRIPT.md
├── sample_email_inbox/             # PDFs for email simulation (20 varied invoices)
├── data/
│   ├── app.db                      # SQLite database (7 tables)
│   ├── sample_invoices/            # 40 varied vendor invoice PDFs
│   ├── charge_code_master.json     # AFRT, DFRT, CUST, WHSE, TRANS, FUEL
│   ├── service_providers.json      # 6 approved vendors
│   ├── mock_shipments.json         # 10 reference shipments
│   └── tolerance_rules.json        # Per-code tolerances and validation rules
├── storage/
│   ├── originals/YYYY/MM/          # Immutable original PDFs + SHA-256 hash
│   ├── working_copies/YYYY/MM/     # Processing copies
│   ├── processed/                  # Output JSON payloads
│   └── failed/                     # Failed invoice error logs
├── src/
│   ├── config.py                   # All path constants
│   ├── database.py                 # 7-table SQLite schema + CRUD
│   ├── file_manager.py             # Original/working copy save with hash
│   ├── intake.py                   # Inbox scanning and file routing
│   ├── ocr.py                      # PyPDF + OCR.space
│   ├── ai_parser.py                # Mock regex + OpenAI GPT parser
│   ├── prompts/
│   │   └── invoice_parser_prompt.py  # Production-grade system + user prompt
│   ├── schemas.py                  # Pydantic models for AI output validation
│   ├── matcher.py                  # Shipment + SP + charge code matching
│   ├── tax.py                      # VAT calculation + validation
│   ├── validator.py                # Full validation (dup, missing, tolerance, VAT)
│   ├── otm_payload.py              # OTM-style draft payload builder
│   ├── logger.py                   # Step-by-step processing log
│   └── pipeline.py                 # End-to-end orchestration
└── pages/
    ├── 1_Overview.py               # KPI charts and processing trends
    ├── 2_Upload_Invoice.py         # Manual upload + sample selector
    ├── 3_Email_Intake.py           # Batch simulation from inbox folder
    ├── 4_Processed_Invoices.py     # All invoices with filters + debug tabs
    ├── 5_Review_Queue.py           # Exception queue with approve/reject
    ├── 6_OTM_Draft_Viewer.py       # Mock OTM screen with actions
    └── 7_Settings.py               # API status, DB stats, config
```

---

## How to Run Locally

**1. Clone and create environment:**
```bash
cd otm_ai_invoice_preprocessor
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

**2. Install dependencies:**
```bash
pip install -r requirements.txt
```

**3. Configure environment:**
```bash
copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux
```

**4. Generate sample invoices (40 varied PDFs):**
```bash
python generate_samples.py
```

**5. Launch the app:**
```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key — leave blank for mock mode |
| `AI_MODE` | `mock` | `mock` or `openai` |
| `OCR_SPACE_API_KEY` | `helloworld` | OCR.space API key (free demo key) |
| `OCR_MODE` | `pdf_text` | `pdf_text` or `ocr_space` |
| `VAT_RATE` | `0.05` | Default VAT rate (5%) |
| `DEFAULT_CURRENCY` | `AED` | Default currency |

---

## Sample Invoice Variety (40 PDFs)

The sample generator creates invoices across 5 different vendor layouts and charge types:

| Type | Count | Description |
|------|-------|-------------|
| AFRT (Air Freight) | 10 | Transworld Logistics, Dubai routes, matched/tolerance/mismatch |
| DFRT (Delivery) | 5 | Aramex, UAE local delivery |
| CUST (Customs) | 5 | DHL Express, import customs fees |
| WHSE (Warehouse) | 4 | Gulf Bridge Warehousing |
| TRANS (Transport) | 4 | Khalid General Transport |
| Duplicates | 2 | Same invoice resubmitted |
| Missing invoice # | 3 | Invoice number field blank |
| Wrong VAT | 2 | 10% or 15% instead of 5% |
| Missing vendor | 2 | Vendor name not provided |
| Unknown charge code | 1 | XYZQ — not in master |
| Currency mismatch | 1 | USD invoice vs AED expected |
| Amount mismatch | 2 | Way outside tolerance |

---

## Future Production Integration

| Component | Production Integration |
|-----------|----------------------|
| Email intake | Outlook/Gmail API + OAuth2 — poll invoices@company.com |
| SFTP | Paramiko + watchdog — auto-detect new files |
| SharePoint | Microsoft Graph API |
| Vendor portal | REST webhook callback |
| OCR (scanned PDFs) | Azure Document Intelligence or AWS Textract |
| OTM API | Oracle OTM REST API — POST to invoice creation endpoint |
| Auth/SSO | Oracle IDCS or Azure AD integration |
| Audit trail | Immutable storage (S3/Azure Blob) + checksum database |
| Monitoring | Prometheus + Grafana or Datadog |
| Queue | Celery + Redis for async processing at scale |
