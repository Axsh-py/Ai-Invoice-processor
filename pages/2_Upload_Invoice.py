import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.file_manager import save_original_and_copy, save_path_as_original_and_copy
from src.pipeline import process_invoice
from src.config import SAMPLE_INVOICES_DIR
from src.theme import apply, page_header, result_banner, field_card, section_label, status_badge

st.set_page_config(page_title="Upload Invoice — OTM AI", page_icon="📤", layout="wide")
apply()
init_db()

page_header(
    title="Upload Invoice",
    subtitle="Upload a vendor PDF invoice or pick a sample. Original is stored immutably.",
)

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="padding:12px 4px 8px">
  <div style="font-size:11px;font-weight:700;text-transform:uppercase;
              letter-spacing:.1em;color:#94A3B8;margin-bottom:10px">
    Processing Controls
  </div>
</div>""", unsafe_allow_html=True)

    _has_key = bool(os.environ.get("OPENAI_API_KEY"))
    _default_idx = 1 if _has_key else 0
    ai_mode = st.selectbox(
        "AI Parser Mode", ["mock", "openai"],
        index=_default_idx,
        help="'mock' uses fast regex (no API key needed). 'openai' uses GPT-4o-mini for higher accuracy."
    )
    if ai_mode == "openai" and not _has_key:
        st.warning("OpenAI API key not found. Add it to Streamlit Cloud Secrets (Settings → Secrets). Falling back to mock.", icon="⚠️")

    st.divider()
    from src.ocr import tesseract_available
    if tesseract_available():
        st.success("Tesseract OCR ready")
    else:
        st.info("Digital PDF extraction active")

    st.markdown("""
<div style="background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);
     border-radius:8px;padding:10px 12px;margin-top:8px">
  <div style="font-size:11px;color:#A5B4FC;font-weight:600;margin-bottom:4px">Safety</div>
  <div style="font-size:11.5px;color:#9CA3AF;line-height:1.5">
    Original invoice is never modified. OCR and AI processing run only on the working copy.
  </div>
</div>""", unsafe_allow_html=True)


def _show_result(invoice_id, raw_text, extracted, validation, otm_payload):
    v_status  = validation.get("validation_status", "UNKNOWN")
    erp_id    = otm_payload.get("otm_document_id", "")
    erp_status = otm_payload.get("erp_status", "")

    result_banner(v_status, invoice_id,
                  erp_id if erp_status == "ERP_DRAFT_CREATED" else "")

    # ── 3-column detail cards ──────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        fields = {
            "Vendor Name":        extracted.get("vendor_name"),
            "Invoice Number":     extracted.get("invoice_number"),
            "Invoice Date":       extracted.get("invoice_date"),
            "Charge Code":        extracted.get("charge_code"),
            "Currency":           extracted.get("currency"),
            "Amount Due":         f"{extracted.get('amount_due') or 0:,.2f}" if extracted.get("amount_due") else None,
            "VAT Amount":         extracted.get("vat_amount"),
            "Total w/ VAT":       extracted.get("amount_due_with_vat"),
            "MBL Number":         extracted.get("mbl_number"),
            "Customer Number":    extracted.get("customer_number"),
            "Tax Type":           extracted.get("tax_type"),
            "Shipment ID":        extracted.get("shipment_id"),
            "Confidence":         f"{(extracted.get('confidence_score') or 0)*100:.0f}%"
                                  if extracted.get("confidence_score") else None,
        }
        st.markdown(field_card("AI Extracted Data", fields), unsafe_allow_html=True)

    with c2:
        val_fields = {
            "Validation Status":  validation.get("validation_status"),
            "Match Status":       validation.get("match_status"),
            "VAT Status":         validation.get("vat_status"),
            "Amount Difference":  str(validation.get("amount_difference") or "—"),
            "Is Duplicate":       str(validation.get("is_duplicate") or False),
        }
        st.markdown(field_card("Validation Result", val_fields), unsafe_allow_html=True)
        for err in (validation.get("errors") or []):
            st.error(err)
        for warn in (validation.get("warnings") or [])[:3]:
            st.warning(warn)

    with c3:
        header = otm_payload.get("invoice_header", {})
        otm_fields = {
            "OTM Document ID":   otm_payload.get("otm_document_id"),
            "Service Provider":  header.get("service_provider_gid"),
            "Consolidation":     header.get("financial_consolidation_type"),
            "Bill Rule":         header.get("invoice_bill_rule_id"),
            "Route":             header.get("route"),
            "ERP Status":        otm_payload.get("erp_status"),
        }
        st.markdown(field_card("OTM Payload", otm_fields), unsafe_allow_html=True)
        st.download_button(
            "Download OTM JSON",
            json.dumps(otm_payload, indent=2, default=str),
            file_name=f"otm_{invoice_id}.json",
            mime="application/json",
        )

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    with st.expander("Raw OCR Text"):
        st.code(raw_text[:4000], language=None)

    with st.expander("Full AI Extracted JSON"):
        st.json(extracted)

    with st.expander("Full OTM Payload JSON"):
        st.json(otm_payload)


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_upload, tab_sample = st.tabs(["  Upload PDF  ", "  Sample Invoice  "])

with tab_upload:
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop a vendor invoice PDF here, or click to browse",
        type=["pdf"], label_visibility="visible"
    )
    if uploaded:
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            st.markdown(f"""
<div style="background:#F0FDF4;border:1px solid #A7F3D0;border-radius:8px;padding:10px 14px;
     display:flex;align-items:center;gap:10px">
  <span style="width:8px;height:8px;border-radius:2px;background:#059669;display:inline-block;flex-shrink:0;margin-top:3px"></span>
  <div>
    <div style="font-size:13px;font-weight:600;color:#065F46">{uploaded.name}</div>
    <div style="font-size:11.5px;color:#6B7280">{uploaded.size:,} bytes</div>
  </div>
</div>""", unsafe_allow_html=True)
        with col_btn:
            process = st.button("Process Invoice", type="primary", key="btn_upload",
                                use_container_width=True)
        if process:
            with st.spinner("Running OCR → AI parsing → matching → validation → OTM draft…"):
                record = save_original_and_copy(uploaded, source="manual_upload")
                invoice_id, raw_text, extracted, validation, otm_payload, _ = \
                    process_invoice(record, ai_mode=ai_mode)
            _show_result(invoice_id, raw_text, extracted, validation, otm_payload)

with tab_sample:
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    sample_files = sorted(SAMPLE_INVOICES_DIR.glob("*.pdf"))
    if not sample_files:
        st.warning("No sample invoices found. Run `python generate_samples.py` first.")
    else:
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            selected = st.selectbox(
                "Select sample invoice", sample_files,
                format_func=lambda p: p.name,
                label_visibility="collapsed",
            )
        with col_btn:
            process_s = st.button("Process Sample", type="primary", key="btn_sample",
                                  use_container_width=True)
        if selected and process_s:
            with st.spinner("Processing sample invoice…"):
                record = save_path_as_original_and_copy(str(selected), source="sample_email_pdf")
                invoice_id, raw_text, extracted, validation, otm_payload, _ = \
                    process_invoice(record, ai_mode=ai_mode)
            _show_result(invoice_id, raw_text, extracted, validation, otm_payload)
