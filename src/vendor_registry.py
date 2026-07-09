"""
Master vendor registry for OTM AI Invoice Preprocessor.

Each vendor entry defines:
  - How to identify the vendor from raw OCR text (patterns, weights, threshold)
  - What fields to extract (key_fields)
  - How to map vendor charge descriptions to OTM charge codes (charge_code_map)
  - Vendor-specific AI extraction instructions (extraction_prompt_hints)
  - OTM service provider info (sp_alias, sp_id, currency)

Identification engine: score each vendor's pattern list against the raw text.
The highest-scoring vendor above its threshold wins.
"""

from typing import Any, Dict, List, Optional

VENDOR_REGISTRY: Dict[str, Dict[str, Any]] = {

    # ── SEA FREIGHT CARRIERS ─────────────────────────────────────────────────────

    "HAPAG_LLOYD": {
        "vendor_id": "HAPAG_LLOYD",
        "name": "Hapag-Lloyd Middle East Shipping LLC",
        "short_name": "Hapag-Lloyd",
        "category": "sea",
        "otm_sp_alias": "HAPAGLLOYD",
        "otm_sp_id": "HLC.300001444444444",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"HLCU[A-Z]{2,3}\d{6,}",    "weight": 100},
                {"type": "contains", "value": "hapag-lloyd",                  "weight": 95},
                {"type": "contains", "value": "hapag lloyd",                  "weight": 95},
                {"type": "contains", "value": "hapaglloyd",                   "weight": 90},
                {"type": "contains", "value": "hlcu",                         "weight": 88},
                {"type": "contains", "value": "odex",                         "weight": 20},
            ],
            "threshold": 85,
        },
        "key_fields": [
            "invoice_number", "customer_number", "swb_number",
            "vessel", "voyage", "origin_port", "destination_port",
            "line_items", "total_aed",
        ],
        "charge_code_map": {
            "dest.document fee":          "DFRT",
            "destination document fee":   "DFRT",
            "equipm.mainten.fee":         "DET",
            "equipment maintenance fee":  "DET",
            "detention":                  "DET",
            "demurrage":                  "DEM",
            "ocean freight":              "OFR",
            "lss":                        "LSS",
            "ebs":                        "EBS",
            "pss":                        "PSS",
            "thc":                        "THC",
            "baf":                        "BAF",
            "default":                    "OFR",
        },
        "extraction_prompt_hints": """VENDOR: Hapag-Lloyd Middle East Shipping LLC

FORMAT RULES:
- Invoice No: 10-digit numeric (e.g. 2180010997)
- Customer No: 8-digit numeric (e.g. 53584705)
- SWB-NO / B/L No: starts with HLCU + port code + digits (e.g. HLCUMTR251145600)
- Shipment block: vessel name, two voyage numbers, sailing date, arrival date
- Route: "FROM [city] TO [city]"
- Charge table: [description]  [amount] AED  [qty] [unit]  [total] AED
- TOTAL at bottom
- Payment portal: ODEX

EXTRACT:
- invoice_number: the 10-digit number (NOT the HLCU number)
- customer_number: the 8-digit customer number
- swb_number / mbl_number: the HLCU... number (shipment reference)
- vessel_name, voyage_numbers, sailing_date, arrival_date
- origin_port, destination_port (from FROM/TO line)
- line_items: each charge row → {description, amount_aed, qty, unit}
- total_aed: TOTAL line
- vat_amount: if shown

OTM CHARGE CODE MAP:
DEST.DOCUMENT FEE → DFRT
EQUIPM.MAINTEN.FEE → DET
DETENTION → DET  |  DEMURRAGE → DEM  |  OCEAN FREIGHT → OFR""",
    },

    "MSC": {
        "vendor_id": "MSC",
        "name": "Mediterranean Shipping Company (MSC)",
        "short_name": "MSC",
        "category": "sea",
        "otm_sp_alias": "MSC",
        "otm_sp_id": "MSC.300001555555555",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"AEJ[A-Z]{2,4}PM\d{9,}",          "weight": 100},
                {"type": "regex",    "pattern": r"AEK[A-Z]{2,4}PM\d{9,}",          "weight": 100},
                {"type": "regex",    "pattern": r"MSCU\d{7,}",                      "weight": 90},
                {"type": "regex",    "pattern": r"MEDU\d{7,}",                      "weight": 90},
                {"type": "contains", "value": "mediterranean shipping",              "weight": 95},
                {"type": "contains", "value": "msc mediterranean",                  "weight": 95},
                {"type": "contains", "value": "aejeapm",                            "weight": 100},
                {"type": "contains", "value": "aeklfpm",                            "weight": 100},
            ],
            "threshold": 85,
        },
        "key_fields": [
            "invoice_number", "client_number", "vessel", "voyage",
            "pol", "pod", "bl_number", "container_number", "container_size",
            "line_items", "vat_aed", "total_aed",
        ],
        "charge_code_map": {
            "container protection":   "DEM",
            "empty inspection":       "DET",
            "delivery order fee":     "DFRT",
            "detention":              "DET",
            "demurrage":              "DEM",
            "ocean freight":          "OFR",
            "lss":                    "LSS",
            "cic":                    "CIC",
            "default":                "OFR",
        },
        "extraction_prompt_hints": """VENDOR: Mediterranean Shipping Company (MSC)

FORMAT RULES:
- Invoice No: starts with AEJEAPM or AEKLFPM + 9+ digits (e.g. AEJEAPM260018004)
- Client No: starts with 1000 + 6+ digits (e.g. 1000176343)
- Header: Vessel, Voy, POL, POD, B/L No
- Container table: container number / size type
- Charge table: Quantity | Rate | Currency | Total curr. | ROE | Total AED | VAT AED
- VAT at 5%

EXTRACT:
- invoice_number: the AEJEAPM/AEKLFPM... number
- client_number: the 1000... number
- bl_number, vessel, pol (Port of Loading), pod (Port of Discharge)
- container_number, container_size
- line_items: each charge → {description, qty, rate, currency, total_curr, roe, total_aed, vat_aed}
- total_aed: grand total  |  vat_amount: total VAT AED

OTM CHARGE CODE MAP:
Container Protection → DEM  |  Empty Inspection → DET  |  Delivery Order Fee → DFRT""",
    },

    "CMA_CGM": {
        "vendor_id": "CMA_CGM",
        "name": "CMA CGM",
        "short_name": "CMA CGM",
        "category": "sea",
        "otm_sp_alias": "CMACGM",
        "otm_sp_id": "CMA.300001666666666",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"AEIM\d{7,}",  "weight": 100},
                {"type": "regex",    "pattern": r"CMAU\d{7,}",  "weight": 90},
                {"type": "regex",    "pattern": r"CMAL\d{7,}",  "weight": 90},
                {"type": "contains", "value": "cma cgm",        "weight": 95},
                {"type": "contains", "value": "aeim",           "weight": 95},
            ],
            "threshold": 85,
        },
        "key_fields": [
            "invoice_number", "voyage", "container_number", "container_size",
            "line_items", "total_aed",
        ],
        "charge_code_map": {
            "container return":  "DET",
            "documentation fee": "DFRT",
            "delivery order":    "DFRT",
            "ocean freight":     "OFR",
            "detention":         "DET",
            "demurrage":         "DEM",
            "default":           "OFR",
        },
        "extraction_prompt_hints": """VENDOR: CMA CGM

FORMAT RULES:
- Invoice No: starts with AEIM + 7+ digits (e.g. AEIM1629821)
- Container: starts with CMAU or CMAL
- Voyage number in header
- Charge table: Size/Type | Charge Description | Tax | Based on | Rate | Currency | Amount | Amount in AED

EXTRACT:
- invoice_number: the AEIM... number
- container_number (CMAU/CMAL), voyage
- line_items: {description, size_type, rate, currency, amount, amount_aed, tax_code}
- total_aed

OTM: Container Return → DET  |  Documentation/Delivery Order → DFRT  |  Freight → OFR""",
    },

    "COSCO": {
        "vendor_id": "COSCO",
        "name": "COSCO Shipping Lines",
        "short_name": "COSCO",
        "category": "sea",
        "otm_sp_alias": "COSCO",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"AE01\d{10,}",     "weight": 100},
                {"type": "regex",    "pattern": r"INV26\d{8,}",     "weight": 95},
                {"type": "regex",    "pattern": r"COSU\d{7,}",      "weight": 90},
                {"type": "contains", "value": "cosco shipping",     "weight": 95},
                {"type": "contains", "value": "cosco",              "weight": 80},
            ],
            "threshold": 80,
        },
        "key_fields": ["receipt_number", "invoice_number", "line_items", "total_amount"],
        "charge_code_map": {
            "admin fee":        "DFRT",
            "documentation":    "DFRT",
            "delivery order":   "DFRT",
            "ocean freight":    "OFR",
            "default":          "OFR",
        },
        "extraction_prompt_hints": """VENDOR: COSCO Shipping Lines

FORMAT RULES:
- Receipt No: AE01 + 10+ digits (e.g. AE012603090001)
- OR Tax Invoice: INV26 + 8+ digits (e.g. INV2603001533)
- Simple table: SNo | Description | Amount
- Total at bottom

EXTRACT:
- document_number: the AE01... or INV26... number
- line_items: {seq, description, amount}
- total_amount  |  currency: AED

OTM: Admin/Documentation/Delivery → DFRT  |  Freight → OFR""",
    },

    "MAERSK": {
        "vendor_id": "MAERSK",
        "name": "Maersk Line",
        "short_name": "Maersk",
        "category": "sea",
        "otm_sp_alias": "MAERSK",
        "otm_sp_id": "MSK.300001333333333",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"MAEU\d{7,}",   "weight": 100},
                {"type": "regex",    "pattern": r"MAES\d{7,}",   "weight": 100},
                {"type": "regex",    "pattern": r"MRKU\d{7,}",   "weight": 90},
                {"type": "contains", "value": "maersk",          "weight": 95},
                {"type": "contains", "value": "a.p. moller",     "weight": 90},
                {"type": "contains", "value": "a.p.moller",      "weight": 90},
            ],
            "threshold": 85,
        },
        "key_fields": ["invoice_number", "bl_number", "container_number", "line_items", "total"],
        "charge_code_map": {
            "ocean freight":  "OFR",
            "detention":      "DET",
            "demurrage":      "DEM",
            "baf":            "BAF",
            "thc":            "THC",
            "lss":            "LSS",
            "ebs":            "EBS",
            "default":        "OFR",
        },
        "extraction_prompt_hints": """VENDOR: Maersk Line

FORMAT RULES:
- B/L starts with MAEU, MAES, or MRKU + digits
- Container numbers: MRKU, MSKU prefixes
- Standard ocean freight invoice format
- Has BAF, THC, LSS, EBS surcharges

EXTRACT: invoice_number, bl_number, container_number, vessel, pol, pod,
line_items with {description, amount, currency}, total_amount

OTM: Ocean Freight → OFR  |  Detention → DET  |  Demurrage → DEM""",
    },

    # ── AIR FREIGHT ──────────────────────────────────────────────────────────────

    "EMIRATES_SKYCARGO": {
        "vendor_id": "EMIRATES_SKYCARGO",
        "name": "Emirates SkyCargo",
        "short_name": "Emirates SkyCargo",
        "category": "air",
        "otm_sp_alias": "EMIRATESSKY",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"176[\s\-]\d{8}",     "weight": 100},
                {"type": "regex",    "pattern": r"AWB\s*NO\.?\s*176",  "weight": 100},
                {"type": "contains", "value": "emirates skycargo",     "weight": 99},
                {"type": "contains", "value": "walkiaedxb",            "weight": 99},
                {"type": "contains", "value": "skycargo",              "weight": 90},
            ],
            "threshold": 88,
        },
        "key_fields": [
            "awb_number", "customer_code", "account_code",
            "awb_issue_section", "other_charges_section", "total_aed",
        ],
        "charge_code_map": {
            "fe general handling":  "AFRT",
            "general handling":     "AFRT",
            "sf delivery order":    "DFRT",
            "delivery order":       "DFRT",
            "ub disassembly":       "AFRT",
            "awb issue":            "AFRT",
            "default":              "AFRT",
        },
        "extraction_prompt_hints": """VENDOR: Emirates SkyCargo

FORMAT RULES:
- AWB NO.: 176 followed by space/dash then 8 digits (e.g. 176 10507700)
  → 176 is Emirates' IATA airline code
- Customer Code & Account Code: WALKIAEDXB
- Two charge sections: "AWB Issue" section + "Other Charges" section
- Each row: AWB No | Description | Amount AED
- Total at bottom  |  VAT if applicable

EXTRACT:
- awb_number: the full "176 XXXXXXXX" number (Master AWB)
- customer_code: "WALKIAEDXB"
- line_items from BOTH sections: {awb_number, section, description, amount_aed}
- vat_amount  |  total_aed: grand total
- charge_code: FE General Handling → AFRT, SF Delivery Order → DFRT, UB Disassembly → AFRT""",
    },

    "CALOGI": {
        "vendor_id": "CALOGI",
        "name": "Calogi — Cargo Airline LLC",
        "short_name": "CALOGI",
        "category": "air",
        "otm_sp_alias": "CALOGI",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"DXBCAIN\d{8,}",  "weight": 100},
                {"type": "contains", "value": "dcl146",            "weight": 100},
                {"type": "contains", "value": "dxbcain",           "weight": 100},
                {"type": "contains", "value": "calogi",            "weight": 95},
                {"type": "contains", "value": "cargo airline",     "weight": 80},
            ],
            "threshold": 90,
        },
        "key_fields": [
            "invoice_number", "account_code", "job_type",
            "mawb_or_mcbv_number", "transaction_type",
            "line_items", "grand_total",
        ],
        "charge_code_map": {
            "airline do primary":     "AFRT",
            "appointment dafza fee":  "AFRT",
            "awb/cbv issue":          "AFRT",
            "awb issue":              "AFRT",
            "cbv issue":              "AFRT",
            "awb amendment":          "AFRT",
            "cbv amendment":          "AFRT",
            "dn amendment":           "AFRT",
            "default":                "AFRT",
        },
        "extraction_prompt_hints": """VENDOR: Calogi (Cargo Airline LLC)

FORMAT RULES:
- Invoice No: DXBCAIN + 8+ digits (e.g. DXBCAIN16397147)
- Account Code: DCL146 — always present (Transworld's account at CALOGI)
- Job Type field: describes the service (e.g. "Airline DO Primary")
- MAWB No / MCBV No: the air waybill or consolidation B/L number
- Transaction Type: specific charge type
- Table: SrNo | Particulars | Payment Mode | Amount
- Grand Total at bottom

EXTRACT:
- invoice_number: the DXBCAIN... number
- account_code: "DCL146"
- job_type: value of Job Type field
- mawb_or_mcbv: the MAWB or MCBV number shown
- transaction_type: value of Transaction Type field
- line_items: {sr_no, particulars, payment_mode, amount}
- grand_total  |  vat_amount if shown

OTM CHARGE CODE (all CALOGI charges → AFRT):
Airline DO Primary → AFRT  |  Appointment Dafza Fee → AFRT
AWB/CBV Issue/Amendment → AFRT  |  DN Amendment → AFRT""",
    },

    "BENGAL_AIRLIFT": {
        "vendor_id": "BENGAL_AIRLIFT",
        "name": "Bengal Airlift",
        "short_name": "Bengal Airlift",
        "category": "air",
        "otm_sp_alias": "BENGALAIRLIFT",
        "currency": "USD",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"DRN\d{10,}[A-Z]\b",  "weight": 100},
                {"type": "regex",    "pattern": r"DRN\d{8,}[A-Z]\b",   "weight": 95},
                {"type": "contains", "value": "bengal airlift",        "weight": 99},
            ],
            "threshold": 88,
        },
        "key_fields": [
            "document_number", "booking_number", "hbl_number", "mbl_number",
            "shipper", "consignee",
            "line_items", "total_usd", "total_aed", "roe",
        ],
        "charge_code_map": {
            "stuffing":         "AFRT",
            "mbl fee":          "AFRT",
            "air freight":      "AFRT",
            "ams":              "CUST",
            "documentation":    "DFRT",
            "default":          "AFRT",
        },
        "extraction_prompt_hints": """VENDOR: Bengal Airlift

FORMAT RULES:
- Document No: DRN + 10+ digits + one letter suffix (e.g. DRN26022238260A)
  → This is a Debit Note
- Booking No in header
- Shipment table: SL | HBL | MBL | SHIPPER | CONSIGNEE
- Charge table: CUR | UNIT COST | UNIT | CHARGE | ROE | AMOUNT
- Charges in USD, converted to AED via ROE

EXTRACT:
- document_number: the DRN...A number
- mbl_number, hbl_number, shipper, consignee
- line_items: {currency(USD), unit_cost, unit, charge_description, roe, amount_aed}
- total_usd  |  total_aed  |  roe (rate of exchange)
- charge_code: AFRT for freight charges, CUST for AMS/customs, DFRT for docs""",
    },

    # ── LOCAL LOGISTICS ───────────────────────────────────────────────────────────

    "GREEN_WAY_CARGO": {
        "vendor_id": "GREEN_WAY_CARGO",
        "name": "Green Way Cargo (GJJ)",
        "short_name": "Green Way Cargo",
        "category": "logistics",
        "otm_sp_alias": "GREENWAYCARGO",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"INV-0\d{5,}",      "weight": 100},
                {"type": "contains", "value": "green way cargo",     "weight": 99},
                {"type": "contains", "value": "green way",           "weight": 85},
                {"type": "contains", "value": "gjj",                 "weight": 80},
            ],
            "threshold": 80,
        },
        "key_fields": [
            "invoice_number", "bill_to", "line_items",
            "boe_number", "awb_number", "route", "vat_amount", "total_amount",
        ],
        "charge_code_map": {
            "transportation":    "TRANS",
            "inland freight":    "TRANS",
            "customs clearance": "CUST",
            "delivery":          "DFRT",
            "default":           "TRANS",
        },
        "extraction_prompt_hints": """VENDOR: Green Way Cargo (GJJ logo)

FORMAT RULES:
- Invoice No: INV-0 + 5+ digits (e.g. INV-023628)
- Bill To: TRANSWORLD LOGISTICS DWC LLC
- Item & Description table: Item No | Description | Qty | Rate | Amount
- Description contains embedded BOE No / AWB No and route (FROM...TO...)
- VAT: Zero Rated 0% (usually no VAT)
- Total Amount at bottom

EXTRACT:
- invoice_number: the INV-0... number
- bill_to: "TRANSWORLD LOGISTICS DWC LLC"
- line_items: {item_no, description, qty, rate, amount}
  also extract from description: boe_number, awb_number, from_location, to_location
- vat_amount: 0 (zero rated)  |  total_amount
- charge_code: Transportation → TRANS, Customs → CUST""",
    },

    "RAVIAN_SHIPPING": {
        "vendor_id": "RAVIAN_SHIPPING",
        "name": "Ravian Shipping Lines",
        "short_name": "Ravian Shipping",
        "category": "logistics",
        "otm_sp_alias": "RAVIANSHIPPING",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"JI-\d+\/\d{2,4}",  "weight": 100},
                {"type": "contains", "value": "ravian shipping",     "weight": 99},
                {"type": "contains", "value": "ravian",              "weight": 85},
            ],
            "threshold": 85,
        },
        "key_fields": [
            "invoice_number", "mbl_number", "bl_number", "vessel", "voyage",
            "line_items", "grand_total",
        ],
        "charge_code_map": {
            "d/o charges":    "DFRT",
            "do charge":      "DFRT",
            "delivery order": "DFRT",
            "admin fee":      "DFRT",
            "dt do payment":  "DFRT",
            "default":        "DFRT",
        },
        "extraction_prompt_hints": """VENDOR: Ravian Shipping Lines

FORMAT RULES:
- Invoice No: JI-[number]/[2-digit year] (e.g. JI-695/26)
- MBL No and Bill of Lading in header
- Vessel and Voyage numbers
- Charge table: S.No | Charges | Qty | Rate | Curr | Amount | VAT% | VAT Amount | Total Amount
- VAT at 5% on applicable lines
- Grand Total at bottom

EXTRACT:
- invoice_number: the JI-.../... number
- mbl_number, bl_number, vessel, voyage
- line_items: {seq, charge_description, qty, rate, currency, amount, vat_percent, vat_amount, total_amount}
- grand_total  |  total_vat
- charge_code: D/O Charges → DFRT, Admin Fee → DFRT, DT DO Payment → DFRT""",
    },

    "ADSO_LLC": {
        "vendor_id": "ADSO_LLC",
        "name": "ADSO LLC",
        "short_name": "ADSO LLC",
        "category": "logistics",
        "otm_sp_alias": "ADSO",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "adso llc",  "weight": 100},
                {"type": "regex",    "pattern": r"\bADSO\b", "weight": 90},
            ],
            "threshold": 90,
        },
        "key_fields": [
            "invoice_number", "origin", "destination", "vessel", "commodity",
            "mbl_number", "line_items", "grand_total_aed",
        ],
        "charge_code_map": {
            "customs duty":        "CUST",
            "bill of entry":       "CUST",
            "port storage":        "DEM",
            "customs clearance":   "CUST",
            "transportation":      "TRANS",
            "air freight":         "AFRT",
            "default":             "CUST",
        },
        "extraction_prompt_hints": """VENDOR: ADSO LLC

FORMAT RULES:
- Invoice No: 7-digit starting with 26 (year prefix), e.g. 2640105, 2640163
- Header: Origin, Destin(ation), Vessel, Comod(ity), MB/L No
- Charge table: Description | Qty | Rate AED | Tax | Total FC | Amount AED | Tax AED | Total AED
- Mixed charges: customs duty, bill of entry, port storage, clearance, transportation

EXTRACT:
- invoice_number: the 7-digit 26... number
- origin, destination, vessel, commodity, mbl_number from header
- line_items: {description, qty, rate_aed, tax_code, total_fc, amount_aed, tax_aed, total_aed}
- grand_total_aed
- charge_code: Customs Duty/BOE → CUST, Port Storage → DEM, Transport → TRANS""",
    },

    "SEACOAST_LOGISTICS": {
        "vendor_id": "SEACOAST_LOGISTICS",
        "name": "Seacoast Logistics",
        "short_name": "Seacoast Logistics",
        "category": "logistics",
        "otm_sp_alias": "SEACOAST",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "seacoast logistics",  "weight": 100},
                {"type": "contains", "value": "seacoast",            "weight": 85},
                {"type": "regex",    "pattern": r"\d{9}-\d{2}-\d",   "weight": 60},
            ],
            "threshold": 80,
        },
        "key_fields": [
            "invoice_number", "mawb_mbl", "line_items", "total_amount",
        ],
        "charge_code_map": {
            "inland freight":       "TRANS",
            "airport transfer":     "TRANS",
            "terminal handling":    "THC",
            "airway bill fee":      "AFRT",
            "screening":            "AFRT",
            "air freight":          "AFRT",
            "default":              "AFRT",
        },
        "extraction_prompt_hints": """VENDOR: Seacoast Logistics

FORMAT RULES:
- Invoice: XXXXXXXXX-01-N format (e.g. 103535026-01-1)
- MAWB/MBL# references an Emirates AWB (176-XXXXXXX format)
- Itemized charges: Inland Freight, Airport Transfer, Terminal Handling, Airway Bill Fee, Screening, Air Freight

EXTRACT:
- invoice_number: full reference number
- mawb_mbl: the 176-... AWB reference
- line_items: {description, amount}  |  total_amount
- charge_codes: Inland/Airport → TRANS, Terminal Handling → THC, Air Freight/Screening → AFRT""",
    },

    # ── CUSTOMS / GOVERNMENT ─────────────────────────────────────────────────────

    "UAE_CUSTOMS_BOE": {
        "vendor_id": "UAE_CUSTOMS_BOE",
        "name": "UAE / Dubai Customs — Bill of Entry",
        "short_name": "UAE Customs BOE",
        "category": "customs",
        "otm_sp_alias": "UAECUSTOMS",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "regex",    "pattern": r"(102|101|303)-\d{8}-\d{2}",  "weight": 100},
                {"type": "contains", "value": "dec no",                        "weight": 85},
                {"type": "contains", "value": "dec date",                      "weight": 70},
                {"type": "contains", "value": "dubai customs",                 "weight": 90},
                {"type": "contains", "value": "port type",                     "weight": 60},
                {"type": "contains", "value": "tw logistics",                  "weight": 40},
            ],
            "threshold": 80,
        },
        "key_fields": [
            "dec_number", "dec_date", "port_type",
            "clearing_agent", "duties_breakdown", "total_duties",
        ],
        "charge_code_map": {
            "customs duty": "CUST",
            "duty":         "CUST",
            "default":      "CUST",
        },
        "extraction_prompt_hints": """VENDOR: UAE / Dubai Customs — Bill of Entry (Government Form)

FORMAT RULES:
- DEC NO: [102|101|303]-[8 digits]-[2-digit year] (e.g. 102-00231557-26)
- DEC DATE: declaration date
- PORT TYPE: land/sea/air
- 59-field structured government customs declaration
- Clearing Agent: TW LOGISTICS LLC
- Contains duties breakdown

EXTRACT:
- dec_number: full DEC NO value
- dec_date  |  port_type  |  clearing_agent: "TW LOGISTICS LLC"
- total_duties: total amount  |  duties_breakdown: {type, amount} list
- charge_code: CUST for all customs charges""",
    },

    "DUBAI_CUSTOMS_EREVENUE": {
        "vendor_id": "DUBAI_CUSTOMS_EREVENUE",
        "name": "Dubai Customs E-Revenue Receipt",
        "short_name": "Dubai Customs E-Rev",
        "category": "customs",
        "otm_sp_alias": "DUBCUSTOMS_EREV",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "exit entry seal charge",  "weight": 100},
                {"type": "contains", "value": "ae-1151728",              "weight": 100},
                {"type": "contains", "value": "e-revenue",               "weight": 80},
            ],
            "threshold": 90,
        },
        "key_fields": ["customer_code", "charge_type", "amount"],
        "charge_code_map": {"default": "CUST"},
        "extraction_prompt_hints": """VENDOR: Dubai Customs E-Revenue Receipt

Small receipt (not a full invoice).
- Charge type: EXIT ENTRY SEAL CHARGE or similar
- Customer Code: AE-1151728
- Fixed amount: AED 40 typically

EXTRACT: customer_code, charge_type, amount (usually AED 40)
OTM: charge_code = CUST""",
    },

    # ── PORT & TERMINAL ──────────────────────────────────────────────────────────

    "DP_WORLD": {
        "vendor_id": "DP_WORLD",
        "name": "DP World",
        "short_name": "DP World",
        "category": "port",
        "otm_sp_alias": "DPWORLD",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "dp world",  "weight": 100},
            ],
            "threshold": 90,
        },
        "key_fields": [
            "receipt_number", "customer", "vessel", "boe_number",
            "line_items", "grand_total",
        ],
        "charge_code_map": {
            "container storage":  "DEM",
            "gate pass":          "DFRT",
            "document processing":"DFRT",
            "default":            "DEM",
        },
        "extraction_prompt_hints": """VENDOR: DP World

FORMAT RULES:
- Tax Invoice (Cash Account)
- Receipt No in header, Customer and Vessel
- Charge table: Charge Description | BOE NO | Clearance | Qty | Rate | Amount | VAT% | VAT | Total Amount

EXTRACT:
- receipt_number, customer, vessel
- line_items: {charge_description, boe_number, clearance_date, qty, rate, amount, vat_percent, vat, total_amount}
- grand_total
- charge_code: Container Storage → DEM, Gate Pass/Doc Processing → DFRT""",
    },

    "ABU_DHABI_PORTS": {
        "vendor_id": "ABU_DHABI_PORTS",
        "name": "Abu Dhabi Ports / Gulftainer",
        "short_name": "Abu Dhabi Ports",
        "category": "port",
        "otm_sp_alias": "ABUDHABI_PORTS",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "gulftainer",        "weight": 100},
                {"type": "contains", "value": "abu dhabi ports",   "weight": 100},
            ],
            "threshold": 85,
        },
        "key_fields": ["receipt_number", "container_number", "terminal", "vessel", "line_items", "total"],
        "charge_code_map": {"default": "DEM"},
        "extraction_prompt_hints": """VENDOR: Abu Dhabi Ports / Gulftainer (Receipt Voucher format)

EXTRACT: receipt_number, container_number, terminal, vessel,
line_items with descriptions and amounts, total_amount
OTM: charge_code = DEM""",
    },

    # ── COURIER / EXPRESS ────────────────────────────────────────────────────────

    "FIRST_FLIGHT_COURIERS": {
        "vendor_id": "FIRST_FLIGHT_COURIERS",
        "name": "First Flight Couriers",
        "short_name": "First Flight",
        "category": "courier",
        "otm_sp_alias": "FIRSTFLIGHT",
        "currency": "AED",
        "identification": {
            "patterns": [
                {"type": "contains", "value": "first flight",         "weight": 100},
                {"type": "regex",    "pattern": r"Account\s*No.?\s*16082", "weight": 100},
                {"type": "contains", "value": "16082",                "weight": 80},
            ],
            "threshold": 85,
        },
        "key_fields": [
            "invoice_number", "account_number",
            "line_items", "grand_total",
        ],
        "charge_code_map": {
            "parcel import":  "AFRT",
            "airway bill":    "AFRT",
            "fuel surcharge": "FUEL",
            "default":        "AFRT",
        },
        "extraction_prompt_hints": """VENDOR: First Flight Couriers

FORMAT RULES:
- Invoice No: plain 6-digit number (e.g. 898394)
- Account No: 16082 (always present)
- Airway Bill table: Date | AWB No | Origin | Destination | Weight | Charge | Fuel Surcharge | Other | Total
- Parcel import service

EXTRACT:
- invoice_number (6-digit)  |  account_number: "16082"
- line_items: {date, awb_number, origin, destination, weight, charge, fuel_surcharge, total}
- grand_total
- charge_code: Parcel/AWB → AFRT, Fuel Surcharge → FUEL""",
    },
}


# ── helper functions ──────────────────────────────────────────────────────────

def get_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    return VENDOR_REGISTRY.get(vendor_id)


def get_all_vendors() -> Dict[str, Dict[str, Any]]:
    return VENDOR_REGISTRY


def get_vendors_by_category(category: str) -> List[Dict[str, Any]]:
    return [v for v in VENDOR_REGISTRY.values() if v.get("category") == category]


CATEGORIES = ["sea", "air", "logistics", "customs", "port", "courier"]

CATEGORY_LABELS = {
    "sea":      "Sea Freight",
    "air":      "Air Freight",
    "logistics":"Local Logistics",
    "customs":  "Customs / Government",
    "port":     "Port & Terminal",
    "courier":  "Courier / Express",
}

CATEGORY_COLORS = {
    "sea":      "#1358A5",
    "air":      "#0A8898",
    "logistics":"#8A6010",
    "customs":  "#2A6038",
    "port":     "#5C3A90",
    "courier":  "#943030",
}
