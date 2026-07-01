import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .prompts.invoice_parser_prompt import SYSTEM_PROMPT, build_user_prompt, build_repair_prompt
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
