import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .prompts.invoice_parser_prompt import SYSTEM_PROMPT, build_user_prompt, build_repair_prompt
from .prompts.invoice_parser_prompt import build_vendor_user_prompt, VENDOR_SYSTEM_PROMPT
from .schemas import validate_extracted_json


def _find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def _load_charge_master() -> dict:
    try:
        from .config import DATA_DIR
        path = DATA_DIR / "charge_code_master.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "AFRT": {"meaning": "Air Freight Charge", "cost_type": "Freight",
                 "description": "Air Freight Charge", "category": "freight", "tax_rate": 0.05},
        "DFRT": {"meaning": "Delivery Freight Charge", "cost_type": "Freight",
                 "description": "Delivery Freight Charge", "category": "delivery", "tax_rate": 0.05},
        "CUST": {"meaning": "Customs Clearance Fee", "cost_type": "Accessorial",
                 "description": "Customs Clearance Fee", "category": "customs", "tax_rate": 0.0},
        "WHSE": {"meaning": "Warehouse Handling Fee", "cost_type": "Accessorial",
                 "description": "Warehouse Handling Fee", "category": "warehouse", "tax_rate": 0.05},
        "TRANS": {"meaning": "Road Transport / Trucking Fee", "cost_type": "Freight",
                  "description": "Road Transport Fee", "category": "transport", "tax_rate": 0.05},
    }


