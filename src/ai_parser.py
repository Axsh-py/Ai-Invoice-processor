import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .prompts.invoice_parser_prompt import SYSTEM_PROMPT, build_user_prompt, build_repair_prompt
from .prompts.invoice_parser_prompt import build_vendor_user_prompt, VENDOR_SYSTEM_PROMPT
from .schemas import validate_extracted_json
from .config import get_secret


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


def _vendor_overrides(t: str, vendor_id: str) -> dict:
    """
    Vendor-specific regex extraction — runs after generic mock_parse_invoice and
    fills / corrects fields that the generic parser misses or gets wrong.
    Returns only keys whose values are non-None.
    """
    out: dict = {}

    def _m1(pat: str, flags: int = re.IGNORECASE) -> Optional[str]:
        r = re.search(pat, t, flags)
        return r.group(1).strip() if r else None

    if vendor_id in ("HAPAG_LLOYD", "HAPAG_LLOYD_INDIA"):
        # 10-digit invoice number (distinct from 15-digit HLCU BL)
        out["invoice_number"] = _m1(r"(?<!\d)(\d{10})(?!\d)")
        # HLCU BL — 2-3 uppercase letters after HLCU then 6+ digits
        out["mbl_number"]      = _m1(r"\b(HLCU[A-Z]{2,3}\d{6,}[A-Z]?)\b")
        out["bl_number"]       = out["mbl_number"]
        # 8-digit customer number (starts with 5 or 9 for Hapag accounts)
        out["customer_number"] = _m1(r"\b([59]\d{7})\b")
        # "FROM [City/Port] TO [City/Port]" route
        _rt = re.search(r"\bFROM\s+([A-Z][A-Za-z ,\(\)]+?)\s+TO\s+([A-Z][A-Za-z ,\(\)]+?)(?=\s*\n|\s{2,}|$)",
                        t, re.IGNORECASE)
        if _rt:
            out["origin_port"]      = _rt.group(1).strip()
            out["destination_port"] = _rt.group(2).strip()
        # Vessel: "VESSEL NAME" before a voyage number block
        out["vessel_name"]  = _m1(r"[Vv]essel\s*[:\-]\s*(.+?)(?:\n|$)")
        out["voyage_number"] = _m1(r"[Vv]oyage\s*(?:No\.?|Code)?\s*[:\-]\s*([A-Z0-9]{4,12})")

    elif vendor_id == "MSC":
        out["invoice_number"]  = _m1(r"\b(AE[JK][A-Z]+PM\d{9,})\b")
        out["bl_number"]       = _m1(r"\b(MSCU\d{7,}|MEDU\d{7,})\b")
        out["mbl_number"]      = out["bl_number"]
        out["customer_number"] = _m1(r"\b(1000\d{6,})\b")
        out["container_number"]= _m1(r"\b(MSCU\d{7}|MEDU\d{7})\b")

    elif vendor_id == "CMA_CGM":
        out["invoice_number"]  = _m1(r"\b(AEIM\d{7,})\b")
        out["container_number"]= _m1(r"\b(CMAU\d{7}|CMAL\d{7}|CGMU\d{7})\b")
        out["mbl_number"]      = out["container_number"]
        out["bl_number"]       = out["container_number"]

    elif vendor_id == "MAERSK":
        out["mbl_number"]      = _m1(r"\b(MAEU\d{7,}|MAES\d{7,}|MRKU\d{7,}|MSKU\d{7,})\b")
        out["bl_number"]       = out["mbl_number"]
        out["container_number"]= _m1(r"\b(MRKU\d{7}|MSKU\d{7})\b")
        # Maersk invoice numbers often alphanumeric, 8-12 chars
        out["invoice_number"]  = _m1(r"[Ii]nvoice\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9\-]{6,15})")

    elif vendor_id == "EMIRATES_SKYCARGO":
        awb = _m1(r"\b(176[\s\-]\d{8})\b")
        if awb:
            out["awb_number"] = awb
            out["mbl_number"] = awb
        out["customer_number"] = "WALKIAEDXB"

    elif vendor_id == "CALOGI":
        out["invoice_number"]  = _m1(r"\b(DXBCAIN\d{8,})\b")
        out["customer_number"] = "DCL146"
        awb = _m1(r"\b(176[-\s]\d{8})\b")
        if awb:
            out["mbl_number"] = awb.replace(" ", "-")

    elif vendor_id == "BENGAL_AIRLIFT":
        out["invoice_number"] = _m1(r"\b(DRN\d{8,}[A-Z])\b")
        out["currency"]       = "USD"
        # MBL from any known carrier format
        out["mbl_number"]     = _m1(r"\b(MAEU\d{7,}|MSCU\d{7,}|HLCU[A-Z]{2,}\d{6,}|COSU\d{7,})\b")

    elif vendor_id == "GREEN_WAY_CARGO":
        out["invoice_number"] = _m1(r"\b(INV-0\d{5,})\b")
        # BOE number embedded in description: "BOE No: 102-XXXXXXXX-XX"
        out["invoice_number"] = out.get("invoice_number") or _m1(r"\b(INV[\-\s]?\d{4,})\b")

    elif vendor_id == "RAVIAN_SHIPPING":
        out["invoice_number"] = _m1(r"\b(JI-\d+/\d{2,4})\b")
        out["mbl_number"]     = _m1(r"\b(MSCU\d{7,}|HLCU[A-Z]{2,}\d{6,}|COSU\d{7,}|MAEU\d{7,})\b")
        out["bl_number"]      = out["mbl_number"]

    elif vendor_id == "ADSO_LLC":
        out["invoice_number"] = _m1(r"\b(26\d{5})\b")  # 7-digit 26XXXXX format
        out["mbl_number"]     = _m1(r"\b([A-Z]{4}\d{9,}[A-Z]?)\b")

    elif vendor_id == "SEACOAST_LOGISTICS":
        out["invoice_number"] = _m1(r"\b(\d{9}-\d{2}-\d)\b")
        awb = _m1(r"\b(176[-\s]\d{8})\b")
        if awb:
            out["mbl_number"] = awb

    elif vendor_id == "UAE_CUSTOMS_BOE":
        out["invoice_number"] = _m1(r"\b((102|101|303)-\d{8}-\d{2})\b")

    elif vendor_id == "DUBAI_CUSTOMS_EREVENUE":
        out["customer_number"] = "AE-1151728"

    elif vendor_id == "DP_WORLD":
        out["invoice_number"] = _m1(r"[Rr]eceipt\s*[Nn]o\.?\s*[:\-]?\s*([A-Z0-9\-/]+)")

    elif vendor_id == "ABU_DHABI_PORTS":
        out["invoice_number"] = _m1(r"[Rr]eceipt\s*(?:[Vv]oucher\s*)?[Nn]o\.?\s*[:\-]?\s*([A-Z0-9\-/]+)")

    elif vendor_id == "FIRST_FLIGHT_COURIERS":
        out["customer_number"] = "16082"
        out["invoice_number"]  = _m1(r"\b(\d{6})\b")

    return {k: v for k, v in out.items() if v is not None}


