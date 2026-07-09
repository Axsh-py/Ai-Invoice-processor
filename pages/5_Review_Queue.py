import base64
import json
import os
import re

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import (
    init_db, get_review_queue, get_invoice_full,
    update_otm_draft_status, save_manual_corrections,
)
from src.theme import apply, page_header, section_label, status_badge, field_card
from src.ai_parser import smart_refill_missing_fields

st.set_page_config(page_title="Review Queue — OTM AI", page_icon="🔍", layout="wide")
apply()
init_db()

page_header(
    title="Human Review Queue",
    subtitle="Invoices needing attention — AI pre-fills what it can. Human corrects the rest.",
)

queue = get_review_queue()

if not queue:
    st.markdown("""
<div style="background:#D1FAE5;border:1px solid #A7F3D0;border-radius:12px;
     padding:20px 24px;display:flex;align-items:center;gap:14px">
  <span style="width:10px;height:10px;border-radius:50%;background:#059669;display:inline-block;flex-shrink:0"></span>
  <div>
    <div style="font-size:15px;font-weight:700;color:#065F46">Review queue is empty</div>
    <div style="font-size:13px;color:#047857;margin-top:2px">
      All invoices have been automatically processed and approved.
    </div>
  </div>
</div>""", unsafe_allow_html=True)
    st.stop()

