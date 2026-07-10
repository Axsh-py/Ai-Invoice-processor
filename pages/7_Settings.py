import json
import os
import sqlite3
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.config import BASE_DIR, DB_PATH, ORIGINALS_DIR, WORKING_DIR, PROCESSED_DIR, FAILED_DIR
from src.config import SAMPLE_INVOICES_DIR, EMAIL_INBOX_DIR
from src.theme import apply, page_header, section_label

st.set_page_config(page_title="Settings — OTM AI", page_icon="⚙️", layout="wide")
apply()
init_db()

page_header("Settings & System Status",
            subtitle="API keys, OCR mode, database statistics, and file storage overview.")

section_label("API STATUS")
col1, col2, col3 = st.columns(3)

with col1:
    oai_key = os.getenv("OPENAI_API_KEY", "")
    if oai_key and len(oai_key) > 10:
        st.success("OpenAI API Key — Configured")
        st.caption(f"Key: sk-...{oai_key[-6:]}")
    else:
        st.warning("OpenAI API Key — Not Set (mock mode active)")
        st.caption("Streamlit Cloud: add `OPENAI_API_KEY = 'sk-...'` in App Settings → Secrets.")

# ── Live AI connection test ────────────────────────────────────────────────────
st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
oai_key = os.getenv("OPENAI_API_KEY", "")
if oai_key and len(oai_key) > 10:
    if st.button("🔌 Test AI Connection (Live OpenAI Call)", type="primary", use_container_width=False):
        with st.spinner("Calling OpenAI gpt-4o-mini..."):
            try:
                from openai import OpenAI
                _client = OpenAI(api_key=oai_key)
                _resp = _client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an invoice assistant. Reply with a single JSON object."},
                        {"role": "user", "content": 'Extract: {"status": "ok", "message": "AI is working"}'},
                    ],
                    temperature=0,
                    max_tokens=60,
                    response_format={"type": "json_object"},
                )
                _content = _resp.choices[0].message.content
                _parsed = json.loads(_content)
                st.success(f"✅ OpenAI connected! Model: gpt-4o-mini | Response: {_parsed}")
                st.caption(f"Tokens used — prompt: {_resp.usage.prompt_tokens}, completion: {_resp.usage.completion_tokens}")
            except Exception as _e:
                st.error(f"❌ OpenAI call failed: {_e}")
                st.caption("Check your API key is valid and has credits. Key shown above.")

with col2:
    from src.ocr import tesseract_available
    if tesseract_available():
        st.success("Tesseract OCR — Installed & Ready")
        import platform as _pl
        _tess_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe" if _pl.system() == "Windows" else "tesseract"
        tess_cmd = os.environ.get("TESSERACT_CMD", _tess_default)
        st.caption(f"Binary: `{tess_cmd}`")
    else:
        st.error("Tesseract — Not Installed")
        st.caption("Download from github.com/UB-Mannheim/tesseract/wiki and install.")

with col3:
    ai_mode = os.getenv("AI_MODE", "mock")
    ocr_mode = os.getenv("OCR_MODE", "pdf_text")
    vat_rate = os.getenv("VAT_RATE", "0.05")
    st.success(f"Mode: AI={ai_mode} | OCR={ocr_mode}")
    st.caption(f"Default VAT rate: {float(vat_rate)*100:.0f}%")

section_label("DATABASE STATISTICS")

try:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    tables = ["invoices", "invoice_files", "ocr_results", "extracted_data",
              "validation_results", "otm_drafts", "processing_logs", "invoice_payloads"]
    db_stats = {}
    for tbl in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) as c FROM {tbl}").fetchone()["c"]
            db_stats[tbl] = count
        except Exception:
            db_stats[tbl] = "N/A"
    conn.close()
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    st.write(f"**Database:** `{DB_PATH}`  |  **Size:** {db_size/1024:.1f} KB")
    cols = st.columns(len(tables))
    for i, (tbl, cnt) in enumerate(db_stats.items()):
        cols[i].metric(tbl.replace("_", " ").title(), cnt)
except Exception as e:
    st.error(f"DB error: {e}")

section_label("FILE STORAGE")

dirs = {
    "Original Invoices": ORIGINALS_DIR,
    "Working Copies": WORKING_DIR,
    "Processed JSON": PROCESSED_DIR,
    "Failed Files": FAILED_DIR,
    "Sample Invoices": SAMPLE_INVOICES_DIR,
    "Email Inbox": EMAIL_INBOX_DIR,
}
sc = st.columns(3)
for i, (label, path) in enumerate(dirs.items()):
    files = list(path.rglob("*")) if path.exists() else []
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    sc[i % 3].metric(label, f"{len([f for f in files if f.is_file()])} files",
                     delta=f"{total_size/1024:.1f} KB")

section_label("REFERENCE DATA")

from src.config import DATA_DIR

ref_files = {
    "charge_code_master.json": DATA_DIR / "charge_code_master.json",
    "service_providers.json": DATA_DIR / "service_providers.json",
    "mock_shipments.json": DATA_DIR / "mock_shipments.json",
    "tolerance_rules.json": DATA_DIR / "tolerance_rules.json",
}
for name, path in ref_files.items():
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            count = len(data) if isinstance(data, list) else len(data)
            st.markdown(f"`{name}` — **{count}** entries")
        except Exception as e:
            st.markdown(f"`{name}` — parse error: {e}")
    else:
        st.markdown(f"`{name}` — **NOT FOUND**")

section_label("ENVIRONMENT CONFIGURATION")
st.code(f"""# .env configuration
OPENAI_API_KEY     = {"[SET]" if os.getenv("OPENAI_API_KEY") else "[NOT SET]"}
OCR_SPACE_API_KEY  = {"[SET]" if os.getenv("OCR_SPACE_API_KEY") else "[NOT SET]"}
AI_MODE            = {os.getenv("AI_MODE", "mock")}
OCR_MODE           = {os.getenv("OCR_MODE", "pdf_text")}
VAT_RATE           = {os.getenv("VAT_RATE", "0.05")}
DEFAULT_CURRENCY   = {os.getenv("DEFAULT_CURRENCY", "AED")}
""", language="ini")

section_label("QUICK ACTIONS")
col_a, col_b = st.columns(2)
with col_a:
    if st.button("Regenerate Sample Invoices"):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(BASE_DIR / "generate_samples.py")],
                                capture_output=True, text=True, cwd=str(BASE_DIR))
        if result.returncode == 0:
            st.success(result.stdout or "Samples regenerated.")
        else:
            st.error(result.stderr or "Error regenerating samples.")

with col_b:
    if st.button("Clear Database (demo reset)", type="secondary"):
        st.session_state["confirm_clear"] = True
        st.rerun()
    if st.session_state.get("confirm_clear"):
        st.warning("This will delete ALL invoice data. Are you sure?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, Clear Database", key="confirm_clear_yes", type="primary"):
                try:
                    conn = sqlite3.connect(str(DB_PATH))
                    tables = ["processing_logs", "otm_drafts", "validation_results",
                              "extracted_data", "ocr_results", "invoice_files",
                              "invoice_payloads", "invoices"]
                    for tbl in tables:
                        try:
                            conn.execute(f"DELETE FROM {tbl}")
                        except Exception:
                            pass
                    conn.commit()
                    conn.close()
                    st.session_state.pop("confirm_clear", None)
                    st.success("Database cleared.")
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_no:
            if st.button("Cancel", key="confirm_clear_no"):
                st.session_state.pop("confirm_clear", None)
                st.rerun()
