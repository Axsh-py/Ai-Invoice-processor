import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Company division prefix used in OTM Document IDs
# Format: TW/DWCLLC/DXB.[VENDOR_DOC_NO]
_OTM_COMPANY_PREFIX = "TW/DWCLLC/DXB"


def _otm_document_id(extracted: Dict[str, Any]) -> str:
    """
    Build OTM-style Document ID: TW/DWCLLC/DXB.[VENDOR_DOC_NO]

    Vendor document number priority:
      1. MBL/AWB/SWB number (most unique reference on the document)
      2. Invoice number (the vendor's own invoice reference)
    Spaces/special chars normalized to hyphens.
    """
    doc_no = (
        extracted.get("mbl_number")
        or extracted.get("awb_number")
        or extracted.get("invoice_number")
        or uuid.uuid4().hex[:10].upper()
    )
    doc_no_clean = re.sub(r"[\s/\\]+", "-", str(doc_no)).strip("-")
    return f"{_OTM_COMPANY_PREFIX}.{doc_no_clean}"


def _map_charge_to_otm_code(description: str, vendor_id: str, fallback_code: str) -> str:
    """
    Map a charge description to an OTM accessorial code using the vendor's charge_code_map.
    Falls back to the invoice-level charge_code if no match found.
    """
    if not description:
        return fallback_code or "OFR"
    try:
        from .vendor_registry import get_vendor
        vendor = get_vendor(vendor_id) or {}
        cmap = vendor.get("charge_code_map", {})
        desc_lower = description.lower().strip()
        # Exact and substring match against charge_code_map keys
        for key, code in cmap.items():
            if key == "default":
                continue
            if key in desc_lower or desc_lower in key:
                return code
        return cmap.get("default") or fallback_code or "OFR"
    except Exception:
        return fallback_code or "OFR"