def mock_parse_invoice(raw_text: str) -> dict:
    """Deterministic regex-based parser — works without any API key."""
    charge_master = _load_charge_master()
    charge_code = _find(r"Charge\s*Code\s*[:\-]\s*([A-Z0-9]+)", raw_text, "")
    if not charge_code:
        for code in charge_master:
            if code in raw_text:
                charge_code = code
                break
    if not charge_code:
        # Table layout: standalone code on its own line between description and amount
        _tbl = re.search(r"\n([A-Z]{3,5})\n([0-9,]+\.[0-9]{2})", raw_text)
        _currencies = {"AED", "USD", "EUR", "GBP", "INR", "VAT"}
        if _tbl and _tbl.group(1) not in _currencies:
            charge_code = _tbl.group(1)
    if not charge_code:
        charge_code = "AFRT"

    code_data = charge_master.get(charge_code, {})

    # Handle both "Label: Value" on one line AND table layouts where value is on the next line
    amount_str = _find(r"(?:Freight\s*Charge|Charge\s*Amount|Amount\s*Due|Amount)\s*[:\-]\s*\n?\s*([0-9,]+\.?[0-9]*)", raw_text, "")
    if not amount_str:
        # Table layout: charge code followed immediately by amount on next line
        amount_str = re.search(rf"{re.escape(charge_code)}\s*\n\s*([0-9,]+\.?[0-9]*)", raw_text, re.IGNORECASE)
        amount_str = amount_str.group(1) if amount_str else "0"
    amount = float(amount_str.replace(",", "") or 0)

    # GST components (Indian invoices)
    cgst_str = _find(r"(?:IN:\s*)?Central\s*GST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    sgst_str = _find(r"(?:IN:\s*)?State\s*GST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    igst_str = _find(r"IGST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    cgst_amount: Optional[float] = float(cgst_str.replace(",", "")) if cgst_str else None
    sgst_amount: Optional[float] = float(sgst_str.replace(",", "")) if sgst_str else None
    igst_amount: Optional[float] = float(igst_str.replace(",", "")) if igst_str else None

    # Detect tax system
    has_gst = bool(cgst_str or sgst_str or igst_str or re.search(r"\bGST\b", raw_text))
    has_vat = bool(re.search(r"\bVAT\b", raw_text))
    tax_type = "GST" if has_gst else ("VAT" if has_vat else "NONE")

    # Total tax amount
    if cgst_amount is not None or sgst_amount is not None:
        vat_amount: Optional[float] = round((cgst_amount or 0) + (sgst_amount or 0), 2)
    elif igst_amount is not None:
        vat_amount = igst_amount
    else:
        vat_str = _find(r"(?:VAT|Tax)\s*(?:\([^)]*\))?\s*[:\-]\s*\n?\s*([0-9,]+\.?[0-9]*)", raw_text, "")
        vat_amount = float(vat_str.replace(",", "")) if vat_str else None

    total_str = _find(r"(?:Total\s*Due|Amount\s*Due|Grand\s*Total|Total)\s*[:\-]?\s*\n?\s*([0-9,]+\.?[0-9]*)", raw_text, "")
    total_amount: Optional[float] = float(total_str.replace(",", "")) if total_str else None

    # Require at least one digit to avoid grabbing adjacent label words ("Invoice", "Date")
    invoice_number = _find(r"Invoice\s*(?:No|Number|#)\s*[:\-]\s*([A-Z0-9\/\-]*[0-9][A-Z0-9\/\-]*)", raw_text, "")
    if not invoice_number:
        invoice_number = _find(r"(?:Ref|Reference)\s*[:\-]\s*([A-Z0-9\/\-]*[0-9][A-Z0-9\/\-]*)", raw_text, "")

    # MBL / Bill of Lading number
    mbl_number = _find(r"(?:Bill\s*of\s*Lading|B/?L\s*(?:No|Number|#)?|MBL|HBL)\s*[:\-]?\s*([A-Z0-9]{6,20})", raw_text, "")

    # Customer / Account number
    customer_number = _find(r"(?:Customer\s*(?:No|Number|ID)|Account\s*(?:No|Number)|Customer\s*#)\s*[:\-]\s*([A-Z0-9]+)", raw_text, "")

    vendor_name = _find(r"Vendor\s*[:\-]\s*(.+)", raw_text, "")
    if not vendor_name:
        # For real-world invoices: "On behalf of" / "Bill-to Party" patterns
        vendor_name = _find(r"(?:On\s*behalf\s*of|Issued\s*by)\s*[:\-]\s*(.+)", raw_text, "")

    invoice_date = _find(r"Invoice\s*Date\s*[:\-]\s*([0-9A-Za-z\-\.\/ ]+)", raw_text,
                         datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"))
    service_provider_id = _find(r"Service\s*Provider\s*ID\s*[:\-]\s*([A-Z0-9\.]+)", raw_text, "")
    shipment_id = _find(r"Shipment\s*ID\s*[:\-]\s*([A-Z0-9\-]+)", raw_text, "")
    # Detect currency from text — look for explicit Currency: field or 3-letter code before amounts
    currency = _find(r"Currency\s*[:\-]\s*([A-Z]{3})", raw_text, "")
    if not currency:
        currency = _find(r"\b(INR|AED|USD|EUR|GBP|SGD|SAR|QAR|OMR|BHD|KWD)\b", raw_text, "AED")
    route = _find(r"Route\s*[:\-]\s*(.+?)(?:\n|$)", raw_text, "")
    if not route:
        # Try POL/POD pattern: "POL: X ... POD: Y"
        pol = _find(r"POL\s*[:\-]\s*(.+?)(?:\s{2,}|\n)", raw_text, "")
        pod = _find(r"POD\s*[:\-]\s*(.+?)(?:\s{2,}|\n)", raw_text, "")
        if pol and pod:
            route = f"{pol.strip()} to {pod.strip()}"

    missing_fields = []
    if not invoice_number:
        missing_fields.append("invoice_number")
    if not vendor_name:
        missing_fields.append("vendor_name")
    if amount == 0:
        missing_fields.append("amount_due")
    if not shipment_id and not mbl_number:
        missing_fields.append("shipment_id")

    confidence = 0.91 if (amount > 0 and charge_code and not missing_fields) else (
        0.72 if amount > 0 and charge_code else 0.45
    )

    return {
        "vendor_name": vendor_name or None,
        "invoice_number": invoice_number or None,
        "invoice_date": invoice_date,
        "service_provider_id": service_provider_id or None,
        "customer_number": customer_number or None,
        "mbl_number": mbl_number or None,
        "shipment_id": shipment_id or None,
        "charge_code": charge_code,
        "charge_description": code_data.get("description"),
        "invoice_type": code_data.get("invoice_type"),
        "invoice_category": code_data.get("category", "unknown"),
        "currency": currency,
        "amount_due": amount,
        "tax_type": tax_type,
        "vat_amount": vat_amount,
        "amount_due_with_vat": total_amount,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "route_or_port": route or None,
        "line_items": [
            {
                "line_item_sequence": 1,
                "charge_code": charge_code,
                "description": code_data.get("description", ""),
                "amount": amount,
                "currency": currency,
            }
        ],
        "missing_fields": missing_fields,
        "possible_errors": [],
        "confidence_score": confidence,
    }


def openai_parse_invoice(raw_text: str) -> dict:
    """Parse invoice using OpenAI with production-grade prompt and JSON validation."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def _call(prompt_text: str) -> dict:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    try:
        raw = _call(build_user_prompt(raw_text))
        validated = validate_extracted_json(raw)
        return validated.to_dict()
    except json.JSONDecodeError:
        try:
            raw = _call(build_repair_prompt(raw_text))
            validated = validate_extracted_json(raw)
            result = validated.to_dict()
            result["possible_errors"] = result.get("possible_errors", []) + ["JSON repair was needed"]
            return result
        except Exception as exc:
            fallback = mock_parse_invoice(raw_text)
            fallback["ai_fallback_reason"] = f"OpenAI JSON repair failed: {exc}"
            return fallback
    except Exception as exc:
        fallback = mock_parse_invoice(raw_text)
        fallback["ai_fallback_reason"] = f"OpenAI call failed: {exc}"
        return fallback


def parse_invoice(raw_text: str, mode: str = "mock") -> dict:
    """Route to OpenAI or mock parser. Always returns a valid dict."""
    if mode == "openai" and os.environ.get("OPENAI_API_KEY"):
        result = openai_parse_invoice(raw_text)
    else:
        result = mock_parse_invoice(raw_text)

    try:
        validated = validate_extracted_json(result)
        final = validated.to_dict()
        if result.get("ai_fallback_reason"):
            final["ai_fallback_reason"] = result["ai_fallback_reason"]
        return final
    except Exception:
        return result


def openai_parse_invoice_for_vendor(raw_text: str, vendor_id: str) -> dict:
    """Vendor-specific extraction using OpenAI with vendor-aware prompt."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def _call(system: str, user: str) -> dict:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    try:
        user_prompt = build_vendor_user_prompt(raw_text, vendor_id)
        raw = _call(VENDOR_SYSTEM_PROMPT, user_prompt)
        try:
            validated = validate_extracted_json(raw)
            result = validated.to_dict()
        except Exception:
            result = raw
        result["vendor_id"] = vendor_id
        result["_parsed_with"] = "vendor_openai"
        return result
    except Exception as exc:
        fallback = mock_parse_invoice(raw_text)
        fallback["vendor_id"] = vendor_id
        fallback["ai_fallback_reason"] = f"vendor OpenAI call failed: {exc}"
        fallback["_parsed_with"] = "mock_fallback"
        return fallback


def parse_invoice_for_vendor(
    raw_text: str,
    vendor_id: str = "UNKNOWN",
    mode: str = "mock",
) -> dict:
    """
    Vendor-aware extraction entry point.
    Uses vendor-specific prompt when vendor_id is known.
    Falls back to generic parser for UNKNOWN vendors.
    """
    if vendor_id and vendor_id != "UNKNOWN" and mode == "openai" and os.environ.get("OPENAI_API_KEY"):
        return openai_parse_invoice_for_vendor(raw_text, vendor_id)

    # Generic parse (mock or openai without vendor context)
    result = parse_invoice(raw_text, mode=mode)
    result["vendor_id"] = vendor_id
    result["_parsed_with"] = f"generic_{mode}"
    return result


# ── Regex patterns for smart auto-fill ────────────────────────────────────────
_INV_NO_PATS = [
    r"invoice\s*(?:no\.?|number|#|num\.?)\s*[:\-]?\s*([\w\-/]{3,30})",
    r"inv\.?\s*(?:no\.?|#)\s*[:\-]?\s*([\w\-/]{3,20})",
    r"bill\s*(?:no\.?|number)\s*[:\-]?\s*([\w\-/]{3,20})",
    r"ref\.?\s*(?:no\.?|#)?\s*[:\-]?\s*([\w\-/]{4,20})",
]
_AMOUNT_PATS = [
    r"total\s*(?:amount|due|payable)\s*[:\-]?\s*(?:AED|USD|EUR|GBP|INR)?\s*([\d,]+\.?\d*)",
    r"amount\s*(?:due|payable)\s*[:\-]?\s*(?:AED|USD|EUR|GBP|INR)?\s*([\d,]+\.?\d*)",
    r"grand\s*total\s*[:\-]?\s*(?:AED|USD|EUR|GBP|INR)?\s*([\d,]+\.?\d*)",
    r"net\s*(?:amount|total)\s*[:\-]?\s*(?:AED|USD|EUR|GBP|INR)?\s*([\d,]+\.?\d*)",
    r"(?:AED|USD|EUR|GBP|INR)\s+([\d,]+\.\d{2})\b",
    r"\b([\d,]+\.\d{2})\s*(?:AED|USD|EUR|GBP|INR)\b",
]
_VAT_PATS = [
    r"(?:vat|tax|gst)\s*(?:amount|@\s*\d+%?)?\s*[:\-]?\s*(?:AED|USD|EUR)?\s*([\d,]+\.?\d*)",
    r"(?:5%|18%)\s*(?:vat|gst|tax)\s*[:\-]?\s*(?:AED|USD|EUR)?\s*([\d,]+\.?\d*)",
]
_DATE_PATS = [
    r"(?:invoice\s*)?date\s*[:\-]?\s*(\d{1,2}[\s\-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-/]\d{2,4})",
    r"(?:invoice\s*)?date\s*[:\-]?\s*(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})",
    r"(?:invoice\s*)?date\s*[:\-]?\s*(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})",
    r"dated?\s*[:\-]?\s*(\d{1,2}[\s\-/]\w+[\s\-/]\d{2,4})",
]
_MBL_PATS = [
    r"(?:mbl|master\s*b/?l|bill\s*of\s*lading)\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Z0-9]{8,20})",
    r"(?:awb|air\s*waybill)\s*(?:no\.?|#)?\s*[:\-]?\s*(\d[\d\s]{7,14})",
    r"(?:b/?l|swb)\s*(?:no\.?|#)?\s*[:\-]?\s*([A-Z0-9]{8,20})",
]
_CURRENCY_PAT = r"\b(AED|USD|EUR|GBP|INR|SAR|QAR|KWD|BHD|OMR)\b"
_CONTAINER_PAT = r"\b([A-Z]{4}\d{7})\b"
_CUST_NO_PATS = [
    r"(?:customer|client|account|cust\.?)\s*(?:no\.?|number|#|id|code)\s*[:\-]?\s*([\w\-]{4,20})",
]


def smart_refill_missing_fields(
    raw_text: str,
    extracted: dict,
    vendor_id: str = "UNKNOWN",
) -> dict:
    """
    Regex-based auto-fill for fields the AI missed.
    Returns a dict of only the fields that were empty and now have a value.
    Runs in the pipeline after AI extraction AND on-demand in Review Queue.
    """
    filled: dict = {}
    t = raw_text or ""

    def _try(pats: list, key: str) -> str:
        for pat in pats:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    # Invoice number
    if not extracted.get("invoice_number"):
        val = _try(_INV_NO_PATS, "invoice_number")
        skip = {"no", "date", "ref", "num", "number", "invoice"}
        if val and val.lower() not in skip and len(val) >= 3:
            filled["invoice_number"] = val

    # Invoice date
    if not extracted.get("invoice_date"):
        val = _try(_DATE_PATS, "invoice_date")
        if val:
            filled["invoice_date"] = val

    # Currency
    if not extracted.get("currency"):
        m = re.search(_CURRENCY_PAT, t)
        if m:
            filled["currency"] = m.group(1).upper()

    # Amount due (only if zero or missing)
    cur_amt = float(extracted.get("amount_due") or 0)
    if cur_amt == 0:
        for pat in _AMOUNT_PATS:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                try:
                    amt = float(m.group(1).replace(",", ""))
                    if amt > 0:
                        filled["amount_due"] = round(amt, 2)
                        break
                except Exception:
                    pass

    # VAT amount
    if not extracted.get("vat_amount") or float(extracted.get("vat_amount") or 0) == 0:
        val = _try(_VAT_PATS, "vat_amount")
        if val:
            try:
                filled["vat_amount"] = round(float(val.replace(",", "")), 2)
            except Exception:
                pass

    # MBL / AWB
    if not extracted.get("mbl_number") and not extracted.get("awb_number"):
        val = _try(_MBL_PATS, "mbl_number")
        if val:
            filled["mbl_number"] = val.upper().replace(" ", "")

    # Container number
    if not extracted.get("container_number"):
        m = re.search(_CONTAINER_PAT, t)
        if m:
            filled["container_number"] = m.group(1)

    # Customer number
    if not extracted.get("customer_number"):
        val = _try(_CUST_NO_PATS, "customer_number")
        if val:
            filled["customer_number"] = val

    # Vendor name from registry when AI left it blank
    if not extracted.get("vendor_name") and vendor_id and vendor_id != "UNKNOWN":
        try:
            from .vendor_registry import get_vendor
            vinfo = get_vendor(vendor_id)
            if vinfo and vinfo.get("name"):
                filled["vendor_name"] = vinfo["name"]
        except Exception:
            pass

    # Recalculate total if we filled both amount and vat
    if "amount_due" in filled or "vat_amount" in filled:
        base = filled.get("amount_due") or float(extracted.get("amount_due") or 0)
        vat  = filled.get("vat_amount") or float(extracted.get("vat_amount") or 0)
        cur_total = float(extracted.get("amount_due_with_vat") or 0)
        if base > 0 and cur_total == 0:
            filled["amount_due_with_vat"] = round(base + vat, 2)

    return filled
