from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    line_item_sequence: int = 1
    charge_code: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None


class ExtractedInvoice(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    service_provider_id: Optional[str] = None
    customer_number: Optional[str] = None   # Customer/Account No on the invoice
    mbl_number: Optional[str] = None        # Master Bill of Lading number
    currency: Optional[str] = None
    amount_due: Optional[float] = None
    vat_amount: Optional[float] = None
    amount_due_with_vat: Optional[float] = None
    tax_type: Optional[str] = None          # "GST" | "VAT" | "NONE"
    cgst_amount: Optional[float] = None     # India: Central GST component
    sgst_amount: Optional[float] = None     # India: State GST component
    igst_amount: Optional[float] = None     # India: Integrated GST component
    charge_code: Optional[str] = None
    charge_description: Optional[str] = None
    invoice_type: Optional[str] = None
    invoice_category: Optional[str] = "unknown"
    shipment_id: Optional[str] = None
    route_or_port: Optional[str] = None
    confidence_score: float = 0.5
    missing_fields: List[str] = Field(default_factory=list)
    possible_errors: List[str] = Field(default_factory=list)
    line_items: List[LineItem] = Field(default_factory=list)

    @field_validator("amount_due", "vat_amount", "amount_due_with_vat",
                     "cgst_amount", "sgst_amount", "igst_amount", mode="before")
    @classmethod
    def coerce_float(cls, v):
        if v is None:
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    @field_validator("confidence_score", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (TypeError, ValueError):
            return 0.5

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class FileRecord(BaseModel):
    source: str
    source_type: str = ""
    original_file_path: str
    working_copy_path: str
    file_hash: str
    original_filename: str = ""
    file_size: int = 0


class ValidationResult(BaseModel):
    validation_status: str = "UNKNOWN"
    match_status: str = "UNKNOWN"
    vat_status: str = "VAT_NOT_FOUND"
    matched_shipment: Optional[Dict[str, Any]] = None
    matched_service_provider: Optional[Dict[str, Any]] = None
    matched_charge_code: Optional[Dict[str, Any]] = None
    amount_difference: float = 0.0
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def validate_extracted_json(data: dict) -> ExtractedInvoice:
    """Validate and coerce AI-extracted JSON into ExtractedInvoice model."""
    normalized: Dict[str, Any] = {}
    normalized["vendor_name"] = data.get("vendor_name")
    normalized["invoice_number"] = data.get("invoice_number")
    normalized["invoice_date"] = data.get("invoice_date")
    normalized["service_provider_id"] = data.get("service_provider_id")
    normalized["customer_number"] = data.get("customer_number")
    normalized["mbl_number"] = data.get("mbl_number")
    normalized["currency"] = data.get("currency")
    normalized["amount_due"] = data.get("amount_due")
    normalized["vat_amount"] = data.get("vat_amount")
    normalized["amount_due_with_vat"] = data.get("amount_due_with_vat")
    normalized["tax_type"] = data.get("tax_type")
    normalized["cgst_amount"] = data.get("cgst_amount")
    normalized["sgst_amount"] = data.get("sgst_amount")
    normalized["igst_amount"] = data.get("igst_amount")
    normalized["charge_code"] = data.get("charge_code")
    normalized["charge_description"] = data.get("charge_description")
    normalized["invoice_type"] = data.get("invoice_type")
    normalized["invoice_category"] = data.get("invoice_category") or data.get("category") or "unknown"
    normalized["shipment_id"] = data.get("shipment_id")
    normalized["route_or_port"] = data.get("route_or_port") or data.get("route")
    normalized["confidence_score"] = data.get("confidence_score") or data.get("confidence") or 0.5
    normalized["missing_fields"] = data.get("missing_fields") or []
    normalized["possible_errors"] = data.get("possible_errors") or []
    raw_items = data.get("line_items") or []
    normalized["line_items"] = [
        LineItem(
            line_item_sequence=item.get("line_item_sequence", idx + 1),
            charge_code=item.get("charge_code"),
            description=item.get("description"),
            amount=item.get("amount"),
            currency=item.get("currency"),
        )
        for idx, item in enumerate(raw_items)
        if isinstance(item, dict)
    ]
    return ExtractedInvoice(**normalized)
