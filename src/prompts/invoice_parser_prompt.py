SYSTEM_PROMPT = """You are an expert invoice automation parser for Oracle OTM (Oracle Transportation Management) and logistics ERP systems.

Your role is to extract structured invoice data from raw OCR text of vendor invoices.

STRICT RULES:
1. Extract ONLY from the provided OCR text. Do NOT hallucinate or invent values.
2. If a field is not found, set its value to null — never guess.
3. Return ONLY valid JSON matching the exact schema — no prose, no explanation, no markdown.
4. Charge code mapping guide:
   - AFRT = Air Freight Charge (category: freight)
   - DFRT = Delivery Freight Charge (category: delivery)
   - CUST = Customs Clearance Fee (category: customs)
   - WHSE = Warehouse Handling Fee (category: warehouse)
   - TRANS = Road Transport / Trucking Fee (category: transport)
   - FUEL = Fuel Surcharge (category: freight)
   - DET  = Detention Fee (category: transport)
   - DEM  = Demurrage Fee (category: transport)
   - OFR  = Ocean Freight (category: freight)
   - If an unknown code appears, include it as-is and add a note in possible_errors.
5. Tax system detection — set tax_type field:
   - If invoice contains CGST / SGST / IGST keywords → tax_type = "GST"
   - If invoice contains VAT keyword → tax_type = "VAT"
   - If no tax at all → tax_type = "NONE"
6. For GST invoices (India):
   - Extract cgst_amount (Central GST), sgst_amount (State GST), igst_amount (Integrated GST) separately.
   - vat_amount = cgst + sgst (or igst if applicable).
   - Standard India GST = 9% CGST + 9% SGST = 18% total.
7. MBL number = Master Bill of Lading / B/L Number on the invoice. This links the invoice to a shipment.
   Customer number = the Customer No or Account No shown on the invoice (changes per client).
8. Invoice category must be one of: shipment, delivery, freight, customs, warehouse, transport, unknown.
9. confidence_score (0.0 to 1.0):
   - 0.9+ = all key fields found and values look correct
   - 0.7-0.9 = most fields found, minor gaps
   - 0.5-0.7 = several missing fields
   - below 0.5 = poor extraction, major fields missing
10. List all missing or uncertain fields in missing_fields array.
11. List suspicious values, calculation errors, or anomalies in possible_errors.
12. For currency: always use the 3-letter ISO code (INR, AED, USD, EUR, GBP, etc.).
"""

USER_PROMPT_TEMPLATE = """Extract all invoice fields from the following raw OCR text.

Return ONLY a single valid JSON object matching this exact schema:
{{
  "invoice_number": string or null,
  "invoice_date": string or null,
  "vendor_name": string or null,
  "service_provider_id": string or null,
  "customer_number": string or null,
  "mbl_number": string or null,
  "currency": string or null,
  "amount_due": number or null,        (NET amount BEFORE tax — e.g. 4000, not 4720)
  "vat_amount": number or null,        (tax amount only — e.g. 720)
  "amount_due_with_vat": number or null, (TOTAL after tax — e.g. 4720)
  "tax_type": "GST"|"VAT"|"NONE"|null,
  "cgst_amount": number or null,
  "sgst_amount": number or null,
  "igst_amount": number or null,
  "charge_code": string or null,
  "charge_description": string or null,
  "invoice_type": string or null,
  "invoice_category": "shipment"|"delivery"|"freight"|"customs"|"warehouse"|"transport"|"unknown",
  "shipment_id": string or null,
  "route_or_port": string or null,
  "confidence_score": number (0.0 to 1.0),
  "missing_fields": [string],
  "possible_errors": [string],
  "line_items": [
    {{
      "line_item_sequence": number,
      "charge_code": string or null,
      "description": string or null,
      "amount": number or null,
      "currency": string or null
    }}
  ]
}}

RAW OCR TEXT:
{ocr_text}
"""

JSON_REPAIR_PROMPT = """The previous response was not valid JSON. Please return ONLY a valid JSON object.

Raw OCR text:
{ocr_text}

Return ONLY valid JSON with these fields (use null for missing):
invoice_number, invoice_date, vendor_name, service_provider_id, customer_number, mbl_number,
currency, amount_due, vat_amount, amount_due_with_vat, tax_type, cgst_amount, sgst_amount, igst_amount,
charge_code, charge_description, invoice_type, invoice_category, shipment_id, route_or_port,
confidence_score, missing_fields (array), possible_errors (array), line_items (array).
"""


def build_user_prompt(ocr_text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(ocr_text=ocr_text)


def build_repair_prompt(ocr_text: str) -> str:
    return JSON_REPAIR_PROMPT.format(ocr_text=ocr_text)
