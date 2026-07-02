import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT,
    processing_status TEXT DEFAULT 'PENDING',
    validation_status TEXT,
    match_status TEXT,
    vat_status TEXT,
    erp_status TEXT,
    erp_invoice_id TEXT,
    confidence REAL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS invoice_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    original_file_path TEXT,
    working_copy_path TEXT,
    file_hash TEXT,
    original_filename TEXT,
    file_size INTEGER,
    created_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    ocr_mode TEXT,
    raw_ocr_text TEXT,
    ocr_status TEXT,
    ocr_error TEXT,
    created_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS extracted_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    ai_mode TEXT,
    extracted_json TEXT,
    invoice_number TEXT,
    invoice_date TEXT,
    vendor_name TEXT,
    service_provider_id TEXT,
    currency TEXT,
    amount_due REAL,
    vat_amount REAL,
    amount_due_with_vat REAL,
    charge_code TEXT,
    charge_description TEXT,
    invoice_type TEXT,
    invoice_category TEXT,
    shipment_id TEXT,
    route_or_port TEXT,
    confidence REAL,
    missing_fields TEXT,
    possible_errors TEXT,
    corrected_by TEXT,
    corrected_at TEXT,
    created_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    validation_json TEXT,
    validation_status TEXT,
    match_status TEXT,
    vat_status TEXT,
    matched_shipment_id TEXT,
    matched_vendor TEXT,
    amount_difference REAL,
    errors TEXT,
    warnings TEXT,
    is_duplicate INTEGER DEFAULT 0,
    duplicate_of_id INTEGER,
    created_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS otm_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    otm_invoice_id TEXT UNIQUE,
    otm_payload_json TEXT,
    draft_status TEXT DEFAULT 'PENDING',
    approved_by TEXT,
    approved_at TEXT,
    rejected_reason TEXT,
    created_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS processing_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    step TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoice_payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    raw_text TEXT,
    extracted_json TEXT,
    validation_json TEXT,
    otm_payload_json TEXT,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

