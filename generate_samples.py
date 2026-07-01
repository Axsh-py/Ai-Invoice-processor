"""
OTM AI Invoice Preprocessor — Sample Invoice Generator
Generates 40 varied vendor PDF invoices across different charge types,
vendors, layouts, and error conditions for demo purposes.
Run: python generate_samples.py
"""
import random
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

SAMPLE_DIR = Path(__file__).resolve().parent / "data" / "sample_invoices"
EMAIL_DIR = Path(__file__).resolve().parent / "sample_email_inbox"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
EMAIL_DIR.mkdir(parents=True, exist_ok=True)

W, H = A4


def _line(c, y, x1=22, x2=188):
    c.line(x1 * mm, y * mm, x2 * mm, y * mm)


def _bold(c, text, x, y, size=10):
    c.setFont("Helvetica-Bold", size)
    c.drawString(x * mm, y * mm, text)
    c.setFont("Helvetica", 10)


def _text(c, text, x, y, size=10):
    c.setFont("Helvetica", size)
    c.drawString(x * mm, y * mm, text)


def _header_box(c, company, trn, address):
    c.setFillColorRGB(0.08, 0.18, 0.40)
    c.rect(15 * mm, (H / mm - 38) * mm, 180 * mm, 28 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, (H / mm - 20) * mm, company)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, (H / mm - 26) * mm, f"TRN: {trn}   |   {address}")
    c.setFillColorRGB(0, 0, 0)


def layout_transworld(c, inv_data):
    """Layout A — Transworld Logistics modern header"""
    _header_box(c, "Transworld Logistics FZE",
                "TRN100234567890001", "Jebel Ali FZE, Dubai, UAE")
    y = H / mm - 48
    c.setFont("Helvetica-Bold", 16)
    c.drawString(22 * mm, y * mm, "TAX INVOICE")
    y -= 8
    _line(c, y)
    y -= 8
    _bold(c, "Service Provider ID:", 22, y)
    _text(c, "TW.300001490621360", 75, y)
    _bold(c, "Invoice No:", 120, y)
    _text(c, inv_data.get("invoice_number", ""), 148, y)
    y -= 7
    _bold(c, "Invoice Date:", 22, y)
    _text(c, inv_data.get("invoice_date", ""), 55, y)
    _bold(c, "Shipment ID:", 120, y)
    _text(c, inv_data.get("shipment_id", ""), 148, y)
    y -= 7
    _bold(c, "Currency:", 22, y)
    _text(c, inv_data.get("currency", "AED"), 45, y)
    _bold(c, "Route:", 120, y)
    _text(c, inv_data.get("route", ""), 135, y)
    y -= 7
    _bold(c, "Vendor:", 22, y)
    _text(c, "Transworld Logistics FZE", 45, y)
    y -= 10
    _line(c, y)
    y -= 8
    _bold(c, "Charge Description", 22, y)
    _bold(c, "Charge Code", 100, y)
    _bold(c, "Amount (AED)", 148, y)
    y -= 6
    _line(c, y)
    y -= 8
    _text(c, inv_data.get("description", "Air Freight Charge"), 22, y)
    _text(c, inv_data.get("charge_code", "AFRT"), 100, y)
    _text(c, f"{inv_data.get('amount_due', 0):,.2f}", 148, y)
    y -= 10
    _line(c, y)
    y -= 8
    if inv_data.get("show_vat", True):
        _bold(c, "VAT (5%):", 120, y)
        _text(c, f"{inv_data.get('vat_amount', 0):,.2f}", 148, y)
        y -= 7
    _bold(c, "Amount Due with VAT:", 100, y)
    _text(c, f"{inv_data.get('total', 0):,.2f}", 148, y)
    y -= 15
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(22 * mm, y * mm,
                 "Note: Vendor submitted limited charge details. OTM fields to be auto-completed by AI preprocessor.")
    if inv_data.get("exception_note"):
        y -= 7
        c.setFillColorRGB(0.7, 0, 0)
        c.drawString(22 * mm, y * mm, inv_data["exception_note"])
        c.setFillColorRGB(0, 0, 0)


