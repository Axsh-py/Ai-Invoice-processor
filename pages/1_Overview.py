from collections import Counter
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db, get_kpis, list_invoices, get_processing_logs
from src.theme import apply, page_header, section_label

st.set_page_config(page_title="Overview — OTM AI", page_icon="📊", layout="wide")
apply()
init_db()

page_header(
    title="Pipeline Overview",
    subtitle="KPIs, validation trends, charge code distribution, and processing logs.",
)

kpis = get_kpis()
invoices = list_invoices(limit=500)

# ── KPI row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Processed",         kpis["total"])
c2.metric("OTM Drafts Auto-Created", kpis["otm_drafts"])
c3.metric("Review Required",         kpis["review_required"])
c4.metric("Duplicates Detected",     kpis["duplicates"])
c5.metric("Avg AI Confidence",       f"{kpis['avg_confidence']}%")

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

c6, c7, c8 = st.columns(3)
c6.metric("Matched (exact)",        kpis["matched"])
c7.metric("Matched in Tolerance",   kpis["matched_in_tolerance"])
c8.metric("Total Amount",           f"AED {kpis['total_amount']:,.2f}")

# ── Charts ────────────────────────────────────────────────────────────────────
left, right = st.columns(2, gap="medium")

with left:
    section_label("VALIDATION STATUS DISTRIBUTION")
    if invoices:
        statuses = [r.get("validation_status") or "UNKNOWN" for r in invoices]
        df = pd.DataFrame.from_dict(Counter(statuses), orient="index", columns=["Count"])
        df = df.sort_values("Count", ascending=False)
        st.bar_chart(df, color="#4F46E5")
    else:
        st.info("No data yet.")

with right:
    section_label("CHARGE CODE DISTRIBUTION")
    if invoices:
        codes = [r.get("charge_code") or "UNKNOWN" for r in invoices]
        df = pd.DataFrame.from_dict(Counter(codes), orient="index", columns=["Count"])
        df = df.sort_values("Count", ascending=False)
        st.bar_chart(df, color="#059669")
    else:
        st.info("No data yet.")

left2, right2 = st.columns(2, gap="medium")

with left2:
    section_label("MATCH STATUS SUMMARY")
    if invoices:
        match_statuses = [r.get("match_status") or "UNKNOWN" for r in invoices]
        df = pd.DataFrame.from_dict(Counter(match_statuses), orient="index", columns=["Count"])
        st.bar_chart(df, color="#D97706")
    else:
        st.info("No data yet.")

with right2:
    section_label("VAT STATUS SUMMARY")
    if invoices:
        vat_statuses = [r.get("vat_status") or "VAT_NOT_FOUND" for r in invoices]
        df = pd.DataFrame.from_dict(Counter(vat_statuses), orient="index", columns=["Count"])
        st.bar_chart(df, color="#0891B2")
    else:
        st.info("No data yet.")

# ── Amount chart ──────────────────────────────────────────────────────────────
section_label("AMOUNT BY INVOICE (TOP 20)")
if invoices:
    amt_data = [
        {
            "Invoice #": r.get("invoice_number") or f"ID-{r['id']}",
            "Amount Due": float(r.get("amount_due") or 0),
        }
        for r in invoices[:20]
        if (r.get("amount_due") or 0) > 0
    ]
    if amt_data:
        st.bar_chart(pd.DataFrame(amt_data).set_index("Invoice #")["Amount Due"],
                     color="#7C3AED")

# ── Recent logs ───────────────────────────────────────────────────────────────
section_label("RECENT PROCESSING LOGS")
if invoices:
    inv_ids = [r["id"] for r in invoices[:5]]
    all_logs = []
    for iid in inv_ids:
        for log in get_processing_logs(iid):
            all_logs.append({
                "Invoice ID": log.get("invoice_id"),
                "Step":       log.get("step"),
                "Status":     log.get("status"),
                "Message":    (log.get("message") or "")[:80],
                "Time":       (log.get("created_at") or "")[:19],
            })
    if all_logs:
        st.dataframe(pd.DataFrame(all_logs), use_container_width=True, hide_index=True)
    else:
        st.info("No logs found.")
else:
    st.info("No invoices processed yet.")