# ── Queue metrics ─────────────────────────────────────────────────────────────
col_count, col_dup, col_miss = st.columns(3)
dups    = sum(1 for r in queue if r.get("is_duplicate"))
missing = sum(1 for r in queue if not r.get("invoice_number"))
col_count.metric("Invoices Pending", len(queue))
col_dup.metric("Duplicates",         dups)
col_miss.metric("Missing Invoice #", missing)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Queue table ───────────────────────────────────────────────────────────────
section_label("PENDING INVOICES")
rows = []
for r in queue:
    rows.append({
        "ID":         r["id"],
        "Vendor":     (r.get("vendor_name") or "Unknown")[:24],
        "Invoice #":  r.get("invoice_number") or "—",
        "Charge":     r.get("charge_code") or "—",
        "Amount":     f"{r.get('amount_due') or 0:,.2f} {r.get('currency') or ''}",
        "Validation": r.get("validation_status") or "—",
        "Match":      r.get("match_status") or "—",
        "VAT":        r.get("vat_status") or "—",
        "Dup?":       "Yes" if r.get("is_duplicate") else "No",
        "Conf.":      f"{(r.get('confidence') or 0)*100:.0f}%",
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
             column_config={
                 "ID":   st.column_config.NumberColumn("ID", width="small"),
                 "Dup?": st.column_config.TextColumn("Dup?", width="small"),
             })

# ── Invoice selector ──────────────────────────────────────────────────────────
section_label("SELECT INVOICE TO REVIEW")
inv_ids = [r["id"] for r in queue]
sel_id  = st.selectbox(
    "Invoice",
    inv_ids,
    format_func=lambda i: f"ID {i} — {next((r.get('vendor_name') or 'Unknown' for r in queue if r['id'] == i), '')}",
    label_visibility="collapsed",
)

selected = next((r for r in queue if r["id"] == sel_id), None)
if not selected:
    st.stop()

inv, payload = get_invoice_full(sel_id)

# ── Invoice status card ───────────────────────────────────────────────────────
def _safe_json_list(val):
    try:
        r = json.loads(val or "[]")
        return r if isinstance(r, list) else []
    except Exception:
        return []

errors   = _safe_json_list(selected.get("errors"))
warnings = _safe_json_list(selected.get("warnings"))
missing_flds = _safe_json_list(selected.get("missing_fields"))

vs = selected.get("validation_status") or "UNKNOWN"
accent = "#7C3AED" if selected.get("is_duplicate") else "#DC2626" if "FAIL" in vs else "#D97706"

st.markdown(f"""
<div class="ri" style="border-left-color:{accent}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:16px;font-weight:700;color:#111827">
        {selected.get('vendor_name') or '⚠ Vendor unknown'}
      </div>
      <div style="font-size:12px;color:#6B7280;margin-top:2px">
        Invoice #{selected.get('invoice_number') or '—'} &nbsp;·&nbsp;
        {selected.get('amount_due') or 0:,.2f} {selected.get('currency') or ''}
        &nbsp;·&nbsp; Charge: {selected.get('charge_code') or '—'}
      </div>
    </div>
    <div>{status_badge(vs)}</div>
  </div>
  <div style="display:flex;gap:20px;flex-wrap:wrap">
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">Match</div>
      <div style="font-size:12px;font-weight:600;color:#374151">{selected.get('match_status') or '—'}</div>
    </div>
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">VAT</div>
      <div style="font-size:12px;font-weight:600;color:#374151">{selected.get('vat_status') or '—'}</div>
    </div>
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">AI Confidence</div>
      <div style="font-size:12px;font-weight:600;color:#374151">{(selected.get('confidence') or 0)*100:.0f}%</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

if errors:
    st.error("**Errors:** " + " · ".join(errors))
if warnings:
    st.warning("**Warnings:** " + " · ".join(warnings[:3]))
if missing_flds:
    st.info(f"**AI-flagged missing fields:** {', '.join(missing_flds)}")

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── Load extracted data ───────────────────────────────────────────────────────
try:
    ai_data = json.loads(payload.get("extracted_json") or "{}") if payload else {}
except Exception:
    ai_data = {}

raw_ocr = (payload.get("raw_text") or "") if payload else ""

# ── Session state for auto-filled values ─────────────────────────────────────
state_key = f"form_{sel_id}"
if state_key not in st.session_state:
    st.session_state[state_key] = dict(ai_data)

form_data = st.session_state[state_key]

# ── Main layout: LEFT = Document viewer | RIGHT = Edit form ──────────────────
col_doc, col_form = st.columns([45, 55], gap="large")

# ════════════════════════════════════════════════════════════════════════
# LEFT PANEL — Source document
# ════════════════════════════════════════════════════════════════════════
with col_doc:
    st.markdown("""
<div style="font-size:11px;font-weight:700;text-transform:uppercase;
            letter-spacing:.1em;color:#6366F1;margin-bottom:8px">
  Source Document
</div>""", unsafe_allow_html=True)

    # ── PDF preview / download ─────────────────────────────────────────
    orig_path = selected.get("original_file_path") or selected.get("working_copy_path") or ""
    pdf_shown = False
    if orig_path and os.path.exists(orig_path) and orig_path.lower().endswith(".pdf"):
        try:
            with open(orig_path, "rb") as f:
                pdf_bytes = f.read()
            b64 = base64.b64encode(pdf_bytes).decode()
            st.markdown(
                f'<iframe src="data:application/pdf;base64,{b64}" '
                f'width="100%" height="480px" '
                f'style="border:1px solid #E5E7EB;border-radius:8px"></iframe>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "Download Original PDF",
                pdf_bytes,
                file_name=os.path.basename(orig_path),
                mime="application/pdf",
                use_container_width=True,
            )
            pdf_shown = True
        except Exception:
            pass

    if not pdf_shown:
        # Fallback: show OCR text in scrollable box with highlights
        st.markdown("""
<div style="font-size:12px;color:#6B7280;margin-bottom:6px">
  PDF not available locally — showing extracted text from invoice.
  Use this to verify AI-extracted fields.
</div>""", unsafe_allow_html=True)

        # Highlight key patterns in OCR text
        def _highlight_ocr(text: str) -> str:
            if not text:
                return "<em style='color:#9CA3AF'>No text extracted from PDF.</em>"
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # Highlight numbers / amounts
            escaped = re.sub(
                r"(\b[\d,]+\.?\d{0,2}\b)",
                r'<span style="background:#FEF3C7;color:#92400E;border-radius:2px;padding:0 2px">\1</span>',
                escaped,
            )
            # Highlight dates
            escaped = re.sub(
                r"(\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{4}[-/]\d{2}[-/]\d{2}\b)",
                r'<span style="background:#DBEAFE;color:#1E40AF;border-radius:2px;padding:0 2px">\1</span>',
                escaped,
            )
            return escaped

        ocr_html = _highlight_ocr(raw_ocr[:6000])
        st.markdown(f"""
<div style="background:#F8F9FA;border:1px solid #E5E7EB;border-radius:8px;
     padding:12px 14px;height:440px;overflow-y:auto;
     font-family:monospace;font-size:11.5px;line-height:1.7;color:#374151;
     white-space:pre-wrap;word-break:break-word">
{ocr_html}
</div>""", unsafe_allow_html=True)

    # ── Quick patterns found by regex ─────────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    refill_preview = smart_refill_missing_fields(raw_ocr, ai_data, vendor_id=ai_data.get("vendor_id", "UNKNOWN"))
    if refill_preview:
        st.markdown("""
<div style="font-size:11px;font-weight:700;text-transform:uppercase;
            letter-spacing:.1em;color:#059669;margin-bottom:6px">
  Patterns detected in document
</div>""", unsafe_allow_html=True)
        for k, v in refill_preview.items():
            current = ai_data.get(k)
            icon = "✓" if current else "→"
            clr = "#6B7280" if current else "#059669"
            st.markdown(
                f'<div style="font-size:12px;color:{clr};margin-bottom:2px">'
                f'<b>{icon} {k.replace("_"," ").title()}:</b> {v}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown('<div style="font-size:12px;color:#9CA3AF">No additional patterns detected.</div>',
                    unsafe_allow_html=True)

    # ── Raw OCR tab (always accessible) ───────────────────────────────
    with st.expander("Full Raw OCR Text"):
        st.code(raw_ocr[:8000] or "No OCR text.", language=None)

# ════════════════════════════════════════════════════════════════════════
# RIGHT PANEL — Review & Correct form
# ════════════════════════════════════════════════════════════════════════
with col_form:
    st.markdown("""
<div style="font-size:11px;font-weight:700;text-transform:uppercase;
            letter-spacing:.1em;color:#6366F1;margin-bottom:8px">
  Review &amp; Correct Fields
</div>""", unsafe_allow_html=True)

    # ── AI Auto-Fill button ────────────────────────────────────────────
    auto_filled_this_run = st.session_state.get(f"autofilled_{sel_id}", [])

    btn_col, info_col = st.columns([1, 2])
    with btn_col:
        if st.button("AI Auto-Fill Missing Fields", type="secondary",
                     use_container_width=True, key=f"autofill_{sel_id}"):
            refilled = smart_refill_missing_fields(raw_ocr, form_data,
                                                    vendor_id=form_data.get("vendor_id", "UNKNOWN"))
            if refilled:
                for k, v in refilled.items():
                    if v is not None and not form_data.get(k):
                        form_data[k] = v
                st.session_state[state_key] = form_data
                st.session_state[f"autofilled_{sel_id}"] = list(refilled.keys())
                st.rerun()
            else:
                st.toast("No additional fields could be auto-filled from the document text.")

    with info_col:
        if auto_filled_this_run:
            st.success(f"Auto-filled: {', '.join(auto_filled_this_run)}")
        else:
            st.caption("Click to let AI find missing fields from the invoice text.")

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Edit form ──────────────────────────────────────────────────────
    def _fval(key, default=""):
        v = form_data.get(key)
        if v is None:
            return default
        return v

    def _badge(key):
        auto = key in auto_filled_this_run
        orig = ai_data.get(key)
        if auto:
            return '<span style="background:#D1FAE5;color:#065F46;font-size:10px;padding:1px 6px;border-radius:4px;margin-left:4px">auto-filled</span>'
        if not orig:
            return '<span style="background:#FEF3C7;color:#92400E;font-size:10px;padding:1px 6px;border-radius:4px;margin-left:4px">missing</span>'
        return ""

    with st.form(key=f"corrections_{sel_id}"):
        # ── Identification ─────────────────────────────────────────────
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:6px">Identification {_badge("invoice_number")}</div>', unsafe_allow_html=True)
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            cor_vendor  = st.text_input("Vendor Name",    value=_fval("vendor_name"))
            cor_inv_no  = st.text_input("Invoice Number", value=_fval("invoice_number"))
        with r1c2:
            cor_inv_date = st.text_input("Invoice Date",  value=_fval("invoice_date"))
            cor_charge   = st.text_input("Charge Code",   value=_fval("charge_code"))

        st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

        # ── Amounts ────────────────────────────────────────────────────
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:6px">Amounts {_badge("amount_due")}</div>', unsafe_allow_html=True)
        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            cor_currency = st.text_input("Currency (ISO)", value=_fval("currency", "AED"))
            cor_amount   = st.number_input("Amount Due (net)",
                                           value=float(_fval("amount_due", 0) or 0),
                                           min_value=0.0, format="%.2f")
        with r2c2:
            cor_vat   = st.number_input("VAT / Tax",
                                        value=float(_fval("vat_amount", 0) or 0),
                                        min_value=0.0, format="%.2f")
            cor_total = st.number_input("Total (incl. tax)",
                                        value=float(_fval("amount_due_with_vat", 0) or 0),
                                        min_value=0.0, format="%.2f")
        with r2c3:
            cor_shipment = st.text_input("Shipment ID", value=_fval("shipment_id"))
            cor_mbl      = st.text_input("MBL / AWB No.", value=_fval("mbl_number") or _fval("awb_number"))

        st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

        # ── Additional fields ──────────────────────────────────────────
        with st.expander("More fields (vessel, ports, container, customer)"):
            mx1, mx2 = st.columns(2)
            with mx1:
                cor_vessel    = st.text_input("Vessel Name",      value=_fval("vessel_name"))
                cor_voyage    = st.text_input("Voyage Number",    value=_fval("voyage_number"))
                cor_container = st.text_input("Container Number", value=_fval("container_number"))
            with mx2:
                cor_origin    = st.text_input("Origin Port",      value=_fval("origin_port"))
                cor_dest      = st.text_input("Destination Port", value=_fval("destination_port"))
                cor_cust_no   = st.text_input("Customer Number",  value=_fval("customer_number"))

        corrector = st.text_input("Your name / employee ID", value="reviewer_01",
                                  key=f"corrector_{sel_id}")
        save_btn = st.form_submit_button("Save Corrections", type="primary",
                                         use_container_width=True)

        if save_btn:
            corrections = {
                "vendor_name":         cor_vendor,
                "invoice_number":      cor_inv_no,
                "invoice_date":        cor_inv_date,
                "charge_code":         cor_charge.upper() if cor_charge else "",
                "currency":            cor_currency.upper() if cor_currency else "AED",
                "shipment_id":         cor_shipment,
                "mbl_number":          cor_mbl,
                "amount_due":          cor_amount   if cor_amount > 0   else None,
                "vat_amount":          cor_vat      if cor_vat > 0      else None,
                "amount_due_with_vat": cor_total    if cor_total > 0    else None,
                "vessel_name":         cor_vessel,
                "voyage_number":       cor_voyage,
                "container_number":    cor_container,
                "origin_port":         cor_origin,
                "destination_port":    cor_dest,
                "customer_number":     cor_cust_no,
            }
            save_manual_corrections(sel_id, corrections, corrected_by=corrector)
            # Update session state so form reflects saved values
            for k, v in corrections.items():
                if v is not None and v != "":
                    form_data[k] = v
            st.session_state[state_key] = form_data
            st.success(f"Corrections saved for Invoice #{sel_id}. Now click Approve below.")
            st.rerun()

    # ── Validation / OTM payload tabs ─────────────────────────────────
    with st.expander("View Validation Detail & OTM Payload"):
        t1, t2 = st.tabs(["Validation", "OTM Payload"])
        with t1:
            if payload:
                try:
                    st.json(json.loads(payload.get("validation_json") or "{}"))
                except Exception:
                    st.code(payload.get("validation_json") or "")
        with t2:
            if payload:
                try:
                    st.json(json.loads(payload.get("otm_payload_json") or "{}"))
                except Exception:
                    st.code(payload.get("otm_payload_json") or "")

# ── Actions row ───────────────────────────────────────────────────────────────
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
section_label("ACTIONS")

col_approve, col_reject, col_force = st.columns(3, gap="medium")

with col_approve:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""<div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:4px">
      Approve &amp; Create OTM Draft</div>
<div style="font-size:12px;color:#6B7280;margin-bottom:10px">
  Save corrections first, then approve to push to OTM.</div>""", unsafe_allow_html=True)
    approver = st.text_input("Your name / ID", value="reviewer_01", key=f"approver_{sel_id}")
    if st.button("Approve & Create OTM Draft", type="primary", key=f"approve_{sel_id}",
                 use_container_width=True):
        otm_dl = None
        if payload:
            try:
                from src.otm_payload import build_otm_payload
                ex2 = json.loads(payload.get("extracted_json") or "{}")
                va2 = json.loads(payload.get("validation_json") or "{}")
                otm_dl = build_otm_payload(ex2, va2)
            except Exception:
                try:
                    otm_dl = json.loads(payload.get("otm_payload_json") or "{}")
                except Exception:
                    pass
        update_otm_draft_status(sel_id, "ERP_DRAFT_CREATED", approved_by=approver)
        st.success(f"Invoice #{sel_id} approved — OTM draft created.")
        if otm_dl:
            st.download_button("Download OTM JSON",
                               json.dumps(otm_dl, indent=2, default=str),
                               f"otm_{sel_id}.json", "application/json",
                               key=f"dl_otm_{sel_id}")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_reject:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""<div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:4px">
      Reject Invoice</div>
<div style="font-size:12px;color:#6B7280;margin-bottom:10px">
  Mark as rejected with a reason.</div>""", unsafe_allow_html=True)
    reject_reason = st.text_area("Rejection reason", key=f"reason_{sel_id}", height=60)
    if st.button("Reject Invoice", type="secondary", key=f"reject_{sel_id}",
                 use_container_width=True):
        update_otm_draft_status(sel_id, "REJECTED", rejected_reason=reject_reason)
        st.error(f"Invoice #{sel_id} rejected.")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_force:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""<div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:4px">
      Force Override</div>
<div style="font-size:12px;color:#6B7280;margin-bottom:10px">
  Bypass validation and force-create OTM draft. Use with caution.</div>""",
                unsafe_allow_html=True)
    st.markdown("<div style='height:33px'></div>", unsafe_allow_html=True)
    if st.button("Force Create OTM Draft", key=f"force_{sel_id}", use_container_width=True):
        update_otm_draft_status(sel_id, "ERP_DRAFT_CREATED_MANUAL",
                                approved_by="manual_override")
        st.info(f"Manual OTM draft created for invoice #{sel_id}.")
        if payload:
            try:
                otm = json.loads(payload.get("otm_payload_json") or "{}")
                st.download_button("Download OTM JSON", json.dumps(otm, indent=2),
                                   f"otm_manual_{sel_id}.json", "application/json",
                                   key=f"dl_force_{sel_id}")
            except Exception:
                pass
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
