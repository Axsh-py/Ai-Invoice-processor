import os
from pathlib import Path


def get_secret(key: str, default: str = "") -> str:
    """
    Read a secret from st.secrets (Streamlit Cloud) or os.environ (local .env).
    Always call this at render time (inside a page function), never at import time,
    so that Streamlit's runtime is fully initialised when st.secrets is accessed.
    """
    try:
        import streamlit as st
        val = st.secrets.get(key, None)
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
ORIGINALS_DIR = STORAGE_DIR / "originals"
WORKING_DIR = STORAGE_DIR / "working_copies"
PROCESSED_DIR = STORAGE_DIR / "processed"
FAILED_DIR = STORAGE_DIR / "failed"
SAMPLE_INVOICES_DIR = DATA_DIR / "sample_invoices"
EMAIL_INBOX_DIR = BASE_DIR / "sample_email_inbox"
DB_PATH = BASE_DIR / "data" / "app.db"
LOGS_DIR = BASE_DIR / "logs"

for _path in [
    DATA_DIR, ORIGINALS_DIR, WORKING_DIR, PROCESSED_DIR, FAILED_DIR,
    SAMPLE_INVOICES_DIR, EMAIL_INBOX_DIR, LOGS_DIR,
]:
    _path.mkdir(parents=True, exist_ok=True)