def _build_line_items(
    extracted: Dict[str, Any],
    validation: Dict[str, Any],
    shipment: Dict[str, Any],
    sp: Dict[str, Any],
    charge: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Build OTM line items from extracted data.

    If the AI extracted individual charge lines (line_items), use each one.
    Otherwise fall back to a single line with the invoice total.
    """
    vendor_id = extracted.get("vendor_id", "UNKNOWN")
    fallback_code = extracted.get("charge_code", "")
    preprocess_status = validation.get("match_status", "EXCEPTION_REVIEW")
    matched_shp_id = shipment.get("shipment_id", "")
    matched_route = shipment.get("route", "")
    matched_sp_name = sp.get("name") or shipment.get("vendor_name", "")
    transport_unit = shipment.get("transport_handling_unit", "")
    v_status = validation.get("validation_status", "")
    adj_reason = "; ".join(validation.get("warnings", [])) if v_status != "PASSED" else ""

    raw_items = extracted.get("line_items") or []

    # Use extracted line items when they have real charge descriptions + amounts
    if raw_items and any(item.get("amount") for item in raw_items):
        items = []
        for i, item in enumerate(raw_items, start=1):
            desc = item.get("description") or item.get("charge_code") or "Charge"
            item_amount = float(item.get("amount") or 0)
            item_currency = item.get("currency") or extracted.get("currency") or "AED"
            # Map description → OTM accessorial code via vendor's charge_code_map
            acc_code = item.get("charge_code") or _map_charge_to_otm_code(desc, vendor_id, fallback_code)
            # Determine cost type from charge master
            cost_type = "Freight"
            try:
                from .matcher import match_charge_code
                cc_info = match_charge_code(acc_code)
                if cc_info:
                    cost_type = cc_info.get("cost_type", "Freight")
            except Exception:
                pass

            items.append({
                "line_item_sequence": i,
                "cost_type": cost_type,
                "charge_description": desc,
                "unit_count": item.get("qty") or item.get("unit_count") or 1,
                "unit_of_measure": item.get("unit") or "FLAT",
                "currency": item_currency,
                "base_charge": item_amount,
                "accessorial_code": acc_code,
                "transport_handling_unit": transport_unit,
                "preprocess_status": preprocess_status,
                "adjustment_reason": adj_reason,
                "matched_shipment_id": matched_shp_id,
                "matched_route": matched_route,
                "matched_service_provider": matched_sp_name,
            })
        return items

    # Fall back: single line item with invoice total
    acc_code = charge.get("otm_accessorial_code") or fallback_code or "OFR"
    cost_type = charge.get("cost_type", "Freight")
    description = (
        extracted.get("charge_description")
        or charge.get("description")
        or "Freight Charge"
    )
    return [
        {
            "line_item_sequence": 1,
            "cost_type": cost_type,
            "charge_description": description,
            "unit_count": 1,
            "unit_of_measure": "FLAT",
            "currency": extracted.get("currency") or "AED",
            "base_charge": extracted.get("amount_due"),
            "accessorial_code": acc_code,
            "transport_handling_unit": transport_unit,
            "preprocess_status": preprocess_status,
            "adjustment_reason": adj_reason,
            "matched_shipment_id": matched_shp_id,
            "matched_route": matched_route,
            "matched_service_provider": matched_sp_name,
        }
    ]


def build_otm_payload(extracted: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    """Build an Oracle OTM-compliant invoice payload from extracted + validation data."""
    shipment = validation.get("matched_shipment") or {}
    charge   = validation.get("matched_charge_code") or {}
    sp       = validation.get("matched_service_provider") or {}
    v_status = validation.get("validation_status", "UNKNOWN")

    auto_create = v_status == "PASSED"
    erp_status  = "ERP_DRAFT_CREATED" if auto_create else "WAITING_FOR_HUMAN_REVIEW"
    now_utc     = datetime.now(tz=timezone.utc)

    # ── OTM Document ID (the key reference field in Oracle OTM) ───────────────
    otm_document_id = _otm_document_id(extracted)

    # ── Vendor-specific fields from AI extraction ──────────────────────────────
    vsf = extracted.get("vendor_specific_fields") or {}

    origin_port       = (extracted.get("origin_port")
                         or vsf.get("origin_port") or vsf.get("pol")
                         or shipment.get("origin_port") or "")
    destination_port  = (extracted.get("destination_port")
                         or vsf.get("destination_port") or vsf.get("pod")
                         or shipment.get("destination_port") or "")
    vessel_name       = (extracted.get("vessel_name")
                         or vsf.get("vessel_name") or vsf.get("vessel") or "")
    voyage_number     = (extracted.get("voyage_number")
                         or vsf.get("voyage_number") or vsf.get("voyage") or "")
    container_number  = (extracted.get("container_number")
                         or vsf.get("container_number") or "")
    awb_number        = (extracted.get("awb_number")
                         or vsf.get("awb_number") or extracted.get("mbl_number") or "")
    customer_number   = (extracted.get("customer_number")
                         or vsf.get("customer_number") or vsf.get("client_number") or "")
    bl_number         = (extracted.get("mbl_number")
                         or vsf.get("bl_number") or vsf.get("swb_number") or "")

    # ── Invoice Header ─────────────────────────────────────────────────────────
    invoice_header = {
        # OTM identifiers
        "otm_document_id":               otm_document_id,
        "invoice_number":                extracted.get("invoice_number"),
        "invoice_date":                  extracted.get("invoice_date"),
        "date_received":                 now_utc.strftime("%Y-%m-%d"),

        # Service provider (OTM calls it "service provider" not "vendor")
        "service_provider_alias_qualifier": "GLOG",
        "service_provider_alias":        sp.get("alias") or extracted.get("vendor_id"),
        "service_provider_gid":          extracted.get("service_provider_id") or shipment.get("service_provider_id"),
        "service_provider_name":         sp.get("name") or extracted.get("vendor_name"),

        # Financial
        "currency":                      extracted.get("currency") or shipment.get("currency", "AED"),
        "amount_due":                    extracted.get("amount_due"),
        "vat_amount":                    extracted.get("vat_amount"),
        "amount_due_with_vat":           extracted.get("amount_due_with_vat"),
        "financial_consolidation_type":  "STANDARD",
        "invoice_bill_rule_id":          shipment.get("invoice_bill_rule_id", "INVOICE_PER_LINE"),
        "payment_method":                shipment.get("payment_method", "BANK_TRANSFER"),

        # Shipment reference
        "shipment_id":                   extracted.get("shipment_id") or shipment.get("shipment_id"),
        "bl_number":                     bl_number,
        "awb_number":                    awb_number,
        "customer_number":               customer_number,

        # Route & transport details
        "origin_port":                   origin_port,
        "destination_port":              destination_port,
        "route":                         (extracted.get("route_or_port")
                                          or shipment.get("route")
                                          or (f"{origin_port} to {destination_port}".strip(" to") if origin_port or destination_port else "")),
        "vessel_name":                   vessel_name,
        "voyage_number":                 voyage_number,
        "container_number":              container_number,

        # Metadata
        "invoice_source":                "AI_PREPROCESSOR",
        "exchange_rate_date":            now_utc.strftime("%Y-%m-%d"),
        "start_date":                    extracted.get("invoice_date"),
        "end_date":                      extracted.get("invoice_date"),
    }

    # ── Line Items (one per charge, not one aggregate) ─────────────────────────
    line_items = _build_line_items(extracted, validation, shipment, sp, charge)

    # ── Invoice Summary ────────────────────────────────────────────────────────
    total_lines       = len(line_items)
    total_base        = sum(float(li.get("base_charge") or 0) for li in line_items)
    total_vat         = float(extracted.get("vat_amount") or 0)
    total_with_vat    = float(extracted.get("amount_due_with_vat") or (total_base + total_vat))

    invoice_summary = {
        "total_lines":            total_lines,
        "total_base_charges":     round(total_base, 2),
        "total_vat":              round(total_vat, 2),
        "total_amount_with_vat":  round(total_with_vat, 2),
        "currency":               extracted.get("currency") or "AED",
        "validation_status":      v_status,
        "match_status":           validation.get("match_status", "EXCEPTION_REVIEW"),
        "vat_status":             validation.get("vat_status", "VAT_NOT_FOUND"),
        "vendor_id":              extracted.get("vendor_id"),
        "vendor_confidence":      round(float(extracted.get("vendor_confidence") or 0), 2),
        "ai_confidence":          round(float(extracted.get("confidence_score") or extracted.get("confidence") or 0), 2),
        "auto_created":           auto_create,
    }

    return {
        "erp_status":       erp_status,
        "otm_document_id":  otm_document_id,
        "invoice_header":   invoice_header,
        "line_items":       line_items,
        "invoice_summary":  invoice_summary,
        "human_review": {
            "required": not auto_create,
            "reason":   validation.get("errors", []) + validation.get("warnings", []),
        },
    }