def layout_aramex(c, inv_data):
    """Layout B — Aramex columnar billing layout"""
    c.setFillColorRGB(0.95, 0.55, 0.05)
    c.rect(15 * mm, (H / mm - 35) * mm, 180 * mm, 22 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, (H / mm - 20) * mm, "ARAMEX INTERNATIONAL LLC")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, (H / mm - 28) * mm, "TRN: TRN100234567890002  |  Aramex Building, Jebel Ali, Dubai")
    c.setFillColorRGB(0, 0, 0)
    y = H / mm - 44
    _bold(c, "INVOICE", 22, y, 14)
    y -= 9
    _bold(c, "Service Provider ID: AL.300001234567890", 22, y)
    y -= 7
    _text(c, f"Invoice Number: {inv_data.get('invoice_number', '')}", 22, y)
    _text(c, f"Invoice Date: {inv_data.get('invoice_date', '')}", 110, y)
    y -= 7
    _text(c, f"Shipment ID: {inv_data.get('shipment_id', '')}", 22, y)
    _text(c, f"Currency: {inv_data.get('currency', 'AED')}", 110, y)
    y -= 7
    _text(c, f"Route: {inv_data.get('route', '')}", 22, y)
    y -= 7
    _text(c, f"Vendor: Aramex International LLC", 22, y)
    y -= 8
    _line(c, y)
    y -= 8
    _bold(c, "SERVICE DESCRIPTION", 22, y)
    _bold(c, "CODE", 115, y)
    _bold(c, "AMOUNT (AED)", 150, y)
    y -= 6
    _line(c, y)
    y -= 8
    _text(c, inv_data.get("description", "Delivery Freight Charge"), 22, y)
    _text(c, inv_data.get("charge_code", "DFRT"), 115, y)
    _text(c, f"{inv_data.get('amount_due', 0):,.2f}", 150, y)
    y -= 12
    _bold(c, "VAT (5%):", 130, y)
    _text(c, f"{inv_data.get('vat_amount', 0):,.2f}", 160, y)
    y -= 7
    _bold(c, "TOTAL DUE:", 130, y)
    _text(c, f"{inv_data.get('total', 0):,.2f}", 160, y)


def layout_dhl(c, inv_data):
    """Layout C — DHL minimal customs invoice"""
    c.setFillColorRGB(1.0, 0.8, 0.0)
    c.rect(15 * mm, (H / mm - 30) * mm, 180 * mm, 18 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0.8, 0, 0)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, (H / mm - 18) * mm, "DHL")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(45 * mm, (H / mm - 18) * mm, "EXPRESS (UAE) LLC")
    c.setFillColorRGB(0, 0, 0)
    y = H / mm - 38
    _bold(c, "COMMERCIAL INVOICE / TAX INVOICE", 22, y, 13)
    y -= 9
    _text(c, f"Invoice No: {inv_data.get('invoice_number', '')}", 22, y)
    _text(c, f"Date: {inv_data.get('invoice_date', '')}", 110, y)
    y -= 7
    _text(c, f"Service Provider ID: DHL.30000187654321", 22, y)
    y -= 7
    _text(c, f"TRN: TRN100234567890003", 22, y)
    _text(c, f"Shipment ID: {inv_data.get('shipment_id', '')}", 110, y)
    y -= 7
    _text(c, f"Origin: {inv_data.get('origin', 'DXB')}   Destination: {inv_data.get('destination', '')}", 22, y)
    y -= 7
    _text(c, f"Vendor: DHL Express (UAE) LLC", 22, y)
    y -= 10
    _line(c, y)
    y -= 8
    _bold(c, "Description", 22, y)
    _bold(c, "Code", 110, y)
    _bold(c, "Amount (AED)", 150, y)
    y -= 6
    _line(c, y)
    y -= 8
    _text(c, inv_data.get("description", "Customs Clearance Fee"), 22, y)
    _text(c, inv_data.get("charge_code", "CUST"), 110, y)
    _text(c, f"{inv_data.get('amount_due', 0):,.2f}", 150, y)
    y -= 10
    note = "Note: Customs fees are VAT-exempt per UAE regulations." if inv_data.get("charge_code") == "CUST" else ""
    if note:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(22 * mm, y * mm, note)
        y -= 7
    _bold(c, "Total Amount Due:", 120, y)
    _text(c, f"{inv_data.get('total', 0):,.2f}", 160, y)


