import json
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.file_manager import save_path_as_original_and_copy
from src.pipeline import process_invoice
from src.config import EMAIL_INBOX_DIR, SAMPLE_INVOICES_DIR
from src.theme import apply, page_header

st.set_page_config(page_title="Email Intake — OTM AI", page_icon="📧", layout="wide")
apply()
init_db()

page_header("Email Intake Simulation",
            subtitle="Simulate batch invoice pickup from an email inbox folder.")
st.caption("Simulates automated invoice intake from a vendor email inbox. In production this connects to Outlook/Gmail API.")

with st.sidebar:
    st.header("Processing Controls")
    ai_mode = st.selectbox("AI Parser", ["mock", "openai"])
    # OCR mode is now fully automatic — no selection needed
    st.divider()
    inbox_choice = st.radio("Inbox Source", ["sample_email_inbox/", "data/sample_invoices/ (all 40)"])
    max_invoices = st.slider("Max invoices to process", 5, 40, 20)

st.markdown("""<div class="info-box">
<strong>Production note:</strong> In a real deployment this module connects to:
<ul style="margin:4px 0">
<li>Outlook/Gmail API — auto-download PDF attachments from invoices@company.com</li>
<li>SFTP/FTP drop folder — poll every 10 minutes</li>
<li>SharePoint or OneDrive — Microsoft Graph API</li>
<li>Vendor portal webhook — REST API callback</li>
</ul>
Each PDF is saved as an immutable original, then queued for OCR → AI processing.
</div>""", unsafe_allow_html=True)

if inbox_choice.startswith("sample_email_inbox"):
    inbox_dir = EMAIL_INBOX_DIR
else:
    inbox_dir = SAMPLE_INVOICES_DIR

pdf_files = sorted(inbox_dir.glob("*.pdf"))[:max_invoices]

st.write(f"**Inbox:** `{inbox_dir}`")
st.write(f"**PDFs found:** {len(pdf_files)}")

if not pdf_files:
    st.warning(f"No PDF files found in `{inbox_dir}`. Run `python generate_samples.py` first.")
    st.stop()

if st.button(f"Simulate Fetch & Process {len(pdf_files)} Invoice Emails", type="primary"):
    progress = st.progress(0, text="Starting...")
    status_area = st.empty()
    results = []

    for i, pdf_path in enumerate(pdf_files):
        progress.progress((i + 1) / len(pdf_files), text=f"Processing {pdf_path.name}...")
        try:
            record = save_path_as_original_and_copy(str(pdf_path), source="email_inbox")
            invoice_id, raw_text, extracted, validation, otm_payload, _ = process_invoice(record, ai_mode=ai_mode)
            v_status = validation.get("validation_status", "UNKNOWN")
            erp_status = otm_payload.get("erp_status", "")
            results.append({
                "ID": invoice_id,
                "File": pdf_path.name,
                "Vendor": (extracted.get("vendor_name") or "")[:25],
                "Invoice #": extracted.get("invoice_number") or "—",
                "Charge Code": extracted.get("charge_code") or "—",
                "Amount": f"{extracted.get('amount_due') or 0:,.2f}",
                "Currency": extracted.get("currency") or "—",
                "MBL": extracted.get("mbl_number") or "—",
                "Customer #": extracted.get("customer_number") or "—",
                "Tax Type": extracted.get("tax_type") or "—",
                "Validation": v_status,
                "VAT": validation.get("vat_status", ""),
                "Match": validation.get("match_status", ""),
                "OTM Status": erp_status,
                "Confidence": f"{(extracted.get('confidence_score') or 0)*100:.0f}%",
            })
        except Exception as exc:
            results.append({
                "ID": "ERR", "File": pdf_path.name, "Vendor": "—",
                "Invoice #": "—", "Charge Code": "—", "Amount": "—",
                "Currency": "—", "MBL": "—", "Customer #": "—", "Tax Type": "—",
                "Validation": "FAILED", "VAT": "—", "Match": "—",
                "OTM Status": f"ERROR: {str(exc)[:40]}", "Confidence": "—",
            })

    progress.empty()
    df = pd.DataFrame(results)

    passed = sum(1 for r in results if r["Validation"] == "PASSED")
    review = sum(1 for r in results if r["Validation"] in ("REVIEW_REQUIRED", "MISSING_DATA"))
    failed = sum(1 for r in results if r["Validation"] in ("FAILED", "DUPLICATE"))
    drafts = sum(1 for r in results if r["OTM Status"] == "ERP_DRAFT_CREATED")

    st.success(f"Processed {len(results)} invoices: {passed} passed, {review} need review, {failed} failed/duplicate, {drafts} OTM drafts created.")

    def _style_row(row):
        v = row.get("Validation", "")
        color = ("#e8f5e9" if v == "PASSED"
                 else "#fff3e0" if v in ("REVIEW_REQUIRED", "MISSING_DATA")
                 else "#ffebee")
        return [f"background-color: {color}"] * len(row)

    st.dataframe(df.style.apply(_style_row, axis=1), use_container_width=True, hide_index=True)

    st.download_button(
        "Download Batch Results CSV",
        df.to_csv(index=False),
        file_name="email_intake_batch.csv",
        mime="text/csv",
    )
