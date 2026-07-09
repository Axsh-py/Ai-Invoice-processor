import json
import sqlite3
import os
import tempfile
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.config import DB_PATH
from src.theme import apply, page_header, section_label
from src.vendor_registry import (
    VENDOR_REGISTRY, CATEGORIES, CATEGORY_LABELS, CATEGORY_COLORS, get_vendor
)
from src.file_manager import save_original_and_copy, save_path_as_original_and_copy
from src.pipeline import process_invoice

st.set_page_config(
    page_title="Vendor Dashboard — OTM AI",
    page_icon="🏢",
    layout="wide",
)
apply()
init_db()

# ── Inject per-vendor section CSS ──────────────────────────────────────────────
st.markdown("""
<style>
.vendor-header {
    display:flex; align-items:center; gap:10px;
    padding:10px 14px; border-radius:6px 6px 0 0;
    margin-bottom:0;
}
.vendor-pill {
    font-size:10px; font-weight:700; letter-spacing:.1em;
    text-transform:uppercase; padding:2px 8px; border-radius:3px;
    color:#fff; flex-shrink:0;
}
.v-badge {
    font-size:11px; background:#F1F5FA; border:1px solid #C8D8EC;
    border-radius:3px; padding:1px 7px; font-family:monospace; color:#1A3A5C;
}
.otm-ready {
    font-size:10px; font-weight:700; letter-spacing:.08em;
    text-transform:uppercase; padding:2px 8px; border-radius:3px;
    background:#DCFCE7; color:#166534;
}
.otm-review {
    font-size:10px; font-weight:700; letter-spacing:.08em;
    text-transform:uppercase; padding:2px 8px; border-radius:3px;
    background:#FEF3C7; color:#92400E;
}
.inv-row {
    display:flex; align-items:center; gap:8px; padding:6px 10px;
    border-bottom:1px solid #EEF3FA; font-size:12.5px;
}
.inv-row:last-child { border-bottom:none; }
.inv-id { font-family:monospace; font-size:11px; color:#3A5A8A; min-width:60px; }
.inv-no { font-family:monospace; font-size:11.5px; font-weight:600; flex:1; color:#0C1B2E; }
.inv-amt { font-family:monospace; font-size:11px; color:#374151; min-width:100px; text-align:right; }
.inv-date { font-size:11px; color:#6B7280; min-width:88px; }
</style>
""", unsafe_allow_html=True)

page_header(
    "Vendor Dashboard",
    subtitle="Per-vendor invoice sections — upload raw invoices, bot identifies vendor, extracts data, produces OTM-ready output.",
)

# ── Sidebar: upload + processing controls ─────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="font-size:11px;font-weight:700;text-transform:uppercase;
            letter-spacing:.1em;color:#94A3B8;padding:8px 0 6px">
  Upload Raw Invoice
</div>""", unsafe_allow_html=True)

    ai_mode = st.selectbox(
        "AI Parser", ["mock", "openai"],
        help="openai uses GPT-4o-mini with vendor-specific prompts for best accuracy.",
        key="vd_ai_mode",
    )

    uploaded = st.file_uploader(
        "Drop vendor PDF here",
        type=["pdf"],
        label_visibility="collapsed",
        key="vd_uploader",
    )

    if uploaded:
        if st.button("Process & Classify", type="primary", use_container_width=True):
            with st.spinner("OCR → classify vendor → extract → OTM ready…"):
                record = save_original_and_copy(uploaded, source="vendor_dashboard")
                try:
                    invoice_id, raw_text, extracted, validation, otm_payload, _ = \
                        process_invoice(record, ai_mode=ai_mode)
                    st.session_state["vd_last_result"] = {
                        "invoice_id": invoice_id,
                        "vendor_id": extracted.get("vendor_id", "UNKNOWN"),
                        "vendor_name": extracted.get("vendor_name") or extracted.get("vendor_short_name", ""),
                        "extracted": extracted,
                        "validation": validation,
                        "otm_payload": otm_payload,
                        "raw_text": raw_text,
                    }
                    st.success(
                        f"Classified: **{extracted.get('vendor_id','?')}** "
                        f"(conf {extracted.get('vendor_confidence', 0)*100:.0f}%)"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Processing failed: {exc}")

    st.divider()

    # last processed result mini-panel
    if "vd_last_result" in st.session_state:
        r = st.session_state["vd_last_result"]
        v = get_vendor(r["vendor_id"]) or {}
        cat = v.get("category", "unknown")
        color = CATEGORY_COLORS.get(cat, "#888")
        st.markdown(f"""
