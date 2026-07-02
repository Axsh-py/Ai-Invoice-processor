"""
OTM AI Invoice Preprocessor — Design System v3
"""
import streamlit as st

_CSS = """
<style>
/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbar"] {
    display: none !important; visibility: hidden !important;
}
[data-testid="stHeader"] { background: transparent !important; height: 0 !important; }

/* ── App background ── */
.stApp, [data-testid="stAppViewContainer"], .main {
    background: #F0F4F8 !important;
}
.main .block-container {
    padding: 0 2rem 2rem !important;
    max-width: 1380px !important;
}

/* ── Typography ── */
h1 { font-size: 20px !important; font-weight: 700 !important; color: #111827 !important; letter-spacing: -.02em !important; line-height: 1.2 !important; }
h2 { font-size: 15px !important; font-weight: 600 !important; color: #1F2937 !important; }
h3 { font-size: 13px !important; font-weight: 600 !important; color: #374151 !important; }
p, .stMarkdown p { font-size: 13.5px !important; color: #4B5563 !important; line-height: 1.6 !important; }

/* ══════════════════════════════════════════════════════════════════════════════
   SIDEBAR — full custom styling
   Brand injected via ::before so it appears ABOVE the page nav
══════════════════════════════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: #0E1117 !important;
    border-right: 1px solid #1C2333 !important;
    box-shadow: 2px 0 12px rgba(0,0,0,.25) !important;
}

/* Brand block above nav — pure CSS, no Python needed */
[data-testid="stSidebarNav"] {
    padding-top: 0 !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stSidebarNav"]::before {
    content: 'OTM AI';
    display: block;
    font-size: 15px;
    font-weight: 800;
    color: #F1F5F9;
    letter-spacing: -.02em;
    padding: 22px 16px 2px;
}
[data-testid="stSidebarNav"]::after {
    content: 'Invoice Preprocessor';
    display: block;
    font-family: 'Courier New', monospace;
    font-size: 10px;
    color: #3D4F6A;
    letter-spacing: .04em;
    padding: 0 16px 16px;
    border-bottom: 1px solid #1C2333;
    margin-bottom: 6px;
}

/* Nav links — Streamlit 1.58+ uses stSidebarNavLink */
[data-testid="stSidebarNav"] > ul {
    padding: 4px 8px !important;
    list-style: none !important;
}
[data-testid="stSidebarNav"] > ul li { margin-bottom: 1px !important; }

/* All nav link selectors — cover all Streamlit versions */
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p {
    color: #CBD5E1 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    text-decoration: none !important;
}
[data-testid="stSidebarNav"] a {
    display: flex !important;
    align-items: center !important;
    border-radius: 6px !important;
    padding: 8px 10px !important;
    transition: background .15s, color .15s !important;
    position: relative !important;
}
/* Icon dot before each nav link */
[data-testid="stSidebarNav"] a::before {
    content: '';
    display: inline-block;
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #4B6078;
    margin-right: 10px;
    flex-shrink: 0;
    transition: background .15s, transform .15s;
}
[data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebarNav"] a:hover [data-testid="stSidebarNavLink"],
[data-testid="stSidebarNav"] a:hover [data-testid="stSidebarNavLink"] span {
    background: rgba(99,102,241,.12) !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebarNav"] a:hover::before { background: #818CF8; }

[data-testid="stSidebarNav"] [aria-selected="true"] a,
[data-testid="stSidebarNav"] li[aria-selected="true"] a {
    background: rgba(99,102,241,.18) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}
[data-testid="stSidebarNav"] [aria-selected="true"] [data-testid="stSidebarNavLink"],
[data-testid="stSidebarNav"] [aria-selected="true"] [data-testid="stSidebarNavLink"] span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}
[data-testid="stSidebarNav"] [aria-selected="true"] a::before,
[data-testid="stSidebarNav"] li[aria-selected="true"] a::before {
    background: #818CF8;
    transform: scale(1.3);
}
[data-testid="stSidebarNav"] [aria-selected="true"] a {
    border-left: 2px solid #6366F1 !important;
    padding-left: 8px !important;
}

/* Sidebar ALL text — comprehensive white override */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
    color: #E2E8F0 !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: .08em !important;
}
section[data-testid="stSidebar"] p { color: #CBD5E1 !important; font-size: 12.5px !important; }
section[data-testid="stSidebar"] label { color: #CBD5E1 !important; font-size: 12.5px !important; }
section[data-testid="stSidebar"] .stMarkdown p { color: #94A3B8 !important; }
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] [data-testid="stRadio"] label { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] [data-testid="stSlider"] label { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] label { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] hr { border-color: #1C2333 !important; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background: #161B27 !important; border-color: #2A3A52 !important; color: #E2E8F0 !important;
}
/* Slider track and thumb */
section[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stThumbValue"],
section[data-testid="stSidebar"] [data-testid="stSlider"] div { color: #CBD5E1 !important; }

/* ── Metrics ────────────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: white !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    padding: 16px 18px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.04) !important;
    transition: box-shadow .2s !important;
}
[data-testid="metric-container"]:hover { box-shadow: 0 4px 12px rgba(0,0,0,.08) !important; }
[data-testid="stMetricLabel"] > div {
    font-size: 10px !important; text-transform: uppercase !important;
    letter-spacing: .1em !important; color: #9CA3AF !important; font-weight: 700 !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 26px !important; font-weight: 800 !important;
    color: #111827 !important; letter-spacing: -.025em !important;
    font-variant-numeric: tabular-nums !important;
}
[data-testid="stMetricDelta"] > div { font-size: 12px !important; }

/* ── DataFrames ────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 8px !important; border: 1px solid #E5E7EB !important;
    overflow: hidden !important; box-shadow: 0 1px 2px rgba(0,0,0,.03) !important;
}

/* ── Buttons ────────────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 7px !important; font-weight: 600 !important;
    font-size: 13px !important; padding: 7px 18px !important;
    letter-spacing: .01em !important; transition: all .15s ease !important;
}
.stButton > button[kind="primary"] {
    background: #2563EB !important; border: none !important; color: white !important;
    box-shadow: 0 1px 3px rgba(37,99,235,.3) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1D4ED8 !important; transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(37,99,235,.3) !important;
}
.stButton > button[kind="secondary"] {
    background: white !important; border: 1px solid #D1D5DB !important; color: #374151 !important;
}
.stButton > button[kind="secondary"]:hover { background: #F9FAFB !important; border-color: #9CA3AF !important; }

/* ── Inputs ─────────────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] > div > div > input,
[data-testid="stNumberInput"] > div > div > input,
[data-testid="stNumberInput"] input,
[data-testid="stNumberInput"] > div,
[data-testid="stNumberInput"] > div > div {
    border-radius: 7px !important; border-color: #D1D5DB !important;
    background: white !important; font-size: 13.5px !important; color: #111827 !important;
}
[data-testid="stTextInput"] > div > div > input:focus,
[data-testid="stNumberInput"] > div > div > input:focus {
    border-color: #2563EB !important; box-shadow: 0 0 0 3px rgba(37,99,235,.12) !important;
}
[data-testid="stSelectbox"] > div > div {
    border-radius: 7px !important; border-color: #D1D5DB !important;
    background: white !important; font-size: 13.5px !important;
}
[data-testid="stTextArea"] > div > textarea {
    border-radius: 7px !important; border-color: #D1D5DB !important; font-size: 13.5px !important;
}
[data-testid="stTextArea"] > div > textarea:focus {
    border-color: #2563EB !important; box-shadow: 0 0 0 3px rgba(37,99,235,.12) !important;
}

/* ── File uploader ──────────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] > section {
    background: white !important; border: 2px dashed #CBD5E1 !important;
    border-radius: 10px !important; padding: 24px !important; transition: all .2s !important;
}
[data-testid="stFileUploader"] > section:hover {
    border-color: #2563EB !important; background: #F8FBFF !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #E5E7EB !important; }
[data-testid="stTabs"] button[role="tab"] {
    font-size: 13px !important; font-weight: 500 !important;
    color: #6B7280 !important; padding: 8px 14px !important; transition: color .15s !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #111827 !important; font-weight: 600 !important;
    border-bottom: 2px solid #2563EB !important;
}
[data-testid="stTabs"] [role="tabpanel"] {
    background: white !important; border: 1px solid #E5E7EB !important;
    border-top: none !important; border-radius: 0 0 8px 8px !important; padding: 18px !important;
}

/* ── Expander ────────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: white !important; border: 1px solid #E5E7EB !important;
    border-radius: 8px !important; overflow: hidden !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.03) !important;
}
[data-testid="stExpander"] > details > summary {
    padding: 11px 14px !important; font-weight: 600 !important;
    font-size: 13px !important; color: #374151 !important;
}

/* ── Forms ───────────────────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: white !important; border: 1px solid #E5E7EB !important;
    border-radius: 10px !important; padding: 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.04) !important;
}

/* ── Charts ──────────────────────────────────────────────────────────────────── */
[data-testid="stArrowVegaLiteChart"] {
    background: white !important; border: 1px solid #E5E7EB !important;
    border-radius: 8px !important; padding: 6px !important;
}

/* ── Misc ────────────────────────────────────────────────────────────────────── */
hr { border-color: #E5E7EB !important; margin: 1rem 0 !important; }
[data-testid="stCaptionContainer"], .stCaption, small { color: #9CA3AF !important; font-size: 11.5px !important; }
[data-testid="stAlertContainer"] { border-radius: 8px !important; font-size: 13px !important; }
[data-testid="stCodeBlock"] { border: 1px solid #E5E7EB !important; border-radius: 7px !important; font-size: 12px !important; }
[data-testid="stSpinner"] { color: #2563EB !important; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #F1F5F9; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94A3B8; }

/* ══════════════════════════════════════════════════════════════════════════════
   CUSTOM HTML COMPONENTS
══════════════════════════════════════════════════════════════════════════════ */

/* Page header */
.pg-hdr {
    background: linear-gradient(135deg, #0D1117 0%, #161B27 50%, #0D1117 100%);
    border: 1px solid #1C2333;
    border-radius: 12px; padding: 20px 26px; margin-bottom: 20px; margin-top: 1rem;
}
.pg-hdr h1 {
    color: #F1F5F9 !important; font-size: 19px !important;
    margin: 0 0 5px !important; font-weight: 700 !important;
}
.pg-hdr .phs { font-size: 13px; color: #4B6078; margin: 0; line-height: 1.5; }
.pg-hdr .phb { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
.pg-hdr .phb span {
    font-size: 10.5px; font-weight: 500; color: #4B6078;
    background: rgba(255,255,255,.05); border: 1px solid #1C2333;
    border-radius: 4px; padding: 2px 10px; font-family: 'Courier New', monospace;
    letter-spacing: .03em;
}

/* KPI card */
.kc {
    background: white; border: 1px solid #E5E7EB; border-radius: 10px;
    padding: 16px 18px; box-shadow: 0 1px 2px rgba(0,0,0,.04);
    transition: box-shadow .2s, transform .2s;
}
.kc:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); transform: translateY(-1px); }
.kc .kl { font-size: 10px; text-transform: uppercase; letter-spacing: .1em; color: #9CA3AF; font-weight: 700; margin-bottom: 7px; }
.kc .kv { font-size: 28px; font-weight: 800; line-height: 1; letter-spacing: -.025em; font-variant-numeric: tabular-nums; margin-bottom: 3px; }
.kc .ks { font-size: 11px; color: #9CA3AF; }
.kc-blue   .kv { color: #2563EB; }
.kc-green  .kv { color: #059669; }
.kc-amber  .kv { color: #D97706; }
.kc-red    .kv { color: #DC2626; }
.kc-purple .kv { color: #7C3AED; }
.kc-teal   .kv { color: #0891B2; }
.kc-slate  .kv { color: #475569; }

/* Status badge — no emoji, text only */
.sb {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: 4px;
    font-size: 11px; font-weight: 700; white-space: nowrap;
    font-family: 'Courier New', monospace; letter-spacing: .03em;
}
.sb::before {
    content: '';
    display: inline-block; width: 5px; height: 5px; border-radius: 50%;
    background: currentColor; opacity: .8; flex-shrink: 0;
}
.sb-passed  { background: #DCFCE7; color: #15803D; }
.sb-review  { background: #FEF9C3; color: #A16207; }
.sb-failed  { background: #FEE2E2; color: #B91C1C; }
.sb-dup     { background: #EDE9FE; color: #6D28D9; }
.sb-missing { background: #DBEAFE; color: #1D4ED8; }
.sb-default { background: #F3F4F6; color: #4B5563; }

/* Section label */
.sl {
    display: flex; align-items: center; gap: 10px; margin: 16px 0 8px;
}
.sl::after { content: ''; flex: 1; height: 1px; background: #E5E7EB; }
.sl span { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: #9CA3AF; white-space: nowrap; }

/* Field card */
.fc {
    background: white; border: 1px solid #E5E7EB; border-radius: 8px;
    padding: 14px 16px; box-shadow: 0 1px 2px rgba(0,0,0,.03); height: 100%;
}
.fc .ft { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: #9CA3AF; padding-bottom: 9px; margin-bottom: 9px; border-bottom: 1px solid #F3F4F6; }
.fc .fr { margin-bottom: 7px; }
.fc .fk { font-size: 10px; color: #9CA3AF; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }
.fc .fv { font-size: 13px; color: #111827; font-weight: 500; margin-top: 1px; word-break: break-word; }

/* Result banner — colored left border, no emoji */
.rb {
    border-radius: 8px; padding: 13px 16px; margin-bottom: 14px;
    display: flex; align-items: center; gap: 12px;
    border: 1px solid; border-left-width: 4px;
}
.rb-ok   { background: #F0FDF4; border-color: #BBF7D0; border-left-color: #16A34A; }
.rb-warn { background: #FEFCE8; border-color: #FDE68A; border-left-color: #CA8A04; }
.rb-err  { background: #FEF2F2; border-color: #FECACA; border-left-color: #DC2626; }
.rb .ri  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rb-ok   .ri { background: #16A34A; }
.rb-warn .ri { background: #CA8A04; }
.rb-err  .ri { background: #DC2626; }
.rb .rt  { font-size: 13.5px; font-weight: 600; }
.rb-ok   .rt { color: #14532D; }
.rb-warn .rt { color: #713F12; }
.rb-err  .rt { color: #7F1D1D; }
.rb .rs  { font-size: 12px; color: #6B7280; margin-top: 2px; }

/* Review item */
.ri-card {
    background: white; border: 1px solid #E5E7EB;
    border-left: 3px solid #D97706;
    border-radius: 8px; padding: 14px 18px; margin-bottom: 8px;
    box-shadow: 0 1px 2px rgba(0,0,0,.03);
}
.ri-card.ri-dup  { border-left-color: #7C3AED; }
.ri-card.ri-fail { border-left-color: #DC2626; }

/* Generic card */
.card {
    background: white; border: 1px solid #E5E7EB;
    border-radius: 10px; padding: 16px 18px;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
}

/* Pipeline step */
.ps {
    background: white; border: 1px solid #E5E7EB;
    border-radius: 8px; padding: 14px 12px; text-align: center;
    transition: box-shadow .2s;
}
.ps:hover { box-shadow: 0 3px 10px rgba(0,0,0,.07); }
.ps .pn {
    width: 28px; height: 28px; border-radius: 50%;
    background: #EFF6FF; color: #2563EB;
    font-size: 12px; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 8px; font-family: 'Courier New', monospace;
    border: 1.5px solid #BFDBFE;
}
.ps .pt { font-size: 12px; font-weight: 700; color: #111827; margin-bottom: 4px; }
.ps .pd { font-size: 11px; color: #9CA3AF; line-height: 1.4; }
</style>
"""