def layout_generic(c, inv_data):
    """Layout D — Generic/unknown vendor simple invoice"""
    c.setFont("Helvetica-Bold", 14)
    c.drawString(22 * mm, (H / mm - 20) * mm, inv_data.get("vendor", "Unknown Vendor"))
    c.setFont("Helvetica", 9)
    c.drawString(22 * mm, (H / mm - 28) * mm, inv_data.get("address", "Dubai, UAE"))
    y = H / mm - 38
    _bold(c, "INVOICE", 22, y, 16)
    y -= 10
    if inv_data.get("show_invoice_number", True):
        _text(c, f"Invoice Number: {inv_data.get('invoice_number', '')}", 22, y)
    else:
        _text(c, "Invoice Number: [MISSING]", 22, y)
        c.setFillColorRGB(0.7, 0, 0)
        c.drawString(22 * mm, (y - 5) * mm, "(Invoice number not provided by vendor)")
        c.setFillColorRGB(0, 0, 0)
    y -= 7
    if inv_data.get("show_vendor", True):
        _text(c, f"Vendor: {inv_data.get('vendor', '')}", 22, y)
    else:
        _text(c, "Vendor: [NOT PROVIDED]", 22, y)
    y -= 7
    _text(c, f"Date: {inv_data.get('invoice_date', '')}", 22, y)
    _text(c, f"Currency: {inv_data.get('currency', 'AED')}", 110, y)
    y -= 7
    _text(c, f"Shipment Ref: {inv_data.get('shipment_id', 'N/A')}", 22, y)
    y -= 10
    _line(c, y)
    y -= 8
    _bold(c, "Service", 22, y)
    _bold(c, "Code", 100, y)
    _bold(c, "Amount", 150, y)
    y -= 6
    _line(c, y)
    y -= 8
    _text(c, inv_data.get("description", "Freight Charge"), 22, y)
    _text(c, inv_data.get("charge_code", "AFRT"), 100, y)
    _text(c, f"{inv_data.get('amount_due', 0):,.2f}", 150, y)
    y -= 10
    vat_rate_shown = inv_data.get("vat_rate_shown", 0.05)
    vat_shown = round(float(inv_data.get("amount_due", 0)) * vat_rate_shown, 2)
    _text(c, f"VAT ({int(vat_rate_shown*100)}%): {vat_shown:,.2f}", 120, y)
    y -= 7
    _bold(c, f"Total: {inv_data.get('total', 0):,.2f}", 120, y)