def mock_parse_invoice(raw_text: str, vendor_id: str = "UNKNOWN") -> dict:
    """Deterministic regex-based parser — works without any API key."""
    charge_master = _load_charge_master()
    charge_code = _find(r"Charge\s*Code\s*[:\-]\s*([A-Z0-9]+)", raw_text, "")
    if not charge_code:
        for code in charge_master:
            if code in raw_text:
                charge_code = code
                break
    if not charge_code:
        _tbl = re.search(r"\n([A-Z]{3,5})\n([0-9,]+\.[0-9]{2})", raw_text)
        _currencies = {"AED", "USD", "EUR", "GBP", "INR", "VAT"}
        if _tbl and _tbl.group(1) not in _currencies:
            charge_code = _tbl.group(1)
    # Intentionally leave None — pipeline/vendor-registry will set vendor-specific code.
    # Do NOT default to "AFRT" here; that would block vendor-registry override.

    # Try to extract raw charge description from table row (e.g. "1  ADMIN FEES  AED 1500.00")
    raw_charge_desc = _find(
        r"\b\d+\s+([A-Z][A-Z\s&/\-]{3,40}?)(?:\s{2,}|\s+(?:AED|USD|EUR|INR)|\s+[\d,]+\.)",
        raw_text, "")

    code_data = charge_master.get(charge_code or "", {})

    # ── Amount extraction — handles "Label: AED 1500.00" and plain numeric formats ──
    amount_str = _find(
        r"(?:Freight\s*Charge|Charge\s*Amount|Amount\s*Due|Net\s*Amount)"
        r"\s*[:\-]\s*\n?\s*(?:[A-Z]{3}\s*)?([0-9,]+\.?[0-9]*)", raw_text, "")
    if not amount_str:
        # "Gross Amount Payable: AED 1500.00" / "Total Amount: AED 1500.00"
        amount_str = _find(
            r"(?:Gross\s*Amount\s*Payable|Total\s*Amount|Grand\s*Total)"
            r"\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9,]+\.?[0-9]*)", raw_text, "")
    if not amount_str:
        amount_str = re.search(rf"{re.escape(charge_code)}\s*\n\s*([0-9,]+\.?[0-9]*)",
                               raw_text, re.IGNORECASE)
        amount_str = amount_str.group(1) if amount_str else "0"
    amount = float(amount_str.replace(",", "") or 0)

    # ── GST components (Indian invoices) ──────────────────────────────────────
    cgst_str = _find(r"(?:IN:\s*)?Central\s*GST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    sgst_str = _find(r"(?:IN:\s*)?State\s*GST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    igst_str = _find(r"IGST[^0-9\n]*([0-9,]+\.?[0-9]*)", raw_text, "")
    cgst_amount: Optional[float] = float(cgst_str.replace(",", "")) if cgst_str else None
    sgst_amount: Optional[float] = float(sgst_str.replace(",", "")) if sgst_str else None
    igst_amount: Optional[float] = float(igst_str.replace(",", "")) if igst_str else None

    has_gst = bool(cgst_str or sgst_str or igst_str or re.search(r"\bGST\b", raw_text))
    has_vat = bool(re.search(r"\bVAT\b", raw_text))
    tax_type = "GST" if has_gst else ("VAT" if has_vat else "NONE")

    if cgst_amount is not None or sgst_amount is not None:
        vat_amount: Optional[float] = round((cgst_amount or 0) + (sgst_amount or 0), 2)
    elif igst_amount is not None:
        vat_amount = igst_amount
    else:
        # Handles "Tax Amount Payable: AED 0.00" and plain "VAT: 75.00"
        vat_str = _find(
            r"(?:Tax\s*Amount\s*Payable|VAT\s*Amount|Tax\s*Amount|VAT)"
            r"\s*(?:Payable)?\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9,]+\.?[0-9]*)",
            raw_text, "")
        vat_amount = float(vat_str.replace(",", "")) if vat_str else None

    total_str = _find(
        r"(?:Gross\s*Amount\s*Payable|Grand\s*Total|Total\s*Due|Amount\s*Due)"
        r"\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9,]+\.?[0-9]*)", raw_text, "")
    total_amount: Optional[float] = float(total_str.replace(",", "")) if total_str else None

    # ── Invoice number ────────────────────────────────────────────────────────
    invoice_number = _find(
        r"Invoice\s*(?:No|Number|#)\s*[:\-]?\s*\n?\s*([A-Z0-9][A-Z0-9\/\-]{2,})",
        raw_text, "")
    if not invoice_number:
        invoice_number = _find(
            r"(?:Ref|Reference)\s*[:\-]\s*([A-Z0-9\/\-]*[0-9][A-Z0-9\/\-]*)",
            raw_text, "")

    # ── MBL / Bill of Lading ─────────────────────────────────────────────────
    # Cross-line first: "B/L Number : Validity:\nCOSU6442960720W"
    mbl_number = ""
    for _pat in [
        r"B/?L\s*(?:No\.?|Number|#)?\s*[:\-][^\n]*\n\s*([A-Z]{2,4}[0-9]{7,}[A-Z]?)",
        r"(?:Bill\s*of\s*Lading|MBL|HBL)\s*[:\-]?\s*\n?\s*([A-Z]{2,4}[0-9]{7,}[A-Z]?)",
    ]:
        _m = re.search(_pat, raw_text, re.IGNORECASE)
        if _m:
            mbl_number = _m.group(1).strip()
            break

    # ── Vessel name ──────────────────────────────────────────────────────────
    # Cross-line: "Vessel/Voy:\n0MDG0E1MA CMA CGM NEVADA 0MDG0E1MA"
    # Skip first token (voyage code), capture all-caps words until next code
    _vm = re.search(
        r"Vessel\s*(?:/\s*Voy)?\s*[:\-][^\n]*\n\s*\S+\s+((?:[A-Z][A-Z]* ){1,5}[A-Z]+)",
        raw_text)
    if _vm:
        vessel_name = _vm.group(1).strip()
    else:
        vessel_name = _find(
            r"Vessel\s*(?:/\s*Voy(?:age)?)?\s*[:\-]\s*([A-Z][A-Z0-9 ]{3,40?}?)"
            r"(?:\s+[0-9A-Z]{6,}|\n|$)",
            raw_text, "")
        if not vessel_name:
            vessel_name = _find(r"Vessel\s*[:\-]\s*(.+?)(?:\n|$)", raw_text, "")

    # ── Voyage number ─────────────────────────────────────────────────────────
    # Cross-line: "Voyage Code :\n0MDG0E1MA CMA CGM NEVADA..."
    voyage_number = _find(
        r"Voyage\s*(?:Code|No\.?|Number)?\s*[:\-][^\n]*\n\s*([A-Z0-9]{5,15})", raw_text, "")
    if not voyage_number:
        voyage_number = _find(
            r"Voyage\s*(?:Code|No\.?|Number)?\s*[:\-]\s*([A-Z0-9]{5,15})", raw_text, "")

    # ── POL / POD — value may be on the same or next line ────────────────────
    pol = _find(r"POL\s*[:\-]\s*([A-Za-z][A-Za-z ]{2,30})(?:\n|\s{2,}|POD|$)",
                raw_text, "")
    pod = _find(r"POD\s*[:\-]\s*([A-Za-z][A-Za-z ]{2,30})(?:\n|\s{2,}|FPD|$)",
                raw_text, "")
    # Fallback: labels on one line, values on next line
    # "POL: POD: FPD:\nQingdao Jebel Ali Jebel Ali"
    if not pol:
        _m = re.search(r"POL\s*:\s*POD\s*:.*?\n(.*?)(?:\n|$)", raw_text, re.DOTALL)
        if _m:
            _words = _m.group(1).strip().split()
            _n = len(_words)
            # Detect repeated trailing suffix (FPD usually equals POD)
            _found = False
            for _sfx in range(1, _n // 2 + 1):
                if _words[-_sfx:] == _words[-2 * _sfx:-_sfx]:
                    pod = " ".join(_words[-_sfx:])
                    pol = " ".join(_words[:_n - 2 * _sfx]) or _words[0]
                    _found = True
                    break
            if not _found:
                pol = _words[0] if _words else ""
                pod = " ".join(_words[1:]) if len(_words) > 1 else ""

    route = _find(r"Route\s*[:\-]\s*(.+?)(?:\n|$)", raw_text, "")
    if not route and pol and pod:
        route = f"{pol.strip()} to {pod.strip()}"

    # ── Container number — 3–4 letter owner code + 6–7 digits ────────────────
    container_number = _find(r"\b([A-Z]{3,4}[0-9]{6,7})\b", raw_text, "")

    # ── Customer / Account number ─────────────────────────────────────────────
    customer_number = _find(
        r"(?:Customer\s*(?:No\.?|Number|ID|#)|Account\s*(?:No\.?|Number)|Client\s*(?:No\.?|#|Code))"
        r"\s*[:\-]?\s*([A-Z0-9]{4,20})", raw_text, "")

    # ── Vendor name ───────────────────────────────────────────────────────────
    vendor_name = _find(r"Vendor\s*[:\-]\s*(.+)", raw_text, "")
    if not vendor_name:
        vendor_name = _find(r"(?:On\s*behalf\s*of|Issued\s*by)\s*[:\-]\s*(.+)", raw_text, "")

    invoice_date = _find(r"Invoice\s*Date\s*[:\-]\s*([0-9A-Za-z\-\.\/ ]+)", raw_text,
                         datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"))
    service_provider_id = _find(r"Service\s*Provider\s*ID\s*[:\-]\s*([A-Z0-9\.]+)", raw_text, "")
    shipment_id = _find(r"Shipment\s*ID\s*[:\-]\s*([A-Z0-9\-]+)", raw_text, "")

    currency = _find(r"Currency\s*[:\-]\s*([A-Z]{3})", raw_text, "")
    if not currency:
        currency = _find(r"\b(INR|AED|USD|EUR|GBP|SGD|SAR|QAR|OMR|BHD|KWD)\b", raw_text, "AED")

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

    # ── Apply vendor-specific overrides for fields generic parser missed ────────
    _ov = _vendor_overrides(raw_text, vendor_id)
    if _ov.get("invoice_number") and not invoice_number:
        invoice_number = _ov["invoice_number"]
    if _ov.get("mbl_number") and not mbl_number:
        mbl_number = _ov["mbl_number"]
    if _ov.get("bl_number") and not mbl_number:
        mbl_number = _ov["bl_number"]
    if _ov.get("awb_number") and not mbl_number:
        mbl_number = _ov["awb_number"]
    if _ov.get("customer_number") and not customer_number:
        customer_number = _ov["customer_number"]
    if _ov.get("container_number") and not container_number:
        container_number = _ov["container_number"]
    if _ov.get("vessel_name") and not vessel_name:
        vessel_name = _ov["vessel_name"]
    if _ov.get("voyage_number") and not voyage_number:
        voyage_number = _ov["voyage_number"]
    if _ov.get("origin_port") and not pol:
        pol = _ov["origin_port"]
    if _ov.get("destination_port") and not pod:
        pod = _ov["destination_port"]
    if _ov.get("currency") and not currency:
        currency = _ov["currency"]
    # route rebuild after overrides
    if not route and pol and pod:
        route = f"{pol.strip()} to {pod.strip()}"

    return {
        "vendor_name":         vendor_name or None,
        "invoice_number":      invoice_number or None,
        "invoice_date":        invoice_date,
        "service_provider_id": service_provider_id or None,
        "customer_number":     customer_number or None,
        "mbl_number":          mbl_number or None,
        "bl_number":           mbl_number or None,
        "awb_number":          _ov.get("awb_number") or None,
        "shipment_id":         shipment_id or None,
        "vessel_name":         vessel_name or None,
        "voyage_number":       voyage_number or None,
        "origin_port":         pol or None,
        "destination_port":    pod or None,
        "container_number":    container_number or None,
        "charge_code":         charge_code or None,
        "charge_description":  raw_charge_desc or code_data.get("description") or None,
        "invoice_type":        code_data.get("invoice_type"),
        "invoice_category":    code_data.get("category", "unknown"),
        "currency":            currency,
        "amount_due":          amount,
        "tax_type":            tax_type,
        "vat_amount":          vat_amount,
        "amount_due_with_vat": total_amount,
        "cgst_amount":         cgst_amount,
        "sgst_amount":         sgst_amount,
        "igst_amount":         igst_amount,
        "route_or_port":       route or None,
        "line_items": [
            {
                "line_item_sequence": 1,
                "charge_code":   charge_code or "AFRT",
                "description":   raw_charge_desc or code_data.get("description", ""),
                "amount":        amount,
                "currency":      currency,
            }
        ],
        "missing_fields":   missing_fields,
        "possible_errors":  [],
        "confidence_score": confidence,
    }


def openai_parse_invoice(raw_text: str) -> dict:
    """Parse invoice using OpenAI with production-grade prompt and JSON validation."""
    import httpx
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"), http_client=httpx.Client())

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


def parse_invoice(raw_text: str, mode: str = "mock", vendor_id: str = "UNKNOWN") -> dict:
    """Route to OpenAI or mock parser. Always returns a valid dict."""
    if mode == "openai" and os.environ.get("OPENAI_API_KEY"):
        result = openai_parse_invoice(raw_text)
    else:
        result = mock_parse_invoice(raw_text, vendor_id=vendor_id)

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
    import httpx
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"), http_client=httpx.Client())

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
        fallback = mock_parse_invoice(raw_text, vendor_id=vendor_id)
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

    # Generic parse (mock or openai without vendor context) — pass vendor_id so mock uses specific patterns
    result = parse_invoice(raw_text, mode=mode, vendor_id=vendor_id)
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
_CONTAINER_PAT = r"\b([A-Z]{3,4}[0-9]{6,7})\b"
_VESSEL_PATS = [
    # Cross-line: "Vessel/Voy:\n0MDG0E1MA CMA CGM NEVADA 0MDG0E1MA"
    r"[Vv]essel\s*(?:/\s*[Vv]oy)?\s*[:\-][^\n]*\n\s*\S+\s+((?:[A-Z][A-Z]* ){1,5}[A-Z]+)",
    # Same-line: "Vessel/Voy: CMA CGM NEVADA 0MDG0E1MA" — stop before voyage code
    r"[Vv]essel\s*(?:/\s*[Vv]oy(?:age)?)?\s*[:\-]\s*([A-Z][A-Z0-9 ]{3,40?}?)(?:\s+[A-Z0-9]{6,}|\n|$)",
    r"[Vv]essel\s*[Nn]ame\s*[:\-]\s*(.+?)(?:\n|$)",
]
_VOYAGE_PATS = [
    # Cross-line: "Voyage Code :\n0MDG0E1MA CMA CGM NEVADA..."
    r"[Vv]oyage\s*(?:[Cc]ode|[Nn]o\.?|[Nn]umber)?\s*[:\-][^\n]*\n\s*([A-Z0-9]{5,15})",
    r"[Vv]oyage\s*(?:[Cc]ode|[Nn]o\.?|[Nn]umber)?\s*[:\-]\s*([A-Z0-9]{5,15})",
    r"[Vv]oy\.?\s*[:\-]\s*([A-Z0-9]{5,15})",
]
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

    # MBL / AWB — also try direct carrier-code patterns (COSU, HLCU, MSCU…)
    if not extracted.get("mbl_number") and not extracted.get("awb_number"):
        val = _try(_MBL_PATS, "mbl_number")
        if not val:
            # Require exactly 4 uppercase letters + 9+ digits to avoid matching
            # invoice numbers like "INV2603001533" (only 3 letters)
            _m = re.search(r"\b([A-Z]{4}[0-9]{9,}[A-Z]?)\b", t)
            if _m:
                val = _m.group(1)
        if val:
            filled["mbl_number"] = val.upper().replace(" ", "")

    # Vessel name
    if not extracted.get("vessel_name"):
        val = _try(_VESSEL_PATS, "vessel_name")
        if val:
            filled["vessel_name"] = val.strip()

    # Voyage number
    if not extracted.get("voyage_number"):
        val = _try(_VOYAGE_PATS, "voyage_number")
        if val:
            filled["voyage_number"] = val.strip()

    # Container number — 3-4 letter prefix + 6-7 digits
    if not extracted.get("container_number"):
        m = re.search(_CONTAINER_PAT, t)
        if m:
            filled["container_number"] = m.group(1)

    # Customer number
    if not extracted.get("customer_number"):
        val = _try(_CUST_NO_PATS, "customer_number")
        if val:
            filled["customer_number"] = val
        else:
            # Bare TRN/account number below "Invoice to:" address block (COSCO-style)
            _cm = re.search(
                r"Invoice\s+[Tt]o[^\n]*\n(?:[^\n]+\n){1,4}(\d{8,12})\s*(?:\n|$)",
                t)
            if _cm:
                filled["customer_number"] = _cm.group(1)

    # Vendor name from registry when AI left it blank
    if not extracted.get("vendor_name") and vendor_id and vendor_id != "UNKNOWN":
        try:
            from .vendor_registry import get_vendor
            vinfo = get_vendor(vendor_id)
            if vinfo and vinfo.get("name"):
                filled["vendor_name"] = vinfo["name"]
        except Exception:
            pass

    # ── Vendor-specific smart-refill overrides ────────────────────────────────
    def _needfill(key: str) -> bool:
        return not extracted.get(key) and key not in filled

    if vendor_id in ("HAPAG_LLOYD", "HAPAG_LLOYD_INDIA"):
        if _needfill("mbl_number"):
            _m = re.search(r"\b(HLCU[A-Z]{2,3}\d{6,}[A-Z]?)\b", t)
            if _m: filled["mbl_number"] = _m.group(1)
        if _needfill("bl_number"):
            filled["bl_number"] = filled.get("mbl_number") or extracted.get("mbl_number")
        if _needfill("customer_number"):
            _m = re.search(r"\b([59]\d{7})\b", t)
            if _m: filled["customer_number"] = _m.group(1)
        if _needfill("origin_port") or _needfill("destination_port"):
            _rt = re.search(r"\bFROM\s+([A-Z][A-Za-z ,]+?)\s+TO\s+([A-Z][A-Za-z ,]+?)(?=\s*\n|\s{2,}|$)", t, re.IGNORECASE)
            if _rt:
                if _needfill("origin_port"):      filled["origin_port"]      = _rt.group(1).strip()
                if _needfill("destination_port"): filled["destination_port"] = _rt.group(2).strip()

    elif vendor_id == "MSC":
        if _needfill("invoice_number"):
            _m = re.search(r"\b(AE[JK][A-Z]+PM\d{9,})\b", t)
            if _m: filled["invoice_number"] = _m.group(1)
        if _needfill("mbl_number"):
            _m = re.search(r"\b(MSCU\d{7,}|MEDU\d{7,})\b", t)
            if _m: filled["mbl_number"] = _m.group(1); filled["bl_number"] = _m.group(1)
        if _needfill("customer_number"):
            _m = re.search(r"\b(1000\d{6,})\b", t)
            if _m: filled["customer_number"] = _m.group(1)

    elif vendor_id == "CMA_CGM":
        if _needfill("invoice_number"):
            _m = re.search(r"\b(AEIM\d{7,})\b", t)
            if _m: filled["invoice_number"] = _m.group(1)
        if _needfill("container_number"):
            _m = re.search(r"\b(CMAU\d{7}|CMAL\d{7}|CGMU\d{7})\b", t)
            if _m: filled["container_number"] = _m.group(1)

    elif vendor_id == "MAERSK":
        if _needfill("mbl_number"):
            _m = re.search(r"\b(MAEU\d{7,}|MAES\d{7,}|MRKU\d{7,}|MSKU\d{7,})\b", t)
            if _m: filled["mbl_number"] = _m.group(1); filled["bl_number"] = _m.group(1)
        if _needfill("container_number"):
            _m = re.search(r"\b(MRKU\d{7}|MSKU\d{7})\b", t)
            if _m: filled["container_number"] = _m.group(1)

    elif vendor_id == "EMIRATES_SKYCARGO":
        if _needfill("awb_number"):
            _m = re.search(r"\b(176[\s\-]\d{8})\b", t)
            if _m:
                filled["awb_number"] = _m.group(1)
                if _needfill("mbl_number"): filled["mbl_number"] = _m.group(1)

    elif vendor_id == "CALOGI":
        if _needfill("invoice_number"):
            _m = re.search(r"\b(DXBCAIN\d{8,})\b", t)
            if _m: filled["invoice_number"] = _m.group(1)
        if _needfill("mbl_number"):
            _m = re.search(r"\b(176[-\s]\d{8})\b", t)
            if _m: filled["mbl_number"] = _m.group(1).replace(" ", "-")

    elif vendor_id == "BENGAL_AIRLIFT":
        if _needfill("invoice_number"):
            _m = re.search(r"\b(DRN\d{8,}[A-Z])\b", t)
            if _m: filled["invoice_number"] = _m.group(1)
        if _needfill("currency"):
            filled["currency"] = "USD"

    elif vendor_id == "UAE_CUSTOMS_BOE":
        if _needfill("invoice_number"):
            _m = re.search(r"\b((102|101|303)-\d{8}-\d{2})\b", t)
            if _m: filled["invoice_number"] = _m.group(1)

    # Recalculate total if we filled both amount and vat
    if "amount_due" in filled or "vat_amount" in filled:
        base = filled.get("amount_due") or float(extracted.get("amount_due") or 0)
        vat  = filled.get("vat_amount") or float(extracted.get("vat_amount") or 0)
        cur_total = float(extracted.get("amount_due_with_vat") or 0)
        if base > 0 and cur_total == 0:
            filled["amount_due_with_vat"] = round(base + vat, 2)

    return filled