<div style="background:#F8FAFB;border:1px solid #C8D8EC;border-left:4px solid {color};
     border-radius:4px;padding:10px 12px;font-size:12px">
  <div style="font-weight:700;color:#0C1B2E">{v.get('short_name', r['vendor_id'])}</div>
  <div style="color:#6B7280;margin:3px 0">{CATEGORY_LABELS.get(cat,cat)}</div>
  <div style="font-family:monospace;font-size:11px;color:#3A5A8A">
    Invoice #{r['invoice_id']} — {r['extracted'].get('invoice_number') or 'N/A'}
  </div>
  <div style="margin-top:6px;font-size:11px;color:#374151">
    Amount: <strong>
      {r['extracted'].get('currency','AED')}
      {r['extracted'].get('amount_due_with_vat') or r['extracted'].get('amount_due') or '—'}
    </strong>
  </div>
</div>""", unsafe_allow_html=True)

        erp = r["otm_payload"].get("erp_status", "")
        if erp == "ERP_DRAFT_CREATED":
            st.success("OTM Draft Created")
        else:
            st.warning("Pending Review")

        with st.expander("OTM JSON"):
            st.json(r["otm_payload"])


# ── Load all processed invoices grouped by vendor_id ──────────────────────────
def _load_invoices_by_vendor() -> dict:
    """Returns dict: vendor_id → list of invoice rows"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                i.id, i.erp_status, i.validation_status, i.created_at,
                e.vendor_id, e.vendor_confidence, e.vendor_category,
                e.invoice_number, e.vendor_name, e.currency,
                e.amount_due, e.vat_amount, e.amount_due_with_vat,
                e.charge_code, e.invoice_date,
                o.otm_invoice_id, o.draft_status
            FROM invoices i
            LEFT JOIN extracted_data e ON e.invoice_id = i.id
            LEFT JOIN otm_drafts o ON o.invoice_id = i.id
            ORDER BY i.id DESC
        """).fetchall()
        conn.close()

        grouped: dict = {}
        for row in rows:
            vid = row["vendor_id"] or "UNKNOWN"
            if vid not in grouped:
                grouped[vid] = []
            grouped[vid].append(dict(row))
        return grouped
    except Exception:
        return {}


invoices_by_vendor = _load_invoices_by_vendor()
total_invoices = sum(len(v) for v in invoices_by_vendor.values())

# ── Summary bar ────────────────────────────────────────────────────────────────
col_total, col_vendors, col_otm_ready, col_review = st.columns(4)
otm_ready_count = sum(
    1 for rows in invoices_by_vendor.values()
    for r in rows if r.get("erp_status") == "ERP_DRAFT_CREATED"
)
review_count = total_invoices - otm_ready_count

col_total.metric("Total Processed", total_invoices)
col_vendors.metric("Vendor Sections", len(invoices_by_vendor))
col_otm_ready.metric("OTM Draft Ready", otm_ready_count)
col_review.metric("Pending Review", review_count)

st.markdown("---")

# ── Per-category, per-vendor sections ─────────────────────────────────────────
for cat in CATEGORIES:
    cat_label = CATEGORY_LABELS[cat]
    cat_color = CATEGORY_COLORS[cat]
    vendors_in_cat = [v for v in VENDOR_REGISTRY.values() if v["category"] == cat]

    if not vendors_in_cat:
        continue

    section_label(cat_label.upper())

    cols = st.columns(2)
    col_idx = 0

    for vendor in vendors_in_cat:
        vid = vendor["vendor_id"]
        vname = vendor["short_name"]
        inv_rows = invoices_by_vendor.get(vid, [])
        inv_count = len(inv_rows)
        otm_ready = sum(1 for r in inv_rows if r.get("erp_status") == "ERP_DRAFT_CREATED")

        with cols[col_idx % 2]:
            # Vendor section card
            st.markdown(f"""
<div style="border:1px solid #C8D8EC;border-left:4px solid {cat_color};
     border-radius:6px;margin-bottom:16px;overflow:hidden">
  <div class="vendor-header" style="background:#F6F9FD;border-bottom:1px solid #C8D8EC">
    <span class="vendor-pill" style="background:{cat_color}">{cat_label}</span>
    <span style="font-weight:700;font-size:14px;color:#0C1B2E;flex:1">{vname}</span>
    <span class="v-badge">{vid}</span>
    {"<span class='otm-ready'>" + str(otm_ready) + " OTM Ready</span>" if otm_ready else ""}
    <span style="font-size:11px;color:#6B7280">{inv_count} invoice{"s" if inv_count != 1 else ""}</span>
  </div>""", unsafe_allow_html=True)

            if inv_count == 0:
                st.markdown("""
<div style="padding:14px 16px;font-size:12px;color:#9CA3AF;font-style:italic">
  No invoices processed yet for this vendor.
  Upload a raw invoice in the sidebar to get started.
