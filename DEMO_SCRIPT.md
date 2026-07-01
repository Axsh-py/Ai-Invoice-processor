# OTM AI Invoice Preprocessor — Demo Script

**Duration:** 2–3 minutes  
**Audience:** Interviewer / business stakeholder  
**What to have open:** Streamlit app running at `http://localhost:8501`

---

## Setup Before Demo

```bash
python generate_samples.py   # creates 40 varied PDFs
streamlit run app.py         # launch the app
```

---

## The Story (speak this)

> "Imagine a logistics company — they receive invoices from 50+ freight vendors every day.
> Most invoices are incomplete. A vendor sends just a charge code — AFRT — and an amount.
> The finance team has to manually look up the shipment, verify the amount, fill in OTM fields, and key everything in by hand.
> That's 200+ clicks per invoice, dozens of invoices per day.
> This bot eliminates that entire process."

---

## Step-by-Step Demo

### Step 1 — Home Dashboard (30 seconds)

> "This is the home dashboard. It shows live KPIs:
> how many invoices were processed, how many auto-matched,
> how many went to human review, and the total invoice amount processed."

- Point to the KPI cards.
- Mention the average AI confidence score.

---

### Step 2 — Upload Invoice (45 seconds)

> "Let's process a real invoice. I'll go to Upload Invoice and pick a sample."

1. Click **Upload Invoice** in the sidebar.
2. Click the **Sample Invoice** tab.
3. Select `01_AFRT_TW_Dubai_Mumbai_matched.pdf`.
4. Click **Process Sample**.

> "Watch what happens:
> First, the original PDF is saved in storage/originals — it is never touched again.
> A working copy is created. The SHA-256 hash is recorded for legal proof.
> Then OCR extracts the text. OpenAI — or the mock parser — reads it and extracts structured fields.
> The system sees AFRT and maps it to 'Air Freight Charge' using the charge code master."

- Point to the **Extracted Data** panel: vendor, invoice number, charge code, amount.
- Point to the **Validation Result**: PASSED, MATCHED_IN_TOLERANCE.
- Point to the **OTM Payload Summary**: service provider, route, financial consolidation type.

> "The system matched this invoice to shipment SHP-202604150026, Dubai to Mumbai.
> The amount is within the 200 AED tolerance. Status: MATCHED_IN_TOLERANCE.
> An OTM draft was automatically created — no human touch needed."

---

### Step 3 — Email Intake Simulation (30 seconds)

> "In production, this connects to Outlook or Gmail and pulls invoice attachments automatically.
> In this demo, we simulate receiving 20 vendor emails."

1. Click **Email Intake** in the sidebar.
2. Click **Simulate Fetch & Process 20 Invoice Emails**.
3. Watch the progress bar.

> "Twenty invoices — different vendors, charge types, amounts — processed in seconds.
> Some matched automatically. Some went to review because of amount mismatches or missing data.
> Two were flagged as duplicates."

---

### Step 4 — Human Review Queue (30 seconds)

> "Any invoice that the bot cannot auto-approve goes here."

1. Click **Review Queue** in the sidebar.
2. Select an invoice with REVIEW_REQUIRED or DUPLICATE status.

> "The reviewer sees the original file path, working copy path, OCR text, extracted JSON,
> validation errors, the matched shipment, and the AI confidence score.
> They can approve, reject, or force-create an OTM draft manually."

- Show the approve button.
- Show the errors and warnings panel.

---

### Step 5 — OTM Draft Viewer (20 seconds)

> "This is the mock OTM screen. It shows exactly what the Oracle OTM invoice form would look like after being filled by the AI."

1. Click **OTM Draft Viewer** in the sidebar.
2. Select a processed invoice with ERP_DRAFT_CREATED.

> "Service Provider, Invoice Bill Rule, Financial Consolidation Type, Amount Due, VAT, line items —
> all auto-filled. In production, this payload is POSTed directly to Oracle OTM's REST API."

- Show the **Download OTM Payload JSON** button.
- Show the line items table.

---

### Step 6 — Settings (optional, 15 seconds)

> "The Settings page shows API status, database table statistics, and file storage."

- Show API key status (green/orange badges).
- Show the 7-table DB schema row counts.

---

## Key Talking Points

| Interviewer asks | Answer |
|-----------------|--------|
| "What if OpenAI API is down?" | Mock parser uses deterministic regex — zero downtime. |
| "What if the invoice is scanned (not digital)?" | Switch OCR mode to OCR.space. Azure Document Intelligence in production. |
| "How do you protect the original invoice?" | SHA-256 hash + immutable storage. Original is never modified. Working copy is used for processing. |
| "How does it handle duplicates?" | Duplicate check queries DB by invoice number + vendor + amount before insert. Status = DUPLICATE. |
| "How does AFRT mapping work?" | charge_code_master.json maps AFRT → Air Freight Charge, Freight cost type, 5% VAT, OTM accessorial code. |
| "Can it connect to real OTM?" | Yes. Replace `build_otm_payload()` with an OTM REST API POST call. The payload schema is already OTM-compatible. |
| "What about Gmail/Outlook integration?" | Replace the folder scan in `src/intake.py` with Gmail API or Microsoft Graph API. The rest of the pipeline is identical. |

---

## One-Line Pitch

> "This bot turns a vendor's 2-line invoice into a complete, validated, OTM-ready draft — automatically — while keeping the original invoice immutable for audit and legal compliance."
