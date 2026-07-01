from pathlib import Path
from typing import Generator, List
from .config import BASE_DIR, EMAIL_INBOX_DIR, SAMPLE_INVOICES_DIR
from .file_manager import save_path_as_original_and_copy


def scan_email_inbox(limit: int = 50) -> List[dict]:
    """Scan EMAIL_INBOX_DIR for PDF files, return list of file records."""
    pdfs = sorted(EMAIL_INBOX_DIR.glob("*.pdf"))[:limit]
    records = []
    for pdf in pdfs:
        record = save_path_as_original_and_copy(str(pdf), source="email_inbox")
        records.append(record)
    return records


def scan_sample_invoices(limit: int = 50) -> List[dict]:
    """Scan SAMPLE_INVOICES_DIR for PDF files, return list of file records."""
    pdfs = sorted(SAMPLE_INVOICES_DIR.glob("*.pdf"))[:limit]
    records = []
    for pdf in pdfs:
        record = save_path_as_original_and_copy(str(pdf), source="sample_email_pdf")
        records.append(record)
    return records


def get_sample_invoice_paths() -> List[Path]:
    return sorted(SAMPLE_INVOICES_DIR.glob("*.pdf"))


def get_email_inbox_paths() -> List[Path]:
    return sorted(EMAIL_INBOX_DIR.glob("*.pdf"))


SOURCE_LABELS = {
    "manual_upload": "Manual Upload",
    "email_inbox": "Email Inbox",
    "sample_email_pdf": "Sample Email PDF",
    "simulated_email_inbox": "Simulated Email Inbox",
}
