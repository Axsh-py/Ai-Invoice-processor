import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db, list_invoices, get_invoice_full, get_processing_logs
from src.theme import apply, page_header

st.set_page_config(page_title="Processed Invoices — OTM AI", page_icon="📋", layout="wide")
apply()
init_db()

page_header("Processed Invoices",
            subtitle="All invoices processed by the AI pipeline — extracted data, validation results, OCR debug.")

invoices = list_invoices(limit=500)

if not invoices:
    st.info("No invoices yet. Go to Upload Invoice or Email Intake Simulation.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    statuses = ["All"] + sorted({r.get("validation_status") or "UNKNOWN" for r in invoices})
    sel_status = st.selectbox("Validation Status", statuses)
    charges = ["All"] + sorted({r.get("charge_code") or "UNKNOWN" for r in invoices if r.get("charge_code")})
    sel_charge = st.selectbox("Charge Code", charges)
    sources = ["All"] + sorted({r.get("source_type") or "unknown" for r in invoices})
    sel_source = st.selectbox("Source Type", sources)

filtered = invoices
if sel_status != "All":
    filtered = [r for r in filtered if r.get("validation_status") == sel_status]
if sel_charge != "All":
    filtered = [r for r in filtered if r.get("charge_code") == sel_charge]
if sel_source != "All":
    filtered = [r for r in filtered if r.get("source_type") == sel_source]

st.write(f"Showing **{len(filtered)}** of **{len(invoices)}** invoices")

rows = []
for r in filtered:
    vs = r.get("validation_status", "")
    ms = r.get("match_status", "")
    rows.append({
        "ID": r["id"],
        "Vendor": (r.get("vendor_name") or "")[:28],
        "Invoice #": r.get("invoice_number") or "—",
        "Date": r.get("invoice_date") or "—",
        "Charge": r.get("charge_code") or "—",
        "Category": r.get("invoice_category") or "—",
        "Amount": f"{r.get('amount_due') or 0:,.2f}",
        "Currency": r.get("currency") or "—",
        "VAT Status": r.get("vat_status") or "—",
        "Validation": vs,
        "Match": ms,
        "ERP Status": r.get("erp_status") or "—",
        "Confidence": f"{(r.get('confidence') or 0)*100:.0f}%",
        "Source": r.get("source_type") or "—",
        "Processed": (r.get("created_at") or "")[:19],
    })

df = pd.DataFrame(rows)

def _color(val):
    colors = {
        "PASSED": "background-color: #e8f5e9",
        "REVIEW_REQUIRED": "background-color: #fff3e0",
        "MISSING_DATA": "background-color: #fff3e0",
        "FAILED": "background-color: #ffebee",
        "DUPLICATE": "background-color: #f3e5f5",
        "VAT_MATCHED": "background-color: #e8f5e9",
        "VAT_MISMATCH": "background-color: #ffebee",
        "ERP_DRAFT_CREATED": "background-color: #e3f2fd",
        "WAITING_FOR_HUMAN_REVIEW": "background-color: #fff3e0",
    }
    return colors.get(val, "")

st.dataframe(
    df.style.map(_color, subset=["Validation", "Match", "VAT Status", "ERP Status"]),
    use_container_width=True, hide_index=True
)

st.download_button("Export CSV", df.to_csv(index=False), "processed_invoices.csv", "text/csv")

st.markdown("---")
st.subheader("Invoice Detail")
if filtered:
    inv_ids = [r["id"] for r in filtered]
    sel_id = st.selectbox("Select invoice ID to inspect", inv_ids)
    inv, payload = get_invoice_full(sel_id)
    if payload:
        tab1, tab2, tab3, tab4 = st.tabs(["  AI Extracted  ", "  Validation  ", "  OTM Payload  ", "  Raw OCR  "])
        with tab1:
            try:
                st.json(json.loads(payload.get("extracted_json") or "{}"))
            except Exception:
                st.code(payload.get("extracted_json") or "")
        with tab2:
            try:
                st.json(json.loads(payload.get("validation_json") or "{}"))
            except Exception:
                st.code(payload.get("validation_json") or "")
        with tab3:
            try:
                otm = json.loads(payload.get("otm_payload_json") or "{}")
                st.json(otm)
                st.download_button("Download OTM JSON", json.dumps(otm, indent=2),
                                   f"otm_{sel_id}.json", "application/json")
            except Exception:
                st.code(payload.get("otm_payload_json") or "")
        with tab4:
            st.code((payload.get("raw_text") or "")[:5000], language=None)

        st.markdown("**Processing Log**")
        logs = get_processing_logs(sel_id)
        if logs:
            log_rows = [{"Step": l.get("step", ""), "Status": l.get("status", ""),
                         "Message": l.get("message", ""), "Time": (l.get("created_at") or "")[:19]} for l in logs]
            st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
