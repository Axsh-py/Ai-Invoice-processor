import logging
import sys
from pathlib import Path
from .config import BASE_DIR

STEP_FILE_RECEIVED = "FILE_RECEIVED"
STEP_ORIGINAL_SAVED = "ORIGINAL_SAVED"
STEP_WORKING_COPY_CREATED = "WORKING_COPY_CREATED"
STEP_OCR_STARTED = "OCR_STARTED"
STEP_OCR_COMPLETED = "OCR_COMPLETED"
STEP_AI_PARSING_STARTED = "AI_PARSING_STARTED"
STEP_AI_PARSING_COMPLETED = "AI_PARSING_COMPLETED"
STEP_ENRICHMENT_COMPLETED = "ENRICHMENT_COMPLETED"
STEP_VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
STEP_OTM_DRAFT_CREATED = "OTM_DRAFT_CREATED"
STEP_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STEP_DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
STEP_FAILED = "FAILED"

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_ERROR = "ERROR"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_file_handler = logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8")
_file_handler.setFormatter(_fmt)
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_fmt)

_logger = logging.getLogger("otm_pipeline")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _logger.addHandler(_file_handler)
    _logger.addHandler(_console_handler)


def get_logger(name: str = "otm_pipeline") -> logging.Logger:
    return logging.getLogger(name)


def db_log(invoice_id, step: str, status: str, message: str) -> None:
    """Write a processing log entry to the database (imported lazily to avoid circular)."""
    try:
        from .database import log_step
        log_step(invoice_id, step, status, message)
    except Exception as e:
        _logger.warning("db_log failed for invoice %s step %s: %s", invoice_id, step, e)
    level = logging.INFO if status == STATUS_OK else (logging.WARNING if status == STATUS_WARN else logging.ERROR)
    _logger.log(level, "[Invoice %s] %s | %s | %s", invoice_id, step, status, message)