INVOICES = [
    # ─── 1. AFRT Transworld matched ──────────────────────────────────────────────
    {"file": "01_AFRT_TW_Dubai_Mumbai_matched.pdf", "layout": "transworld",
     "invoice_number": "1338/25-26", "invoice_date": "28-Feb-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True},
    {"file": "02_AFRT_TW_Dubai_Delhi_matched.pdf", "layout": "transworld",
     "invoice_number": "1339/25-26", "invoice_date": "01-Mar-2026",
     "shipment_id": "SHP-202606210089", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 2150.40, "vat_rate": 0.05, "route": "Dubai to Delhi",
     "show_vat": True},
    {"file": "03_AFRT_TW_Dubai_London_matched.pdf", "layout": "transworld",
     "invoice_number": "1340/25-26", "invoice_date": "05-Mar-2026",
     "shipment_id": "SHP-202605180045", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 11950.00, "vat_rate": 0.05, "route": "Dubai to London",
     "show_vat": True},
    {"file": "04_AFRT_TW_Dubai_Mumbai_tolerance.pdf", "layout": "transworld",
     "invoice_number": "1341/25-26", "invoice_date": "10-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73125.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True},
    {"file": "05_AFRT_TW_Dubai_Delhi_tolerance.pdf", "layout": "transworld",
     "invoice_number": "1342/25-26", "invoice_date": "12-Mar-2026",
     "shipment_id": "SHP-202606210089", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 2200.00, "vat_rate": 0.05, "route": "Dubai to Delhi",
     "show_vat": True},
    {"file": "06_AFRT_TW_no_vat_shown.pdf", "layout": "transworld",
     "invoice_number": "1343/25-26", "invoice_date": "15-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": False},
    {"file": "07_AFRT_TW_Dubai_Singapore_mismatch.pdf", "layout": "transworld",
     "invoice_number": "1344/25-26", "invoice_date": "18-Mar-2026",
     "shipment_id": "SHP-EXCEPTION-1001", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 22000.00, "vat_rate": 0.05, "route": "Dubai to Singapore",
     "show_vat": True,
     "exception_note": "Demo: amount intentionally outside tolerance for exception test."},
    {"file": "08_AFRT_TW_Dubai_London_mismatch.pdf", "layout": "transworld",
     "invoice_number": "1345/25-26", "invoice_date": "20-Mar-2026",
     "shipment_id": "SHP-EXCEPTION-1001", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 14800.00, "vat_rate": 0.05, "route": "Dubai to London",
     "show_vat": True},
    {"file": "09_AFRT_TW_Mumbai_only_amount.pdf", "layout": "transworld",
     "invoice_number": "1346/25-26", "invoice_date": "22-Mar-2026",
     "shipment_id": "", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True},
    {"file": "10_AFRT_TW_Delhi_partial.pdf", "layout": "transworld",
     "invoice_number": "1347/25-26", "invoice_date": "25-Mar-2026",
     "shipment_id": "SHP-202606210089", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 2150.40, "vat_rate": 0.05, "route": "Dubai to Delhi",
     "show_vat": True},
    # ─── 11. DFRT Aramex delivery invoices ───────────────────────────────────────
    {"file": "11_DFRT_Aramex_Dubai_AbuDhabi_matched.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-001", "invoice_date": "02-Mar-2026",
     "shipment_id": "SHP-202605290031", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 850.00, "vat_rate": 0.05, "route": "Dubai to Abu Dhabi"},
    {"file": "12_DFRT_Aramex_Dubai_Sharjah_matched.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-002", "invoice_date": "05-Mar-2026",
     "shipment_id": "SHP-202606010055", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 1200.00, "vat_rate": 0.05, "route": "Dubai to Sharjah"},
    {"file": "13_DFRT_Aramex_Dubai_AbuDhabi_tolerance.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-003", "invoice_date": "08-Mar-2026",
     "shipment_id": "SHP-202605290031", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 870.00, "vat_rate": 0.05, "route": "Dubai to Abu Dhabi"},
    {"file": "14_DFRT_Aramex_missing_shipment.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-004", "invoice_date": "10-Mar-2026",
     "shipment_id": "", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 1100.00, "vat_rate": 0.05, "route": "Dubai to Ajman"},
    {"file": "15_DFRT_Aramex_Sharjah_mismatch.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-005", "invoice_date": "12-Mar-2026",
     "shipment_id": "SHP-202606010055", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 1850.00, "vat_rate": 0.05, "route": "Dubai to Sharjah"},
    # ─── 16. CUST DHL customs invoices ────────────────────────────────────────────
    {"file": "16_CUST_DHL_Dubai_NewYork_matched.pdf", "layout": "dhl",
     "invoice_number": "DHL-CUST-001", "invoice_date": "04-Mar-2026",
     "shipment_id": "SHP-202605110018", "charge_code": "CUST",
     "description": "Customs Clearance & Documentation Fee", "currency": "AED",
     "amount_due": 3500.00, "vat_rate": 0.0, "route": "Dubai to New York",
     "origin": "DXB", "destination": "JFK"},
    {"file": "17_CUST_DHL_Dubai_Paris_matched.pdf", "layout": "dhl",
     "invoice_number": "DHL-CUST-002", "invoice_date": "07-Mar-2026",
     "shipment_id": "SHP-202606050071", "charge_code": "CUST",
     "description": "Customs Clearance & Documentation Fee", "currency": "AED",
     "amount_due": 4200.00, "vat_rate": 0.0, "route": "Dubai to Paris",
     "origin": "DXB", "destination": "CDG"},
    {"file": "18_CUST_DHL_Dubai_London_matched.pdf", "layout": "dhl",
     "invoice_number": "DHL-CUST-003", "invoice_date": "09-Mar-2026",
     "shipment_id": "", "charge_code": "CUST",
     "description": "Customs Clearance & Documentation Fee", "currency": "AED",
     "amount_due": 2800.00, "vat_rate": 0.0, "route": "Dubai to London",
     "origin": "DXB", "destination": "LHR"},
    {"file": "19_CUST_DHL_wrong_vat.pdf", "layout": "dhl",
     "invoice_number": "DHL-CUST-004", "invoice_date": "11-Mar-2026",
     "shipment_id": "SHP-202605110018", "charge_code": "CUST",
     "description": "Customs Clearance Fee", "currency": "AED",
     "amount_due": 3500.00, "vat_rate": 0.10,
     "route": "Dubai to New York", "origin": "DXB", "destination": "JFK",
     "exception_note": "Demo: wrong VAT rate (10% applied instead of 0% for customs)."},
    {"file": "20_CUST_DHL_tolerance.pdf", "layout": "dhl",
     "invoice_number": "DHL-CUST-005", "invoice_date": "14-Mar-2026",
     "shipment_id": "SHP-202606050071", "charge_code": "CUST",
     "description": "Customs Clearance Fee", "currency": "AED",
     "amount_due": 4350.00, "vat_rate": 0.0,
     "route": "Dubai to Paris", "origin": "DXB", "destination": "CDG"},
    # ─── 21. WHSE warehouse invoices ──────────────────────────────────────────────
    {"file": "21_WHSE_GulfBridge_matched.pdf", "layout": "generic",
     "vendor": "Gulf Bridge Warehousing LLC", "address": "Dubai South, UAE",
     "invoice_number": "GBL-WHSE-001", "invoice_date": "01-Mar-2026",
     "shipment_id": "SHP-202604280062", "charge_code": "WHSE",
     "description": "Warehouse Storage and Handling Fee", "currency": "AED",
     "amount_due": 6500.00, "vat_rate": 0.05},
    {"file": "22_WHSE_GulfBridge_tolerance.pdf", "layout": "generic",
     "vendor": "Gulf Bridge Warehousing LLC", "address": "Dubai South, UAE",
     "invoice_number": "GBL-WHSE-002", "invoice_date": "05-Mar-2026",
     "shipment_id": "SHP-202604280062", "charge_code": "WHSE",
     "description": "Warehouse Storage and Handling Fee", "currency": "AED",
     "amount_due": 6650.00, "vat_rate": 0.05},
    {"file": "23_WHSE_GulfBridge_mismatch.pdf", "layout": "generic",
     "vendor": "Gulf Bridge Warehousing LLC", "address": "Dubai South, UAE",
     "invoice_number": "GBL-WHSE-003", "invoice_date": "10-Mar-2026",
     "shipment_id": "SHP-202604280062", "charge_code": "WHSE",
     "description": "Warehouse Storage and Handling Fee", "currency": "AED",
     "amount_due": 9200.00, "vat_rate": 0.05},
    {"file": "24_WHSE_GulfBridge_no_shipment.pdf", "layout": "generic",
     "vendor": "Gulf Bridge Warehousing LLC", "address": "Dubai South, UAE",
     "invoice_number": "GBL-WHSE-004", "invoice_date": "15-Mar-2026",
     "shipment_id": "", "charge_code": "WHSE",
     "description": "Monthly Warehouse Storage Fee", "currency": "AED",
     "amount_due": 6500.00, "vat_rate": 0.05},
    # ─── 25. TRANS Khalid transport invoices ──────────────────────────────────────
    {"file": "25_TRANS_Khalid_matched.pdf", "layout": "generic",
     "vendor": "Khalid General Transport LLC", "address": "Al Quoz, Dubai, UAE",
     "invoice_number": "KH-TRANS-001", "invoice_date": "03-Mar-2026",
     "shipment_id": "SHP-202605220039", "charge_code": "TRANS",
     "description": "Road Transport / Trucking Fee", "currency": "AED",
     "amount_due": 2800.00, "vat_rate": 0.05},
    {"file": "26_TRANS_Khalid_tolerance.pdf", "layout": "generic",
     "vendor": "Khalid General Transport LLC", "address": "Al Quoz, Dubai, UAE",
     "invoice_number": "KH-TRANS-002", "invoice_date": "06-Mar-2026",
     "shipment_id": "SHP-202605220039", "charge_code": "TRANS",
     "description": "Road Transport / Trucking Fee", "currency": "AED",
     "amount_due": 2860.00, "vat_rate": 0.05},
    {"file": "27_TRANS_Khalid_mismatch.pdf", "layout": "generic",
     "vendor": "Khalid General Transport LLC", "address": "Al Quoz, Dubai, UAE",
     "invoice_number": "KH-TRANS-003", "invoice_date": "09-Mar-2026",
     "shipment_id": "SHP-202605220039", "charge_code": "TRANS",
     "description": "Road Transport / Trucking Fee", "currency": "AED",
     "amount_due": 4200.00, "vat_rate": 0.05},
    {"file": "28_TRANS_Khalid_no_shipment_id.pdf", "layout": "generic",
     "vendor": "Khalid General Transport LLC", "address": "Al Quoz, Dubai, UAE",
     "invoice_number": "KH-TRANS-004", "invoice_date": "12-Mar-2026",
     "shipment_id": "", "charge_code": "TRANS",
     "description": "Road Transport / Trucking Fee", "currency": "AED",
     "amount_due": 2800.00, "vat_rate": 0.05},
    # ─── 29. Special error / exception cases ─────────────────────────────────────
    {"file": "29_DUPLICATE_TW_AFRT_same_as_01.pdf", "layout": "transworld",
     "invoice_number": "1338/25-26", "invoice_date": "28-Feb-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True,
     "exception_note": "Demo: duplicate of invoice 01 — should be flagged as DUPLICATE."},
    {"file": "30_DUPLICATE_Aramex_DFRT_same_as_11.pdf", "layout": "aramex",
     "invoice_number": "AR-2026-001", "invoice_date": "02-Mar-2026",
     "shipment_id": "SHP-202605290031", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 850.00, "vat_rate": 0.05, "route": "Dubai to Abu Dhabi"},
    {"file": "31_MISSING_INV_NUMBER_TW_AFRT.pdf", "layout": "transworld",
     "invoice_number": "", "invoice_date": "18-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True,
     "exception_note": "Demo: invoice number intentionally omitted."},
    {"file": "32_MISSING_INV_NUMBER_Aramex_DFRT.pdf", "layout": "aramex",
     "invoice_number": "", "invoice_date": "19-Mar-2026",
     "shipment_id": "", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 950.00, "vat_rate": 0.05, "route": "Dubai to Ras Al Khaimah"},
    {"file": "33_MISSING_INV_NUMBER_generic.pdf", "layout": "generic",
     "vendor": "FastFreight General Trading LLC", "address": "DAFZA, Dubai",
     "invoice_number": "", "invoice_date": "20-Mar-2026",
     "shipment_id": "", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 5500.00, "vat_rate": 0.05,
     "show_invoice_number": False},
    {"file": "34_WRONG_VAT_TW_AFRT.pdf", "layout": "transworld",
     "invoice_number": "1348/25-26", "invoice_date": "22-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.10, "route": "Dubai to Mumbai",
     "show_vat": True,
     "exception_note": "Demo: wrong VAT rate (10% instead of 5%) — should trigger VAT_MISMATCH."},
    {"file": "35_WRONG_VAT_Khalid_TRANS.pdf", "layout": "generic",
     "vendor": "Khalid General Transport LLC", "address": "Al Quoz, Dubai",
     "invoice_number": "KH-TRANS-005", "invoice_date": "23-Mar-2026",
     "shipment_id": "SHP-202605220039", "charge_code": "TRANS",
     "description": "Road Transport Fee", "currency": "AED",
     "amount_due": 2800.00, "vat_rate": 0.15,
     "exception_note": "Demo: wrong VAT rate 15%"},
    {"file": "36_MISSING_VENDOR_NAME.pdf", "layout": "generic",
     "vendor": "", "address": "Unknown Address, Dubai",
     "invoice_number": "UNK-2026-001", "invoice_date": "24-Mar-2026",
     "shipment_id": "", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 8000.00, "vat_rate": 0.05,
     "show_vendor": False},
    {"file": "37_MISSING_VENDOR_NAME_2.pdf", "layout": "generic",
     "vendor": "", "address": "Dubai, UAE",
     "invoice_number": "UNK-2026-002", "invoice_date": "25-Mar-2026",
     "shipment_id": "", "charge_code": "DFRT",
     "description": "Delivery Freight Charge", "currency": "AED",
     "amount_due": 1500.00, "vat_rate": 0.05,
     "show_vendor": False},
    {"file": "38_UNKNOWN_CHARGE_CODE.pdf", "layout": "generic",
     "vendor": "Global Cargo Services LLC", "address": "Dubai Airport FZ, UAE",
     "invoice_number": "GCS-2026-001", "invoice_date": "26-Mar-2026",
     "shipment_id": "", "charge_code": "XYZQ",
     "description": "Special Cargo Handling Fee", "currency": "AED",
     "amount_due": 3200.00, "vat_rate": 0.05},
    {"file": "39_AFRT_FedEx_Dubai_Mumbai.pdf", "layout": "generic",
     "vendor": "FedEx Express FZE", "address": "Dubai Airport FZ, UAE",
     "invoice_number": "FDX-2026-001", "invoice_date": "27-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "AED",
     "amount_due": 73000.00, "vat_rate": 0.05},
    {"file": "40_AFRT_TW_USD_currency_mismatch.pdf", "layout": "transworld",
     "invoice_number": "1349/25-26", "invoice_date": "28-Mar-2026",
     "shipment_id": "SHP-202604150026", "charge_code": "AFRT",
     "description": "Air Freight Charge", "currency": "USD",
     "amount_due": 19900.00, "vat_rate": 0.05, "route": "Dubai to Mumbai",
     "show_vat": True,
     "exception_note": "Demo: USD invoice vs AED expected — currency mismatch test."},
]


def generate_pdf(inv_data: dict, out_path: Path) -> None:
    vat_rate = inv_data.get("vat_rate", 0.05)
    amount = float(inv_data.get("amount_due", 0))
    vat_amount = round(amount * vat_rate, 2)
    total = round(amount + vat_amount, 2)
    inv_data = {**inv_data, "vat_amount": vat_amount, "total": total}

    cv = canvas.Canvas(str(out_path), pagesize=A4)
    layout = inv_data.get("layout", "generic")
    if layout == "transworld":
        layout_transworld(cv, inv_data)
    elif layout == "aramex":
        layout_aramex(cv, inv_data)
    elif layout == "dhl":
        layout_dhl(cv, inv_data)
    else:
        layout_generic(cv, inv_data)
    cv.save()


def main() -> None:
    email_subset = [0, 1, 2, 5, 6, 10, 11, 15, 16, 20, 21, 24, 25, 28, 29,
                    30, 31, 33, 36, 38]

    for i, inv in enumerate(INVOICES):
        out = SAMPLE_DIR / inv["file"]
        generate_pdf(inv, out)
        if i in email_subset:
            shutil.copy2(out, EMAIL_DIR / inv["file"])

    total = len(list(SAMPLE_DIR.glob("*.pdf")))
    email_total = len(list(EMAIL_DIR.glob("*.pdf")))
    print(f"Generated {total} samples in {SAMPLE_DIR}")
    print(f"Copied {email_total} samples to {EMAIL_DIR} (email inbox simulation)")


if __name__ == "__main__":
    main()
