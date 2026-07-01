import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def build_otm_payload(extracted: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    """Build an Oracle OTM-style invoice payload from extracted + validation data."""
    shipment = validation.get("matched_shipment") or {}
    charge = validation.get("matched_charge_code") or {}
    sp = validation.get("matched_service_provider") or {}
    v_status = validation.get("validation_status", "UNKNOWN")

    auto_create = v_status in ("PASSED",)
    erp_status = "ERP_DRAFT_CREATED" if auto_create else "WAITING_FOR_HUMAN_REVIEW"
    now_utc = datetime.now(tz=timezone.utc)
    erp_invoice_id = (
        "OTM-DRAFT-" + now_utc.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
        if auto_create else ""
    )

    invoice_header = {
        "invoice_number": extracted.get("invoice_number"),
        "financial_consolidation_type": "STANDARD",
        "service_provider_alias_qualifier": "GLOG",
        "service_provider_alias": sp.get("alias") or extracted.get("service_provider_id") or shipment.get("service_provider_id"),
        "service_provider_id": extracted.get("service_provider_id") or shipment.get("service_provider_id"),
        "payment_method": shipment.get("payment_method", "BANK_TRANSFER"),
        "invoice_source": "AI_PREPROCESSOR",
        "invoice_date": extracted.get("invoice_date"),
        "date_received": now_utc.strftime("%Y-%m-%d"),
        "start_date": extracted.get("invoice_date"),
        "end_date": extracted.get("invoice_date"),
        "currency": extracted.get("currency") or shipment.get("currency", "AED"),
        "exchange_rate_date": now_utc.strftime("%Y-%m-%d"),
        "amount_due": extracted.get("amount_due"),
        "vat_amount": extracted.get("vat_amount"),
        "amount_due_with_vat": extracted.get("amount_due_with_vat"),
        "invoice_bill_rule_id": shipment.get("invoice_bill_rule_id", "INVOICE_PER_LINE"),
        "shipment_id": extracted.get("shipment_id") or shipment.get("shipment_id"),
        "route": extracted.get("route_or_port") or shipment.get("route"),
    }
    if erp_invoice_id:
        invoice_header["invoice_id"] = erp_invoice_id

    charge_code = extracted.get("charge_code", "")
    description = (
        extracted.get("charge_description")
        or charge.get("description")
        or "Freight Charge"
    )
    cost_type = charge.get("cost_type", "Freight")
    preprocess_status = validation.get("match_status", "EXCEPTION_REVIEW")
    # Use OTM canonical accessorial code from charge master; fall back to extracted code
    accessorial_code = charge.get("otm_accessorial_code") or charge_code

    line_items = [
        {
            "line_item_sequence": 1,
            "cost_type": cost_type,
            "description": description,
            "unit_count": 1,
            "transport_handling_unit": shipment.get("transport_handling_unit", ""),
            "freight_charge": extracted.get("amount_due"),
            "accessorial_code": accessorial_code,
            "preprocess_status": preprocess_status,
            "adjustment_reason": "; ".join(validation.get("warnings", [])) if v_status != "PASSED" else "",
            "matched_shipment_id": shipment.get("shipment_id", ""),
            "matched_route": shipment.get("route", ""),
            "matched_service_provider": sp.get("name") or shipment.get("vendor_name", ""),
        }
    ]

    invoice_summary = {
        "total_lines": 1,
        "total_freight_charges": extracted.get("amount_due"),
        "total_vat": extracted.get("vat_amount"),
        "total_amount_due_with_vat": extracted.get("amount_due_with_vat"),
        "currency": extracted.get("currency") or "AED",
        "validation_status": v_status,
        "match_status": preprocess_status,
        "vat_status": validation.get("vat_status", "VAT_NOT_FOUND"),
        "ai_confidence": extracted.get("confidence_score") or extracted.get("confidence"),
        "auto_created": auto_create,
    }

    return {
        "erp_status": erp_status,
        "erp_invoice_id": erp_invoice_id,
        "invoice_header": invoice_header,
        "line_items": line_items,
        "invoice_summary": invoice_summary,
        "human_review": {
            "required": not auto_create,
            "reason": validation.get("errors", []) + validation.get("warnings", []),
        },
    }
