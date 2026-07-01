import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db, get_kpis, list_invoices
from src.theme import apply, page_header, kpi_card, section_label, pipeline_step

st.set_page_config(
    page_title="OTM AI Invoice Preprocessor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply()
init_db()

page_header(
    title="Invoice Preprocessor",
    subtitle="Real-time view of invoice intake, enrichment, and OTM draft generation.",
    badges=["Python 3.11", "GPT-4o-mini", "Tesseract OCR v5", "Oracle OTM", "SQLite WAL"],
)

kpis = get_kpis()

# ── Row 1: core KPIs ──────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.markdown(kpi_card(kpis["total"], "Total Processed", "blue"), unsafe_allow_html=True)
c2.markdown(kpi_card(
    kpis["matched"] + kpis["matched_in_tolerance"], "Matched",
    "green", sub=f'{kpis["matched"]} exact · {kpis["matched_in_tolerance"]} tolerance'),
    unsafe_allow_html=True)
c3.markdown(kpi_card(kpis["review_required"], "Review Required", "amber"), unsafe_allow_html=True)
c4.markdown(kpi_card(kpis["duplicates"], "Duplicates Detected", "red"), unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

c5, c6, c7, c8 = st.columns(4)
c5.markdown(kpi_card(kpis["otm_drafts"], "OTM Drafts Created", "purple"), unsafe_allow_html=True)
c6.markdown(kpi_card(
    f"AED {kpis['total_amount']:,.0f}", "Total Amount", "teal"), unsafe_allow_html=True)
c7.markdown(kpi_card(f"{kpis['avg_confidence']}%", "Avg AI Confidence", "slate"),
            unsafe_allow_html=True)
match_rate = (
    round((kpis["matched"] + kpis["matched_in_tolerance"]) / kpis["total"] * 100, 1)
    if kpis["total"] else 0
)
c8.markdown(kpi_card(f"{match_rate}%", "Match Rate", "green"), unsafe_allow_html=True)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Recent Invoices + Status Distribution ─────────────────────────────────────
col_left, col_right = st.columns([3, 2], gap="medium")

with col_left:
    section_label("RECENT INVOICES")
    recent = list_invoices(limit=12)
    if recent:
        rows = []
        for r in recent:
            vs = r.get("validation_status") or ""
            rows.append({
                "ID":        r["id"],
                "Vendor":    (r.get("vendor_name") or "—")[:26],
                "Invoice #": r.get("invoice_number") or "—",
                "Charge":    r.get("charge_code") or "—",
                "Amount":    f"{r.get('amount_due') or 0:,.2f} {r.get('currency') or ''}",
                "Status":    vs,
                "Conf.":     f"{(r.get('confidence') or 0)*100:.0f}%",
            })
        df = pd.DataFrame(rows)

        def _status_color(val):
            m = {
                "PASSED":           "color:#15803D;font-weight:600",
                "REVIEW_REQUIRED":  "color:#A16207;font-weight:600",
                "MISSING_DATA":     "color:#1D4ED8;font-weight:600",
                "FAILED":           "color:#B91C1C;font-weight:600",
                "DUPLICATE":        "color:#6D28D9;font-weight:600",
            }
            return m.get(val, "color:#374151")

        st.dataframe(
            df.style.map(_status_color, subset=["Status"]),
            use_container_width=True, hide_index=True,
            column_config={
                "ID":     st.column_config.NumberColumn("ID", width="small"),
                "Conf.":  st.column_config.TextColumn("Conf.", width="small"),
                "Charge": st.column_config.TextColumn("Charge", width="small"),
            }
        )
    else:
        st.info("No invoices yet — upload a PDF or run Email Intake Simulation.")

with col_right:
    section_label("STATUS DISTRIBUTION")
    if recent:
        from collections import Counter
        all_inv = list_invoices(limit=500)
        counts = Counter(r.get("validation_status") or "UNKNOWN" for r in all_inv)
        _colors = {
            "PASSED":          "#059669",
            "REVIEW_REQUIRED": "#D97706",
            "MISSING_DATA":    "#2563EB",
            "FAILED":          "#DC2626",
            "DUPLICATE":       "#7C3AED",
            "UNKNOWN":         "#9CA3AF",
        }
        st.markdown('<div class="card">', unsafe_allow_html=True)
        total = sum(counts.values())
        for status, count in sorted(counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            color = _colors.get(status, "#9CA3AF")
            st.markdown(f"""
<div style="margin-bottom:11px">
  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
    <span style="font-size:12px;font-weight:600;color:#374151">{status}</span>
    <span style="font-family:'Courier New',monospace;font-size:11px;color:#9CA3AF">
      {count} &nbsp;{pct:.0f}%
    </span>
  </div>
  <div style="background:#F3F4F6;border-radius:3px;height:6px;overflow:hidden">
    <div style="width:{pct}%;height:100%;background:{color};border-radius:3px"></div>
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="card"><p style="color:#9CA3AF;margin:0;font-size:13px">No data yet.</p></div>',
                    unsafe_allow_html=True)

# ── Pipeline steps ────────────────────────────────────────────────────────────
section_label("PROCESSING PIPELINE")

steps = [
    ("01", "Input",     "PDF via upload or email inbox"),
    ("02", "OCR",       "Auto: digital text or Tesseract 300 DPI"),
    ("03", "AI Parse",  "GPT-4o-mini — 15+ structured fields"),
    ("04", "Match",     "5-layer vendor + scored shipment"),
    ("05", "Validate",  "GST/VAT · tolerance · duplicate"),
    ("06", "OTM Draft", "JSON payload for Oracle TMS"),
]

cols = st.columns(len(steps))
for col, (num, title, desc) in zip(cols, steps):
    col.markdown(pipeline_step(num, title, desc), unsafe_allow_html=True)