def apply(brand: bool = True) -> None:
    """Inject the design system. Call once at the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ── Component helpers ─────────────────────────────────────────────────────────

def page_header(title: str, subtitle: str = "", badges: list = None) -> None:
    b_html = ""
    if badges:
        items = "".join(f'<span>{b}</span>' for b in badges)
        b_html = f'<div class="phb">{items}</div>'
    sub_html = f'<p class="phs">{subtitle}</p>' if subtitle else ""
    st.markdown(f"""
<div class="pg-hdr">
  <h1>{title}</h1>
  {sub_html}
  {b_html}
</div>""", unsafe_allow_html=True)


def kpi_card(value, label: str, color: str = "blue", sub: str = "") -> str:
    sub_html = f'<div class="ks">{sub}</div>' if sub else ""
    return f"""<div class="kc kc-{color}">
  <div class="kl">{label}</div>
  <div class="kv">{value}</div>
  {sub_html}
</div>"""


def status_badge(status: str) -> str:
    _map = {
        "PASSED":                "sb-passed",
        "REVIEW_REQUIRED":       "sb-review",
        "MISSING_DATA":          "sb-review",
        "FAILED":                "sb-failed",
        "DUPLICATE":             "sb-dup",
        "NO_SHIPMENT_FOUND":     "sb-missing",
        "MATCHED":               "sb-passed",
        "MATCHED_IN_TOLERANCE":  "sb-passed",
        "VAT_MATCHED":           "sb-passed",
        "VAT_MISMATCH":          "sb-failed",
        "VAT_NOT_FOUND":         "sb-default",
    }
    return f'<span class="sb {_map.get(status, "sb-default")}">{status}</span>'


def section_label(text: str) -> None:
    st.markdown(f'<div class="sl"><span>{text}</span></div>', unsafe_allow_html=True)


def result_banner(status: str, invoice_id, erp_id: str = "") -> None:
    if status == "PASSED":
        cls, title = "rb-ok", f"Invoice #{invoice_id} processed — OTM draft created"
        sub = f"ERP Invoice ID: {erp_id}" if erp_id else "Auto-approved. No review required."
    elif status in ("REVIEW_REQUIRED", "MISSING_DATA"):
        cls, title = "rb-warn", f"Invoice #{invoice_id} sent to Review Queue"
        sub = "Open the Review Queue to correct and approve."
    else:
        cls, title = "rb-err", f"Invoice #{invoice_id} failed validation"
        sub = f"Status: {status}. Check errors below."
    st.markdown(f"""<div class="rb {cls}">
  <div class="ri"></div>
  <div><div class="rt">{title}</div><div class="rs">{sub}</div></div>
</div>""", unsafe_allow_html=True)


def field_card(title: str, fields: dict) -> str:
    rows = "".join(
        f'<div class="fr"><div class="fk">{k}</div>'
        f'<div class="fv">{v if v not in (None, "", "None") else "—"}</div></div>'
        for k, v in fields.items()
    )
    return f'<div class="fc"><div class="ft">{title}</div>{rows}</div>'


def pipeline_step(number: str, title: str, desc: str) -> str:
    return f"""<div class="ps">
  <div class="pn">{number}</div>
  <div class="pt">{title}</div>
  <div class="pd">{desc}</div>
</div>"""
