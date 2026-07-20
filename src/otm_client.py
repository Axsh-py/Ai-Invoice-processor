"""
Oracle OTM REST API client.

Base URL  : OTM_BASE_URL  (env)
Auth      : HTTP Basic — OTM_USERNAME / OTM_PASSWORD  (env, never hardcoded)
API root  : /logisticsRestApi/resources-int/v2/
Mode      : OTM_API_MODE=live|mock  (default: mock)

Public functions:
    test_connection()
    get_invoices(limit, offset, query)
    get_invoice(invoice_gid)
    get_documents(invoice_gid)
    view_document(document_gid)  -> raw bytes
    get_shipment_costs(shipment_gid)
    get_shipments(query, fields, expand)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from .config import get_secret, DATA_DIR

logger = logging.getLogger(__name__)

_API_ROOT = "/logisticsRestApi/resources-int/v2"
_TIMEOUT = 30
_MAX_RETRIES = 2


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_url() -> str:
    return get_secret("OTM_BASE_URL", "").rstrip("/")


def _auth() -> HTTPBasicAuth:
    return HTTPBasicAuth(
        get_secret("OTM_USERNAME", ""),
        get_secret("OTM_PASSWORD", ""),
    )


def api_mode() -> str:
    return get_secret("OTM_API_MODE", "mock").lower()


def default_domain() -> str:
    return get_secret("OTM_DOMAIN", "TW/DWCLLC/DXB")


def _url(path: str) -> str:
    return f"{_base_url()}{_API_ROOT}/{path.lstrip('/')}"


def _get(path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    """GET with retry. Never raises — always returns dict with success/error."""
    url = _url(path)
    last_error = "Unknown error"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, auth=_auth(), params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return {"success": True, "data": resp.json(), "status_code": resp.status_code}
        except requests.exceptions.HTTPError:
            last_error = f"HTTP {resp.status_code} — {resp.text[:200]}"
            if resp.status_code in (401, 403, 404):
                break  # no point retrying auth/not-found errors
        except requests.exceptions.Timeout:
            last_error = "Request timed out"
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
        except Exception as e:
            last_error = str(e)
            break

    logger.error("OTM GET failed — %s — %s", path, last_error)
    return {"success": False, "error": last_error, "status_code": 0}


def _get_bytes(path: str) -> Dict[str, Any]:
    """GET raw bytes for document downloads."""
    url = _url(path)
    try:
        resp = requests.get(url, auth=_auth(), timeout=_TIMEOUT)
        resp.raise_for_status()
        return {
            "success": True,
            "content": resp.content,
            "content_type": resp.headers.get("Content-Type", "application/octet-stream"),
            "status_code": resp.status_code,
        }
    except Exception as e:
        logger.error("OTM document download failed — %s — %s", path, e)
        return {"success": False, "error": str(e), "status_code": 0}


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _mock(filename: str) -> Dict[str, Any]:
    path = DATA_DIR / "mock_otm" / filename
    if path.exists():
        try:
            return {
                "success": True,
                "data": json.loads(path.read_text(encoding="utf-8")),
                "status_code": 200,
                "mock": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Mock parse error: {e}", "status_code": 0}
    return {"success": False, "error": f"Mock file not found: {filename}", "status_code": 0}


# ── Public API ────────────────────────────────────────────────────────────────

def test_connection() -> Dict[str, Any]:
    """Test OTM connectivity. Safe to call from UI."""
    if api_mode() == "mock":
        return {"success": True, "mode": "mock", "message": "Mock mode — no real API call made"}

    if not _base_url():
        return {"success": False, "mode": "live", "error": "OTM_BASE_URL not set in .env / Secrets"}
    if not get_secret("OTM_USERNAME"):
        return {"success": False, "mode": "live", "error": "OTM_USERNAME not set"}

    result = _get("invoices", params={"limit": 1})
    if result["success"]:
        return {
            "success": True,
            "mode": "live",
            "message": f"Connected — {_base_url()}",
            "status_code": result["status_code"],
        }
    return {"success": False, "mode": "live", "error": result.get("error", "Unknown"), "status_code": result.get("status_code", 0)}


def get_invoices(limit: int = 50, offset: int = 0, query: Optional[str] = None) -> Dict[str, Any]:
    """
    List OTM invoices.
    query: OData filter e.g. 'invoiceStatus eq "APPROVED"'
    """
    if api_mode() == "mock":
        return _mock("get_invoices_response.json")

    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if query:
        params["q"] = query
    return _get("invoices", params=params)


def get_invoice(invoice_gid: str) -> Dict[str, Any]:
    """
    Fetch a single OTM invoice by GID.
    invoice_gid: 'TW/TIL/MUM.1181202512300002'  or  'TW/DWCLLC/DXB.INV-001'
    """
    if api_mode() == "mock":
        return _mock("get_invoice_single_response.json")

    return _get(f"invoices/{invoice_gid}")


def get_documents(invoice_gid: str) -> Dict[str, Any]:
    """
    Fetch document metadata attached to an OTM invoice.
    invoice_gid: 'TW/TIL/MUM.1181202512300002'
    """
    if api_mode() == "mock":
        return _mock("get_documents_response.json")

    return _get(f"invoices/{invoice_gid}/documents")


def view_document(document_gid: str) -> Dict[str, Any]:
    """
    Download raw PDF bytes for a document.
    document_gid: 'TW/TIL/MUM.104444-COO BILLS-001'
    Returns dict with 'content' (bytes) and 'content_type'.
    """
    if api_mode() == "mock":
        return {
            "success": True,
            "mock": True,
            "content": b"%PDF-1.4 mock document",
            "content_type": "application/pdf",
            "status_code": 200,
        }

    return _get_bytes(f"custom-actions/download/documents/{document_gid}/contents")


def get_shipments(
    query: Optional[str] = None,
    fields: Optional[str] = None,
    expand: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Query OTM shipments with optional OData filter."""
    if api_mode() == "mock":
        return {"success": True, "data": {"items": [], "totalResults": 0}, "mock": True}

    params: Dict[str, Any] = {"limit": limit}
    if query:
        params["q"] = query
    if fields:
        params["fields"] = fields
    if expand:
        params["expand"] = expand
    return _get("shipments", params=params)


def get_shipment_costs(shipment_gid: str) -> Dict[str, Any]:
    """Get cost line items for a specific shipment."""
    if api_mode() == "mock":
        return {"success": True, "data": {"items": []}, "mock": True}

    return _get(f"shipments/{shipment_gid}/costs")


def get_accessorial_codes(query: Optional[str] = None) -> Dict[str, Any]:
    """Lookup OTM accessorial/charge codes."""
    if api_mode() == "mock":
        return {"success": True, "data": {"items": []}, "mock": True}

    params = {}
    if query:
        params["q"] = query
    return _get("accessorialCodes", params=params)