</div>""", unsafe_allow_html=True)
            else:
                # Invoice rows
                rows_html = ""
                for row in inv_rows[:8]:
                    erp = row.get("erp_status", "")
                    badge = (
                        "<span class='otm-ready'>OTM READY</span>"
                        if erp == "ERP_DRAFT_CREATED"
                        else "<span class='otm-review'>REVIEW</span>"
                    )
                    inv_no = row.get("invoice_number") or "—"
                    amount = ""
                    if row.get("amount_due_with_vat"):
                        amount = f"{row.get('currency','AED')} {row['amount_due_with_vat']:,.2f}"
                    elif row.get("amount_due"):
                        amount = f"{row.get('currency','AED')} {row['amount_due']:,.2f}"
                    created = (row.get("created_at") or "")[:10]
                    rows_html += f"""
<div class="inv-row">
  <span class="inv-id">#{row['id']}</span>
  <span class="inv-no">{inv_no}</span>
  {badge}
  <span class="inv-amt">{amount}</span>
  <span class="inv-date">{created}</span>
</div>"""
                if len(inv_rows) > 8:
                    rows_html += f"""
<div style="padding:6px 10px;font-size:11px;color:#9CA3AF;text-align:center;
     border-top:1px solid #EEF3FA">
  +{len(inv_rows)-8} more invoices
</div>"""

                st.markdown(f"""
<div style="background:#fff;max-height:280px;overflow-y:auto">{rows_html}</div>""",
                    unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # OTM Payload viewer for most recent invoice of this vendor
            if inv_rows:
                with st.expander(f"Latest {vname} — OTM Payload", expanded=False):
                    latest = inv_rows[0]
                    inv_id = latest["id"]
                    try:
                        from src.config import PROCESSED_DIR
                        payload_path = PROCESSED_DIR / f"invoice_{inv_id}_otm_payload.json"
                        if payload_path.exists():
                            payload = json.loads(payload_path.read_text(encoding="utf-8"))
                            c1, c2 = st.columns(2)
                            with c1:
                                hdr = payload.get("otm_payload", {}).get("invoice_header", {})
                                st.markdown("**Invoice Header**")
                                st.json({
                                    "invoice_id":       hdr.get("invoice_id") or payload.get("otm_payload", {}).get("erp_invoice_id"),
                                    "invoice_number":   hdr.get("invoice_number"),
                                    "service_provider": hdr.get("service_provider_alias"),
                                    "currency":         hdr.get("currency"),
                                    "amount_due":       hdr.get("amount_due"),
                                    "vat_amount":       hdr.get("vat_amount"),
                                    "total_with_vat":   hdr.get("amount_due_with_vat"),
                                    "route":            hdr.get("route"),
                                    "shipment_id":      hdr.get("shipment_id"),
                                })
                            with c2:
                                st.markdown("**Extracted (Vendor-Specific)**")
                                ext = payload.get("extracted", {})
                                vsf = ext.get("vendor_specific_fields", {})
                                display = {
                                    "vendor_id":        ext.get("vendor_id"),
                                    "vendor_confidence":f"{(ext.get('vendor_confidence') or 0)*100:.0f}%",
                                    "charge_code":      ext.get("charge_code"),
                                    "invoice_category": ext.get("invoice_category"),
                                }
                                if vsf:
                                    display.update(vsf)
                                st.json(display)

                            li = payload.get("otm_payload", {}).get("line_items", [])
                            if li:
                                st.markdown("**Line Items**")
                                st.json(li)

                            st.download_button(
                                f"Download OTM JSON — Invoice #{inv_id}",
                                json.dumps(payload.get("otm_payload", {}), indent=2, default=str),
                                file_name=f"otm_{vid}_{inv_id}.json",
                                mime="application/json",
                                key=f"dl_{vid}_{inv_id}",
                            )
                        else:
                            st.info("Payload file not found. Re-process this invoice.")
                    except Exception as exc:
                        st.error(f"Could not load payload: {exc}")

        col_idx += 1

# ── Vendor identification guide (collapsible) ──────────────────────────────────
st.markdown("---")
with st.expander("Vendor Identification Rules (all vendors)", expanded=False):
    for vid, vendor in VENDOR_REGISTRY.items():
        cat = vendor.get("category", "unknown")
        color = CATEGORY_COLORS.get(cat, "#888")
        patterns = vendor.get("identification", {}).get("patterns", [])
        st.markdown(f"""
<div style="border-left:3px solid {color};padding:6px 12px;margin:6px 0">
  <strong>{vendor['name']}</strong>
  <span style="font-family:monospace;font-size:10px;color:#6B7280;margin-left:8px">{vid}</span>
  <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">
    {"".join(
        f'<code style="background:#F1F5FA;border:1px solid #C8D8EC;padding:1px 6px;border-radius:2px;font-size:10px">{p.get("value") or p.get("pattern","")}</code>'
        for p in patterns[:4]
    )}
  </div>
</div>""", unsafe_allow_html=True)
