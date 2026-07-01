import json
import os
from pathlib import Path
from typing import Optional, Tuple

from .config import DATA_DIR

_CHARGE_MASTER: Optional[dict] = None


def _get_charge_master() -> dict:
    global _CHARGE_MASTER
    if _CHARGE_MASTER is None:
        path = DATA_DIR / "charge_code_master.json"
        if path.exists():
            _CHARGE_MASTER = json.loads(path.read_text(encoding="utf-8"))
        else:
            _CHARGE_MASTER = {}
    return _CHARGE_MASTER


def detect_tax_type(extracted: dict) -> str:
    """
    Detect tax system from extracted invoice data.
    Returns 'GST' (India 18%), 'VAT' (UAE/EU 5%), or 'NONE'.
    """
    declared = (extracted.get("tax_type") or "").upper()
    if declared in ("GST", "IGST"):
        return "GST"
    if declared == "VAT":
        return "VAT"
    if declared == "NONE":
        return "NONE"
    # Auto-detect: if GST component amounts are present → India GST
    if any(extracted.get(f) for f in ("cgst_amount", "sgst_amount", "igst_amount")):
        return "GST"
    # Detect from currency: INR → likely GST
    curr = (extracted.get("currency") or "").upper()
    if curr == "INR":
        return "GST"
    # VAT only applies to AED/UAE and EU currencies; others default to NONE
    if curr in ("AED", "EUR", "GBP"):
        return "VAT"
    return "NONE"


def get_tax_rate(charge_code: Optional[str] = None, tax_type: str = "VAT") -> float:
    """Return tax rate based on tax system and charge code."""
    if tax_type == "GST":
        return 0.18   # India standard GST: 9% CGST + 9% SGST
    if tax_type == "NONE":
        return 0.0
    # VAT path — check env override, then charge master
    env_rate = os.getenv("VAT_RATE")
    if env_rate:
        try:
            return float(env_rate)
        except ValueError:
            pass
    if charge_code:
        master = _get_charge_master()
        code_data = master.get(charge_code.upper(), {})
        return float(code_data.get("tax_rate", 0.05))
    return 0.05


def get_vat_rate(charge_code: Optional[str] = None) -> float:
    """Legacy wrapper — returns VAT rate for UAE invoices."""
    return get_tax_rate(charge_code, tax_type="VAT")


def calculate_vat(
    amount_due: float,
    charge_code: Optional[str] = None,
    vat_rate: Optional[float] = None,
) -> Tuple[float, float]:
    """Return (vat_amount, amount_due_with_vat)."""
    rate = vat_rate if vat_rate is not None else get_vat_rate(charge_code)
    vat_amount = round(amount_due * rate, 2)
    amount_due_with_vat = round(amount_due + vat_amount, 2)
    return vat_amount, amount_due_with_vat


def validate_vat_match(
    extracted_vat: Optional[float],
    calculated_vat: float,
    tolerance: float = 0.02,
) -> str:
    """Return VAT_MATCHED, VAT_MISMATCH, or VAT_NOT_FOUND."""
    if extracted_vat is None:
        return "VAT_NOT_FOUND"
    if calculated_vat == 0:
        return "VAT_NOT_FOUND"
    diff = abs(float(extracted_vat) - calculated_vat)
    if diff <= tolerance * calculated_vat + 0.01:
        return "VAT_MATCHED"
    return "VAT_MISMATCH"


def enrich_vat(extracted: dict) -> dict:
    """
    Detect tax system (GST/VAT), calculate expected tax, set vat_status.
    Returns a copy of extracted with tax fields filled in.
    """
    result = dict(extracted)
    amount = float(result.get("amount_due") or 0)
    charge_code = result.get("charge_code")

    if amount <= 0:
        result["vat_status"] = "VAT_NOT_FOUND"
        return result

    # Detect which tax system this invoice uses
    tax_type = detect_tax_type(result)
    result["tax_type"] = tax_type
    rate = get_tax_rate(charge_code, tax_type)

    # For GST invoices: use sum of CGST + SGST if both present
    cgst = result.get("cgst_amount")
    sgst = result.get("sgst_amount")
    igst = result.get("igst_amount")
    if tax_type == "GST" and (cgst is not None or sgst is not None or igst is not None):
        if igst is not None:
            calc_vat = round(float(igst), 2)
        else:
            calc_vat = round((float(cgst or 0) + float(sgst or 0)), 2)
        calc_total = round(amount + calc_vat, 2)
    else:
        calc_vat, calc_total = calculate_vat(amount, charge_code, rate)

    result["calculated_vat"] = calc_vat
    result["calculated_total"] = calc_total
    result["detected_tax_rate"] = rate

    extracted_vat = result.get("vat_amount")
    if extracted_vat is None:
        # Store calculated value under separate key; do not overwrite to avoid confusion
        result["calculated_vat_amount"] = calc_vat
        result["amount_due_with_vat"] = calc_total
        result["vat_status"] = "VAT_NOT_FOUND"
    else:
        result["vat_status"] = validate_vat_match(float(extracted_vat), calc_vat)
        if result.get("amount_due_with_vat") is None:
            result["amount_due_with_vat"] = calc_total
    return result
