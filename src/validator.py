import json
from typing import Any, Dict, Optional

from .matcher import match_shipment, match_service_provider, match_charge_code
from .tax import enrich_vat


def _load_tolerance_rules() -> dict:
    try:
        from .config import DATA_DIR
        path = DATA_DIR / "tolerance_rules.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "global": {"default_tolerance_abs": 100.0, "duplicate_window_days": 30},
        "validation_rules": {
            "require_invoice_number": True,
            "require_vendor_name": True,
            "require_amount": True,
            "require_currency": True,
            "allowed_currencies": ["AED", "USD", "EUR", "GBP", "INR"],
        },
    }


def validate_invoice(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full validation: duplicate check, missing fields, amount tolerance, VAT, currency.
    Returns validation result dict.
    """
    from .database import check_duplicate
    errors: list = []
    warnings: list = []
    rules = _load_tolerance_rules()
    val_rules = rules.get("validation_rules", {})
    global_rules = rules.get("global", {})

    extracted = enrich_vat(extracted)
    vat_status = extracted.get("vat_status", "VAT_NOT_FOUND")

    invoice_number = extracted.get("invoice_number")
    vendor_name = extracted.get("vendor_name")
    amount = float(extracted.get("amount_due") or 0)
    currency = (extracted.get("currency") or "").upper() or None
    charge_code = (extracted.get("charge_code") or "").upper()

    is_duplicate = False
    duplicate_of_id: Optional[int] = None

    # Missing invoice_number / vendor / amount → MISSING_DATA (handled in status branch below).
    # Accept all real ISO currency codes — no hard failure on currency.
    # All ISO currencies accepted. If a restricted list is set, warn only — never hard-fail.
    allowed_currencies = val_rules.get("allowed_currencies", [])
    if allowed_currencies and currency and currency not in allowed_currencies:
        warnings.append(f"Currency {currency} is outside configured list — verify manually")

    if invoice_number and vendor_name and amount > 0:
        dup_id = check_duplicate(invoice_number, vendor_name, amount)
        if dup_id:
            is_duplicate = True
            duplicate_of_id = dup_id
            errors.append(f"Duplicate invoice detected — matches existing invoice #{dup_id}")

    matched_charge = match_charge_code(charge_code)
    if charge_code and not matched_charge:
        warnings.append(f"Unknown charge code: {charge_code} — verify manually")

    matched_sp = match_service_provider(vendor_name, extracted.get("service_provider_id"))
    if vendor_name and not matched_sp:
        warnings.append(f"Service provider not found in master: {vendor_name}")

    matched_shipment = match_shipment(extracted)

    amount_difference = 0.0
    in_tolerance = False
    if matched_shipment and amount > 0:
        shipment_currency = matched_shipment.get("currency", "AED")
        if currency and currency != shipment_currency:
            # Cross-currency: skip numeric amount comparison, just warn
            warnings.append(
                f"Currency mismatch: invoice {currency} vs shipment {shipment_currency} "
                f"— amount comparison skipped (different currencies)"
            )
            in_tolerance = True  # don't flag as amount mismatch when currencies differ
        else:
            expected = float(matched_shipment.get("expected_amount", 0))
            tol_abs = float(matched_shipment.get("tolerance_amount", global_rules.get("default_tolerance_abs", 100)))
            amount_difference = round(abs(expected - amount), 2)
            in_tolerance = amount_difference <= tol_abs
            if not in_tolerance:
                warnings.append(
                    f"Amount mismatch: invoice {amount:,.2f} vs expected {expected:,.2f} "
                    f"(diff {amount_difference:,.2f}, tolerance {tol_abs:,.2f})"
                )
    elif amount > 0 and matched_shipment is None:
        warnings.append("No matching shipment found in reference data")

    if vat_status == "VAT_MISMATCH":
        tax_type = extracted.get("tax_type", "VAT")
        rate_label = "18% GST" if tax_type == "GST" else "5% VAT"
        warnings.append(f"Tax mismatch: invoice tax does not match calculated {rate_label}")

    missing = extracted.get("missing_fields") or []
    if missing:
        warnings.append("AI-flagged missing fields: " + ", ".join(missing))

    # Warnings that are informational — don't block auto-approval for known vendors.
    # Tax mismatch is non-blocking for known vendors because international freight
    # charges are often zero-rated in UAE (DEST.DOC FEE, equipment fees, etc.).
    _NON_BLOCKING = ("No matching shipment found", "AI-flagged missing fields", "Tax mismatch")
    blocking_warnings = [w for w in warnings if not any(nb in w for nb in _NON_BLOCKING)]
    vendor_known = (
        extracted.get("vendor_id", "UNKNOWN") not in ("UNKNOWN", "", None)
        and float(extracted.get("vendor_confidence") or 0) >= 0.7
    )

    if is_duplicate:
        validation_status = "DUPLICATE"
        match_status = "DUPLICATE"
    elif errors:
        validation_status = "FAILED"
        match_status = "EXCEPTION_REVIEW"
    elif not invoice_number or not vendor_name or amount == 0:
        validation_status = "MISSING_DATA"
        match_status = "EXCEPTION_REVIEW"
    elif warnings:
        cross_currency = any("Currency mismatch" in w for w in warnings)
        unknown_vendor = not matched_sp

        if cross_currency:
            validation_status = "REVIEW_REQUIRED"
            match_status = "EXCEPTION_REVIEW"
        elif unknown_vendor and not vendor_known:
            # Truly unknown vendor — send to review
            validation_status = "REVIEW_REQUIRED"
            match_status = "EXCEPTION_REVIEW"
        elif blocking_warnings:
            # Has real blocking issues (amount mismatch, bad charge code, etc.)
            validation_status = "REVIEW_REQUIRED"
            match_status = "MATCHED_IN_TOLERANCE" if (matched_shipment and in_tolerance) else "EXCEPTION_REVIEW"
        elif matched_shipment and in_tolerance:
            # Shipment matched in tolerance, only non-blocking warnings remain
            validation_status = "PASSED"
            match_status = "MATCHED_IN_TOLERANCE"
        elif vendor_known and not matched_shipment:
            # Known vendor, no reference shipment (common for DO/port charges) — auto-pass
            validation_status = "PASSED"
            match_status = "NO_SHIPMENT_FOUND"
        else:
            validation_status = "REVIEW_REQUIRED"
            match_status = "EXCEPTION_REVIEW"
    else:
        validation_status = "PASSED"
        if matched_shipment and amount_difference == 0:
            match_status = "MATCHED"
        elif matched_shipment:
            match_status = "MATCHED_IN_TOLERANCE"
        else:
            match_status = "NO_SHIPMENT_FOUND"

    return {
        "validation_status": validation_status,
        "match_status": match_status,
        "vat_status": vat_status,
        "matched_shipment": matched_shipment,
        "matched_service_provider": matched_sp,
        "matched_charge_code": matched_charge,
        "amount_difference": amount_difference,
        "errors": errors,
        "warnings": warnings,
        "is_duplicate": is_duplicate,
        "duplicate_of_id": duplicate_of_id,
    }
