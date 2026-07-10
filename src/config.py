import os
from pathlib import Path


def _load_streamlit_secrets() -> None:
    """
    On Streamlit Cloud, secrets live in st.secrets — NOT in os.environ or .env.
    This runs once at import time and injects all secrets into os.environ so every
    existing os.environ.get() call works without any other code changes.
    Silently skips if not running under Streamlit or no secrets configured.
    """
    try:
        import streamlit as st
        for key, value in st.secrets.items():
            if isinstance(value, str) and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_streamlit_secrets()

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
