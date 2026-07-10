import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db, get_otm_drafts, get_invoice_full, update_otm_draft_status
from src.theme import apply, page_header, section_label, status_badge

st.set_page_config(page_title="OTM Draft Viewer — OTM AI", page_icon="📑", layout="wide")
apply()
init_db()

page_header("OTM Draft Viewer",
            subtitle="Review auto-generated draft payloads for Oracle Transportation Management.")

drafts = get_otm_drafts()
if not drafts:
    st.info("No OTM drafts yet. Process invoices first.")
    st.stop()

with st.sidebar:
    st.header("Filter Drafts")
    statuses = ["All"] + sorted({d.get("draft_status") or "PENDING" for d in drafts})
    sel_status = st.selectbox("Draft Status", statuses)

filtered = drafts
if sel_status != "All":
    filtered = [d for d in drafts if d.get("draft_status") == sel_status]

if not filtered:
    st.info(f"No drafts with status **{sel_status}**. Change the filter to see others.")
    st.stop()

st.write(f"Showing **{len(filtered)}** drafts")

rows = []
for d in filtered:
    rows.append({
        "Invoice ID": d.get("invoice_id"),
        "OTM Invoice ID": d.get("otm_invoice_id") or "—",
        "Vendor": (d.get("vendor_name") or "")[:25],
        "Invoice #": d.get("invoice_number") or "—",
        "Amount (AED)": f"{d.get('amount_due') or 0:,.2f}",
        "Total w/VAT": f"{d.get('amount_due_with_vat') or 0:,.2f}",
        "Draft Status": d.get("draft_status") or "—",
        "Created": (d.get("created_at") or "")[:19],
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("OTM Invoice Screen")

draft_ids = [d.get("invoice_id") for d in filtered]
sel_inv_id = st.selectbox("Select invoice to view OTM draft", draft_ids,
    format_func=lambda i: f"Inv ID {i} — {next((d.get('invoice_number') or 'No#' for d in filtered if d.get('invoice_id') == i), '')}")

sel_draft = next((d for d in filtered if d.get("invoice_id") == sel_inv_id), None)
inv, payload = get_invoice_full(sel_inv_id)

if not payload:
    st.warning("No payload found for this invoice.")
    st.stop()

try:
    otm = json.loads(payload.get("otm_payload_json") or "{}")
except Exception:
    st.error("Could not parse OTM payload JSON.")
    st.stop()

header = otm.get("invoice_header", {})
line_items = otm.get("line_items", [])
summary = otm.get("invoice_summary", {})
human_review = otm.get("human_review", {})

status_badges = {
    "PASSED": '<span class="badge-passed">PASSED</span>',
    "REVIEW_REQUIRED": '<span class="badge-review">REVIEW REQUIRED</span>',
    "DUPLICATE": '<span class="badge-dup">DUPLICATE</span>',
}
v_status = inv.get("validation_status", "UNKNOWN") if inv else "UNKNOWN"
badge = status_badges.get(v_status, f'<span class="badge-review">{v_status}</span>')
st.markdown(f"**Preprocess Status:** {badge}", unsafe_allow_html=True)

st.markdown('<div class="otm-section"><div class="otm-header-title">Invoice Header</div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    st.text_input("Invoice ID (OTM)", value=header.get("invoice_id") or "", disabled=True, key="h_id")
    st.text_input("Invoice Number", value=header.get("invoice_number") or "", disabled=True, key="h_num")
    st.text_input("Financial Consolidation Type", value=header.get("financial_consolidation_type") or "STANDARD", disabled=True)
    st.text_input("Invoice Bill Rule ID", value=header.get("invoice_bill_rule_id") or "", disabled=True)
with col2:
    st.text_input("Service Provider ID", value=header.get("service_provider_id") or "", disabled=True)
    st.text_input("Service Provider Alias", value=header.get("service_provider_alias") or "", disabled=True)
    st.text_input("Invoice Source", value=header.get("invoice_source") or "AI_PREPROCESSOR", disabled=True)
    st.text_input("Payment Method", value=header.get("payment_method") or "", disabled=True)
with col3:
    st.text_input("Invoice Date", value=header.get("invoice_date") or "", disabled=True)
    st.text_input("Date Received", value=header.get("date_received") or "", disabled=True)
    st.text_input("Currency", value=header.get("currency") or "AED", disabled=True)
    st.text_input("Route", value=header.get("route") or "", disabled=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="otm-section"><div class="otm-header-title">Financial Summary</div>', unsafe_allow_html=True)
fc1, fc2, fc3 = st.columns(3)
fc1.number_input("Amount Due", value=float(header.get("amount_due") or 0), disabled=True, format="%.2f")
fc2.number_input("VAT Amount", value=float(header.get("vat_amount") or 0), disabled=True, format="%.2f")
fc3.number_input("Amount Due with VAT", value=float(header.get("amount_due_with_vat") or 0), disabled=True, format="%.2f")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="otm-section"><div class="otm-header-title">Line Items</div>', unsafe_allow_html=True)
if line_items:
    st.dataframe(pd.DataFrame(line_items), use_container_width=True, hide_index=True)
else:
    st.info("No line items found.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="otm-section"><div class="otm-header-title">Invoice Summary</div>', unsafe_allow_html=True)
sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric("Validation Status", summary.get("validation_status") or v_status)
sc2.metric("Match Status", summary.get("match_status") or "—")
sc3.metric("VAT Status", summary.get("vat_status") or "—")
sc4.metric("AI Confidence", f"{(summary.get('ai_confidence') or 0)*100:.0f}%")
st.markdown('</div>', unsafe_allow_html=True)

if human_review.get("required"):
    with st.expander("Human Review Details", expanded=True):
        reasons = human_review.get("reason", [])
        for r in reasons:
            st.warning(r)

st.markdown("---")
st.subheader("Actions")
action_col1, action_col2, action_col3, action_col4 = st.columns(4)

with action_col1:
    if st.button("Create Mock OTM Draft", type="primary", key=f"create_{sel_inv_id}"):
        update_otm_draft_status(sel_inv_id, "ERP_DRAFT_CREATED", approved_by="viewer_action")
        st.success(f"OTM Draft marked as created for invoice {sel_inv_id}.")
        st.rerun()

with action_col2:
    st.download_button(
        "Download OTM Payload JSON",
        json.dumps(otm, indent=2, default=str),
        file_name=f"otm_payload_{sel_inv_id}.json",
        mime="application/json",
        key=f"dl_{sel_inv_id}",
    )

with action_col3:
    if st.button("Mark as Finished", key=f"finish_{sel_inv_id}"):
        update_otm_draft_status(sel_inv_id, "FINISHED", approved_by="viewer_action")
        st.success(f"Invoice {sel_inv_id} marked as finished.")
        st.rerun()

with action_col4:
    if st.button("Back to Review Queue", key=f"back_{sel_inv_id}"):
        update_otm_draft_status(sel_inv_id, "WAITING_FOR_HUMAN_REVIEW")
        st.info(f"Invoice {sel_inv_id} sent back to review queue.")
        st.rerun()

with st.expander("Raw OTM Payload JSON"):
    st.json(otm)
