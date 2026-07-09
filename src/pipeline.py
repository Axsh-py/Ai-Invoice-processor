import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from .ocr import extract_text_from_pdf
from .ai_parser import parse_invoice, parse_invoice_for_vendor
from .vendor_classifier import classify_vendor_full
from .vendor_registry import get_vendor
from .matcher import enrich_invoice, match_shipment, match_service_provider, match_charge_code
from .validator import validate_invoice
from .otm_payload import build_otm_payload
from .database import insert_full_invoice
from .logger import db_log, STEP_FILE_RECEIVED, STEP_OCR_STARTED, STEP_OCR_COMPLETED
from .logger import STEP_AI_PARSING_STARTED, STEP_AI_PARSING_COMPLETED, STEP_ENRICHMENT_COMPLETED
from .logger import STEP_VALIDATION_COMPLETED, STEP_OTM_DRAFT_CREATED, STEP_REVIEW_REQUIRED
from .logger import STATUS_OK, STATUS_WARN, STATUS_ERROR
from .config import PROCESSED_DIR, FAILED_DIR


def process_invoice(
    storage_record: Dict[str, Any],
    ocr_mode: str = "auto",
    ai_mode: str = "mock",
) -> Tuple[int, str, dict, dict, dict, str]:
    """
    Full invoice processing pipeline.
    Returns: (invoice_id, raw_text, extracted, validation, otm_payload, output_path)
    """
    working_path = storage_record.get("working_copy_path", "")
    source_type = storage_record.get("source_type") or storage_record.get("source", "manual_upload")
    invoice_id = None

    db_log(None, STEP_FILE_RECEIVED, STATUS_OK,
           f"File received: {storage_record.get('original_filename', '')} | source: {source_type}")

    try:
        db_log(None, STEP_OCR_STARTED, STATUS_OK, "Smart OCR — auto-selecting best extraction method")
        raw_text, ocr_method = extract_text_from_pdf(working_path)
        db_log(None, STEP_OCR_COMPLETED, STATUS_OK,
               f"OCR complete — method={ocr_method} | {len(raw_text)} chars extracted")

        # ── Vendor classification ──────────────────────────────────────────────
        vendor_id, vendor_confidence, vendor_method = classify_vendor_full(
            raw_text, ai_mode=ai_mode
        )
        vendor_info = get_vendor(vendor_id) or {}
        db_log(None, STEP_AI_PARSING_STARTED, STATUS_OK,
               f"Vendor: {vendor_id} (conf={vendor_confidence:.2f}, method={vendor_method}) | AI: {ai_mode}")

        # ── Vendor-aware extraction ────────────────────────────────────────────
        extracted = parse_invoice_for_vendor(raw_text, vendor_id=vendor_id, mode=ai_mode)
        extracted["vendor_id"] = vendor_id
        extracted["vendor_confidence"] = vendor_confidence
        extracted["vendor_category"] = vendor_info.get("category", "unknown")
        extracted["vendor_short_name"] = vendor_info.get("short_name", vendor_id)
        if not extracted.get("vendor_name") and vendor_info.get("name"):
            extracted["vendor_name"] = vendor_info["name"]

        # ── Vendor-registry enrichment (authoritative when vendor is known) ───
        # When vendor classification is confident, use vendor_registry as ground
        # truth for service_provider_id and charge_code — more reliable than
        # guessing from OCR text alone.
        if vendor_id != "UNKNOWN" and vendor_confidence >= 0.7:
            if vendor_info.get("otm_sp_id") and not extracted.get("service_provider_id"):
                extracted["service_provider_id"] = vendor_info["otm_sp_id"]
            # Set default charge code from vendor's charge_code_map if not extracted
            if not extracted.get("charge_code"):
                default_code = vendor_info.get("charge_code_map", {}).get("default")
                if default_code:
                    extracted["charge_code"] = default_code

        db_log(None, STEP_AI_PARSING_COMPLETED, STATUS_OK,
               f"AI parse complete — vendor: {vendor_id} | charge: {extracted.get('charge_code')} "
               f"amount: {extracted.get('amount_due')} conf: {extracted.get('confidence_score')}")

        matched_shipment = match_shipment(extracted)
        matched_sp = match_service_provider(extracted.get("vendor_name"), extracted.get("service_provider_id"))
        matched_charge = match_charge_code(extracted.get("charge_code"))
        extracted = enrich_invoice(extracted, matched_shipment, matched_sp, matched_charge)
        db_log(None, STEP_ENRICHMENT_COMPLETED, STATUS_OK,
               f"Enrichment done — shipment: {matched_shipment.get('shipment_id') if matched_shipment else 'none'}")

        validation = validate_invoice(extracted)
        db_log(None, STEP_VALIDATION_COMPLETED,
               STATUS_OK if validation["validation_status"] == "PASSED" else STATUS_WARN,
               f"Validation: {validation['validation_status']} | match: {validation['match_status']} | "
               f"VAT: {validation.get('vat_status')}")

        otm_payload = build_otm_payload(extracted, validation)

        invoice_id = insert_full_invoice(
            source_type=source_type,
            file_record=storage_record,
            raw_ocr_text=raw_text,
            ocr_mode=ocr_method,
            ai_mode=ai_mode,
            extracted=extracted,
            validation=validation,
            otm_payload=otm_payload,
        )

        if otm_payload.get("erp_status") == "ERP_DRAFT_CREATED":
            db_log(invoice_id, STEP_OTM_DRAFT_CREATED, STATUS_OK,
                   f"OTM draft created: {otm_payload.get('erp_invoice_id')}")
        else:
            db_log(invoice_id, STEP_REVIEW_REQUIRED, STATUS_WARN,
                   "Sent to human review — " + "; ".join(
                       (validation.get("errors") or []) + (validation.get("warnings") or [])))

        output_path = PROCESSED_DIR / f"invoice_{invoice_id}_otm_payload.json"
        output_path.write_text(json.dumps({
            "invoice_id": invoice_id,
            "extracted": extracted,
            "validation": validation,
            "otm_payload": otm_payload,
        }, indent=2, default=str), encoding="utf-8")

        return invoice_id, raw_text, extracted, validation, otm_payload, str(output_path)

    except Exception as exc:
        from .logger import STEP_FAILED
        import re as _re
        db_log(invoice_id, STEP_FAILED, STATUS_ERROR, f"Pipeline error: {exc}")
        try:
            safe_name = _re.sub(r'[<>:"/\\|?*]', '_', storage_record.get('original_filename', 'unknown'))
            ts = datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            error_path = FAILED_DIR / f"failed_{safe_name}_{ts}.error.txt"
            error_path.write_text(str(exc), encoding="utf-8")
        except Exception:
            pass
        raise
