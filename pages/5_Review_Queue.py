import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db, get_review_queue, get_invoice_full, update_otm_draft_status, save_manual_corrections
from src.theme import apply, page_header, section_label, status_badge, field_card

st.set_page_config(page_title="Review Queue — OTM AI", page_icon="🔍", layout="wide")
apply()
init_db()

page_header(
    title="Human Review Queue",
    subtitle="Invoices requiring human attention — mismatches, missing data, low confidence, or VAT errors.",
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

# ── Queue summary ─────────────────────────────────────────────────────────────
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
                 "ID":    st.column_config.NumberColumn("ID", width="small"),
                 "Dup?":  st.column_config.TextColumn("Dup?", width="small"),
                 "Conf.": st.column_config.TextColumn("Conf.", width="small"),
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

# ── Invoice detail card ───────────────────────────────────────────────────────
def _safe_json_list(val):
    try:
        r = json.loads(val or "[]")
        return r if isinstance(r, list) else []
    except Exception:
        return []

errors   = _safe_json_list(selected.get("errors"))
warnings = _safe_json_list(selected.get("warnings"))
missing  = _safe_json_list(selected.get("missing_fields"))

vs = selected.get("validation_status") or "UNKNOWN"
accent = (
    "#7C3AED" if selected.get("is_duplicate") else
    "#DC2626" if "FAIL" in vs else
    "#D97706"
)

st.markdown(f"""
<div class="ri {'ri-dup' if selected.get('is_duplicate') else ''}"
     style="border-left-color:{accent}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <div style="font-size:16px;font-weight:700;color:#111827">
        {selected.get('vendor_name') or '⚠ Vendor unknown'}
      </div>
      <div style="font-size:12px;color:#6B7280;margin-top:2px">
        Invoice #{selected.get('invoice_number') or '—'} &nbsp;·&nbsp;
        Charge: {selected.get('charge_code') or '—'} &nbsp;·&nbsp;
        {selected.get('amount_due') or 0:,.2f} {selected.get('currency') or ''}
      </div>
    </div>
    <div>{status_badge(vs)}</div>
  </div>
  <div style="display:flex;gap:20px;flex-wrap:wrap">
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">Match</div>
      <div style="font-size:12.5px;font-weight:600;color:#374151">{selected.get('match_status') or '—'}</div>
    </div>
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">VAT</div>
      <div style="font-size:12.5px;font-weight:600;color:#374151">{selected.get('vat_status') or '—'}</div>
    </div>
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">AI Confidence</div>
      <div style="font-size:12.5px;font-weight:600;color:#374151">{(selected.get('confidence') or 0)*100:.0f}%</div>
    </div>
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9CA3AF;font-weight:700">Duplicate</div>
      <div style="font-size:12.5px;font-weight:600;{'color:#7C3AED' if selected.get('is_duplicate') else 'color:#059669'}">
        {'Yes' if selected.get('is_duplicate') else 'No'}
      </div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

if errors:
    st.error("**Errors:** " + " · ".join(errors))
if warnings:
    st.warning("**Warnings:** " + " · ".join(warnings[:3]))
if missing:
    st.info("**AI-flagged missing fields:** " + ", ".join(missing))

# ── Detail tabs ───────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "  AI Extracted JSON  ",
    "  Validation Detail  ",
    "  OTM Draft Payload  ",
    "  Raw OCR Text  ",
])

with tab1:
    if payload:
        try:
            st.json(json.loads(payload.get("extracted_json") or "{}"))
        except Exception:
            st.code(payload.get("extracted_json") or "")

with tab2:
    if payload:
        try:
            val_data = json.loads(payload.get("validation_json") or "{}")
            c1, c2 = st.columns(2)
            with c1:
                val_summary = {
                    "Validation Status": val_data.get("validation_status"),
                    "Match Status":      val_data.get("match_status"),
                    "VAT Status":        val_data.get("vat_status"),
                    "Amount Difference": str(val_data.get("amount_difference") or "—"),
                    "Is Duplicate":      str(val_data.get("is_duplicate")),
                }
                st.markdown(field_card("Validation Summary", val_summary), unsafe_allow_html=True)
            with c2:
                if val_data.get("matched_shipment"):
                    sh = val_data["matched_shipment"]
                    sh_fields = {
                        "Shipment ID":      sh.get("shipment_id"),
                        "Expected Amount":  f"{sh.get('expected_amount')} {sh.get('currency')}",
                        "Tolerance":        f"±{sh.get('tolerance_amount')}",
                        "Route":            sh.get("route"),
                    }
                    st.markdown(field_card("Matched Shipment", sh_fields), unsafe_allow_html=True)
                else:
                    st.markdown('<div class="card"><p style="color:#9CA3AF;margin:0">No shipment matched.</p></div>',
                                unsafe_allow_html=True)
        except Exception:
            st.code(payload.get("validation_json") or "")

with tab3:
    if payload:
        try:
            st.json(json.loads(payload.get("otm_payload_json") or "{}"))
        except Exception:
            st.code(payload.get("otm_payload_json") or "")

with tab4:
    if payload:
        st.code((payload.get("raw_text") or "")[:5000], language=None)

# ── Correction form ───────────────────────────────────────────────────────────
section_label("CORRECT INVOICE FIELDS")
st.caption("Edit any field the AI got wrong. Corrected values are saved and used when you approve.")

try:
    ai_data = json.loads(payload.get("extracted_json") or "{}") if payload else {}
except Exception:
    ai_data = {}

with st.form(key=f"corrections_{sel_id}"):
    c1, c2, c3 = st.columns(3)
    with c1:
        cor_vendor   = st.text_input("Vendor Name",            value=ai_data.get("vendor_name") or "")
        cor_inv_no   = st.text_input("Invoice Number",         value=ai_data.get("invoice_number") or "")
        cor_inv_date = st.text_input("Invoice Date",           value=ai_data.get("invoice_date") or "")
    with c2:
        cor_charge   = st.text_input("Charge Code",            value=ai_data.get("charge_code") or "")
        cor_currency = st.text_input("Currency (ISO 3-letter)",value=ai_data.get("currency") or "AED")
        cor_shipment = st.text_input("Shipment ID",            value=ai_data.get("shipment_id") or "")
    with c3:
        cor_amount   = st.number_input("Amount Due (net)",     value=float(ai_data.get("amount_due") or 0), min_value=0.0, format="%.2f")
        cor_vat      = st.number_input("Tax / VAT Amount",     value=float(ai_data.get("vat_amount") or 0), min_value=0.0, format="%.2f")
        cor_total    = st.number_input("Total (amount + tax)", value=float(ai_data.get("amount_due_with_vat") or 0), min_value=0.0, format="%.2f")

    corrector = st.text_input("Your name / employee ID", value="reviewer_01", key=f"corrector_{sel_id}")
    save_btn = st.form_submit_button("Save Corrections", type="primary")

    if save_btn:
        corrections = {
            "vendor_name":        cor_vendor,
            "invoice_number":     cor_inv_no,
            "invoice_date":       cor_inv_date,
            "charge_code":        cor_charge.upper(),
            "currency":           cor_currency.upper(),
            "shipment_id":        cor_shipment,
            "amount_due":         cor_amount   if cor_amount > 0   else None,
            "vat_amount":         cor_vat      if cor_vat > 0      else None,
            "amount_due_with_vat":cor_total    if cor_total > 0    else None,
        }
        save_manual_corrections(sel_id, corrections, corrected_by=corrector)
        st.success(f"Corrections saved for Invoice #{sel_id}. Approve below to create OTM draft.")
        st.rerun()

# ── Actions ───────────────────────────────────────────────────────────────────
section_label("ACTIONS")

col_approve, col_reject, col_force = st.columns(3, gap="medium")

with col_approve:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""<div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:4px">
      Approve &amp; Insert into OTM</div>
<div style="font-size:12px;color:#6B7280;margin-bottom:12px">
  Creates OTM draft from corrected data. Use after saving corrections above.</div>""",
                unsafe_allow_html=True)
    approver = st.text_input("Your name / ID", value="reviewer_01", key=f"approver_{sel_id}")
    if st.button("Approve & Create OTM Draft", type="primary", key=f"approve_{sel_id}",
                 use_container_width=True):
        otm_to_download = None
        if payload:
            try:
                from src.otm_payload import build_otm_payload
                corrected_extracted  = json.loads(payload.get("extracted_json") or "{}")
                corrected_validation = json.loads(payload.get("validation_json") or "{}")
                otm_to_download = build_otm_payload(corrected_extracted, corrected_validation)
            except Exception:
                otm_to_download = json.loads(payload.get("otm_payload_json") or "{}")
        update_otm_draft_status(sel_id, "ERP_DRAFT_CREATED", approved_by=approver)
        st.success(f"Invoice #{sel_id} approved. OTM draft created.")
        if otm_to_download:
            st.download_button(
                "Download OTM JSON",
                json.dumps(otm_to_download, indent=2, default=str),
                f"otm_{sel_id}.json", "application/json",
                key=f"dl_otm_{sel_id}",
            )
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_reject:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""<div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:4px">
      Reject Invoice</div>
<div style="font-size:12px;color:#6B7280;margin-bottom:12px">
  Mark as rejected with a reason. Will not be inserted into OTM.</div>""",
                unsafe_allow_html=True)
    reject_reason = st.text_area("Rejection reason", key=f"reason_{sel_id}", height=68)
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
<div style="font-size:12px;color:#6B7280;margin-bottom:12px">
  Bypass all validation and force-create OTM draft. Use with caution.</div>""",
                unsafe_allow_html=True)
    st.markdown("<div style='height:37px'></div>", unsafe_allow_html=True)
    if st.button("Force Create OTM Draft", key=f"force_{sel_id}", use_container_width=True):
        update_otm_draft_status(sel_id, "ERP_DRAFT_CREATED_MANUAL", approved_by="manual_override")
        st.info(f"Manual OTM draft created for invoice #{sel_id}.")
        if payload:
            try:
                otm = json.loads(payload.get("otm_payload_json") or "{}")
                st.download_button("⬇ Download OTM JSON", json.dumps(otm, indent=2),
                                   f"otm_manual_{sel_id}.json", "application/json")
            except Exception:
                pass
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
