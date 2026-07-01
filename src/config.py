from pathlib import Path

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