CREATE INDEX IF NOT EXISTS idx_invoice_files_invoice_id ON invoice_files(invoice_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_invoice_id ON ocr_results(invoice_id);
CREATE INDEX IF NOT EXISTS idx_extracted_data_invoice_id ON extracted_data(invoice_id);
CREATE INDEX IF NOT EXISTS idx_extracted_data_invoice_number ON extracted_data(invoice_number, vendor_name);
CREATE INDEX IF NOT EXISTS idx_validation_results_invoice_id ON validation_results(invoice_id);
CREATE INDEX IF NOT EXISTS idx_otm_drafts_invoice_id ON otm_drafts(invoice_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_invoice_id ON processing_logs(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoices_erp_status ON invoices(erp_status);
CREATE INDEX IF NOT EXISTS idx_invoices_match_status ON invoices(match_status);
CREATE INDEX IF NOT EXISTS idx_invoice_payloads_invoice_id ON invoice_payloads(invoice_id);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Migrations for columns added after initial deployment
        for ddl in [
            "ALTER TABLE extracted_data ADD COLUMN corrected_by TEXT",
            "ALTER TABLE extracted_data ADD COLUMN corrected_at TEXT",
        ]:
            try:
                conn.execute(ddl)
            except Exception:
                pass  # column already exists
        conn.commit()


def insert_full_invoice(
    source_type: str,
    file_record: Dict[str, Any],
    raw_ocr_text: str,
    ocr_mode: str,
    ai_mode: str,
    extracted: Dict[str, Any],
    validation: Dict[str, Any],
    otm_payload: Dict[str, Any],
) -> int:
    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    validation_status = validation.get("validation_status", "UNKNOWN")
    match_status = validation.get("match_status", "UNKNOWN")
    vat_status = validation.get("vat_status", "VAT_NOT_FOUND")
    erp_status = otm_payload.get("erp_status", "WAITING_FOR_HUMAN_REVIEW")
    erp_invoice_id = otm_payload.get("erp_invoice_id", "")
    confidence = float(extracted.get("confidence_score") or extracted.get("confidence") or 0.0)

    with _connect() as conn:
        cur = conn.cursor()

        cur.execute(
            """INSERT INTO invoices
               (source_type, processing_status, validation_status, match_status,
                vat_status, erp_status, erp_invoice_id, confidence, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source_type, "COMPLETED", validation_status, match_status,
             vat_status, erp_status, erp_invoice_id, confidence, now, now),
        )
        invoice_id = cur.lastrowid

        cur.execute(
            """INSERT INTO invoice_files
               (invoice_id, original_file_path, working_copy_path, file_hash,
                original_filename, file_size, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                invoice_id,
                file_record.get("original_file_path", ""),
                file_record.get("working_copy_path", ""),
                file_record.get("file_hash", ""),
                file_record.get("original_filename", ""),
                int(file_record.get("file_size", 0)),
                now,
            ),
        )

        cur.execute(
            """INSERT INTO ocr_results
               (invoice_id, ocr_mode, raw_ocr_text, ocr_status, ocr_error, created_at)
               VALUES (?,?,?,?,?,?)""",
            (invoice_id, ocr_mode, raw_ocr_text,
             "SUCCESS" if raw_ocr_text else "FAILED", None, now),
        )

        matched_shipment = validation.get("matched_shipment") or {}
        cur.execute(
            """INSERT INTO extracted_data
               (invoice_id, ai_mode, extracted_json, invoice_number, invoice_date,
                vendor_name, service_provider_id, currency, amount_due, vat_amount,
                amount_due_with_vat, charge_code, charge_description, invoice_type,
                invoice_category, shipment_id, route_or_port, confidence,
                missing_fields, possible_errors, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                invoice_id, ai_mode, json.dumps(extracted),
                extracted.get("invoice_number"),
                extracted.get("invoice_date"),
                extracted.get("vendor_name"),
                extracted.get("service_provider_id"),
                extracted.get("currency"),
                float(extracted.get("amount_due") or 0),
                float(extracted.get("vat_amount") or 0),
                float(extracted.get("amount_due_with_vat") or 0),
                extracted.get("charge_code"),
                extracted.get("charge_description"),
                extracted.get("invoice_type"),
                extracted.get("invoice_category") or extracted.get("category"),
                extracted.get("shipment_id"),
                extracted.get("route_or_port"),
                confidence,
                json.dumps(extracted.get("missing_fields") or []),
                json.dumps(extracted.get("possible_errors") or []),
                now,
            ),
        )

        cur.execute(
            """INSERT INTO validation_results
               (invoice_id, validation_json, validation_status, match_status, vat_status,
                matched_shipment_id, matched_vendor, amount_difference, errors, warnings,
                is_duplicate, duplicate_of_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                invoice_id, json.dumps(validation),
                validation_status, match_status, vat_status,
                matched_shipment.get("shipment_id", ""),
                matched_shipment.get("vendor_name", ""),
                float(validation.get("amount_difference", 0)),
                json.dumps(validation.get("errors") or []),
                json.dumps(validation.get("warnings") or []),
                1 if validation.get("is_duplicate") else 0,
                validation.get("duplicate_of_id"),
                now,
            ),
        )

        cur.execute(
            """INSERT INTO otm_drafts
               (invoice_id, otm_invoice_id, otm_payload_json, draft_status, created_at)
               VALUES (?,?,?,?,?)""",
            (invoice_id, erp_invoice_id, json.dumps(otm_payload), erp_status, now),
        )

        cur.execute(
            """INSERT INTO invoice_payloads
               (invoice_id, raw_text, extracted_json, validation_json, otm_payload_json)
               VALUES (?,?,?,?,?)""",
            (invoice_id, raw_ocr_text, json.dumps(extracted, indent=2),
             json.dumps(validation, indent=2), json.dumps(otm_payload, indent=2)),
        )

        conn.commit()
        return invoice_id


def log_step(invoice_id: Optional[int], step: str, status: str, message: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO processing_logs (invoice_id, step, status, message, created_at) VALUES (?,?,?,?,?)",
            (invoice_id, step, status, message, datetime.now(tz=timezone.utc).isoformat()),
        )
        conn.commit()


def list_invoices(limit: int = 500) -> List[Dict[str, Any]]:
    init_db()
    sql = """
        SELECT i.*, ed.invoice_number, ed.invoice_date, ed.vendor_name,
               ed.charge_code, ed.invoice_category, ed.currency,
               ed.amount_due, ed.vat_amount, ed.amount_due_with_vat,
               ed.shipment_id, ed.missing_fields
        FROM invoices i
        LEFT JOIN extracted_data ed
            ON ed.id = (SELECT MAX(id) FROM extracted_data WHERE invoice_id = i.id)
        ORDER BY i.id DESC LIMIT ?
    """
    with _connect() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_invoice_full(invoice_id: int) -> Tuple[Optional[Dict], Optional[Dict]]:
    init_db()
    with _connect() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        payload = conn.execute("SELECT * FROM invoice_payloads WHERE invoice_id=?", (invoice_id,)).fetchone()
        return (dict(inv) if inv else None, dict(payload) if payload else None)


def get_review_queue() -> List[Dict[str, Any]]:
    init_db()
    sql = """
        SELECT i.id, i.erp_status, i.validation_status, i.match_status, i.vat_status,
               i.confidence, i.created_at,
               ed.invoice_number, ed.vendor_name, ed.charge_code, ed.currency,
               ed.amount_due, ed.amount_due_with_vat, ed.invoice_category,
               ed.missing_fields, ed.possible_errors,
               f.original_file_path, f.working_copy_path,
               vr.errors, vr.warnings, vr.amount_difference, vr.is_duplicate
        FROM invoices i
        LEFT JOIN extracted_data ed
            ON ed.id = (SELECT MAX(id) FROM extracted_data WHERE invoice_id = i.id)
        LEFT JOIN invoice_files f
            ON f.id = (SELECT MAX(id) FROM invoice_files WHERE invoice_id = i.id)
        LEFT JOIN validation_results vr
            ON vr.id = (SELECT MAX(id) FROM validation_results WHERE invoice_id = i.id)
        WHERE i.erp_status = 'WAITING_FOR_HUMAN_REVIEW'
        ORDER BY i.id DESC
    """
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_otm_drafts() -> List[Dict[str, Any]]:
    init_db()
    sql = """
        SELECT d.*, i.confidence, i.created_at as processed_at,
               ed.invoice_number, ed.vendor_name, ed.currency,
               ed.amount_due, ed.amount_due_with_vat
        FROM otm_drafts d
        JOIN invoices i ON i.id = d.invoice_id
        LEFT JOIN extracted_data ed
            ON ed.id = (SELECT MAX(id) FROM extracted_data WHERE invoice_id = d.invoice_id)
        ORDER BY d.id DESC
    """
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_processing_logs(invoice_id: int) -> List[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM processing_logs WHERE invoice_id=? ORDER BY id ASC",
            (invoice_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_otm_draft_status(
    invoice_id: int,
    status: str,
    approved_by: Optional[str] = None,
    rejected_reason: Optional[str] = None,
) -> None:
    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """UPDATE otm_drafts SET draft_status=?, approved_by=?, approved_at=?, rejected_reason=?
               WHERE invoice_id=?""",
            (status, approved_by, now if approved_by else None, rejected_reason, invoice_id),
        )
        conn.execute(
            "UPDATE invoices SET erp_status=?, updated_at=? WHERE id=?",
            (status, now, invoice_id),
        )
        conn.commit()


def save_manual_corrections(invoice_id: int, corrections: Dict[str, Any], corrected_by: str) -> None:
    """Save human-corrected field values into extracted_data and mark invoice as corrected."""
    from .logger import get_logger
    _log = get_logger()
    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    with _connect() as conn:
        fields = ["vendor_name", "invoice_number", "invoice_date", "charge_code",
                  "currency", "amount_due", "vat_amount", "amount_due_with_vat", "shipment_id"]
        sets = ", ".join(f"{f}=?" for f in fields if f in corrections)
        vals = [corrections[f] for f in fields if f in corrections]
        if sets:
            conn.execute(
                f"UPDATE extracted_data SET {sets}, corrected_by=?, corrected_at=? WHERE invoice_id=?",
                vals + [corrected_by, now, invoice_id],
            )
        row = conn.execute(
            "SELECT extracted_json FROM extracted_data WHERE invoice_id=? ORDER BY id DESC LIMIT 1",
            (invoice_id,),
        ).fetchone()
        if row:
            try:
                existing = json.loads(row["extracted_json"] or "{}")
                existing.update({k: v for k, v in corrections.items() if v is not None and v != ""})
                conn.execute(
                    "UPDATE extracted_data SET extracted_json=? WHERE invoice_id=?",
                    (json.dumps(existing), invoice_id),
                )
            except Exception as e:
                _log.warning("save_manual_corrections: failed to rebuild extracted_json for invoice %s: %s", invoice_id, e)
        conn.execute(
            "UPDATE invoices SET validation_status='CORRECTED', updated_at=? WHERE id=?",
            (now, invoice_id),
        )
        conn.commit()


def check_duplicate(invoice_number: str, vendor_name: str, amount_due: float) -> Optional[int]:
    """Return existing invoice id if this looks like a duplicate, else None."""
    if not invoice_number or invoice_number in ("UNKNOWN", ""):
        return None
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """SELECT i.id FROM invoices i
               JOIN extracted_data ed ON ed.invoice_id = i.id
               WHERE ed.invoice_number = ? AND ed.vendor_name = ?
               AND ABS(ed.amount_due - ?) < 0.005
               ORDER BY i.id ASC LIMIT 1""",
            (invoice_number, vendor_name, float(amount_due or 0)),
        ).fetchone()
        return row["id"] if row else None


def get_kpis() -> Dict[str, Any]:
    init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM invoices").fetchone()["c"]
        matched = conn.execute(
            "SELECT COUNT(*) as c FROM invoices WHERE match_status='MATCHED'"
        ).fetchone()["c"]
        tolerance = conn.execute(
            "SELECT COUNT(*) as c FROM invoices WHERE match_status='MATCHED_IN_TOLERANCE'"
        ).fetchone()["c"]
        review = conn.execute(
            "SELECT COUNT(*) as c FROM invoices WHERE erp_status='WAITING_FOR_HUMAN_REVIEW' "
            "AND validation_status IN ('REVIEW_REQUIRED','MISSING_DATA','FAILED')"
        ).fetchone()["c"]
        duplicates = conn.execute(
            "SELECT COUNT(*) as c FROM validation_results WHERE is_duplicate=1"
        ).fetchone()["c"]
        total_amt = conn.execute(
            "SELECT COALESCE(SUM(amount_due_with_vat),0) as s FROM extracted_data"
        ).fetchone()["s"]
        avg_conf = conn.execute(
            "SELECT COALESCE(AVG(confidence),0) as a FROM invoices"
        ).fetchone()["a"]
        otm_drafts = conn.execute(
            "SELECT COUNT(*) as c FROM invoices WHERE erp_status='ERP_DRAFT_CREATED'"
        ).fetchone()["c"]
    return {
        "total": total,
        "matched": matched,
        "matched_in_tolerance": tolerance,
        "review_required": review,
        "duplicates": duplicates,
        "total_amount": round(total_amt, 2),
        "avg_confidence": round(avg_conf * 100, 1),
        "otm_drafts": otm_drafts,
    }
