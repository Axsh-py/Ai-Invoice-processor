import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DATA_DIR

# Words that don't help identify a company — ignored during fuzzy matching
_STOP_WORDS = {"pvt", "ltd", "private", "limited", "llc", "fze", "inc", "ag",
               "gmbh", "co", "corp", "company", "india", "uae", "express",
               "international", "group", "holdings", "and", "the"}

_SHIPMENTS: Optional[list] = None
_SERVICE_PROVIDERS: Optional[list] = None
_CHARGE_MASTER: Optional[dict] = None


def _load_shipments() -> list:
    global _SHIPMENTS
    if _SHIPMENTS is not None:
        return _SHIPMENTS
    path = DATA_DIR / "mock_shipments.json"
    _SHIPMENTS = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return _SHIPMENTS


def _load_service_providers() -> list:
    global _SERVICE_PROVIDERS
    if _SERVICE_PROVIDERS is not None:
        return _SERVICE_PROVIDERS
    path = DATA_DIR / "service_providers.json"
    _SERVICE_PROVIDERS = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return _SERVICE_PROVIDERS


def _load_charge_master() -> dict:
    global _CHARGE_MASTER
    if _CHARGE_MASTER is not None:
        return _CHARGE_MASTER
    path = DATA_DIR / "charge_code_master.json"
    _CHARGE_MASTER = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _CHARGE_MASTER


def match_charge_code(code: Optional[str]) -> Optional[Dict[str, Any]]:
    if not code:
        return None
    master = _load_charge_master()
    return master.get(code.upper())


def _brand_words(name: str) -> list:
    """Extract significant brand words from a company name, ignoring stop words."""
    words = re.split(r"[\s\-\.,\/\(\)]+", name.lower())
    return [w for w in words if len(w) > 1 and w not in _STOP_WORDS]


def match_service_provider(
    vendor_name: Optional[str],
    service_provider_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    providers = _load_service_providers()

    # 1. Exact service_provider_id match
    if service_provider_id:
        for p in providers:
            if p["service_provider_id"] == service_provider_id:
                return p

    if not vendor_name:
        return None

    vendor_lower = vendor_name.lower().strip()

    for p in providers:
        # 2. Direct substring match (exact name contains or is contained)
        if p["name"].lower() in vendor_lower or vendor_lower in p["name"].lower():
            return p

        # 3. Alias match — normalize both sides to strip hyphens/spaces
        alias_norm = p["alias"].lower().replace("-", "").replace(" ", "")
        vendor_norm = vendor_lower.replace("-", "").replace(" ", "")
        if alias_norm in vendor_norm:
            return p

        # 4. name_keywords match — word-boundary check to avoid substring false positives
        for kw in p.get("name_keywords", []):
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', vendor_lower):
                return p

        # 5. Brand-word overlap — "Hapag-Lloyd India Pvt" vs "Hapag-Lloyd AG"
        #    Match if the top-2 brand words of the master appear in the invoice vendor name
        master_words = _brand_words(p["name"])
        if len(master_words) >= 2:
            vendor_words = set(_brand_words(vendor_name))
            # At least 2 significant words must match
            overlap = sum(1 for w in master_words[:3] if w in vendor_words)
            if overlap >= 2:
                return p

    return None


def match_shipment(extracted: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Score all mock shipments and return the best match."""
    shipments = _load_shipments()
    if not shipments:
        return None

    code = (extracted.get("charge_code") or "").upper()
    amount = float(extracted.get("amount_due") or 0)
    invoice_no = extracted.get("invoice_number", "")
    shipment_id = (extracted.get("shipment_id") or "").strip()
    mbl_number = (extracted.get("mbl_number") or "").strip()
    vendor = (extracted.get("vendor_name") or "").lower()
    route = (extracted.get("route_or_port") or "").lower()

    scored = []
    for s in shipments:
        score = 0
        if shipment_id and s["shipment_id"] == shipment_id:
            score += 50
        if mbl_number and s.get("mbl_number", "") == mbl_number:
            score += 50
        if s.get("invoice_number_hint", "") == invoice_no:
            score += 30
        if s.get("expected_charge_code", "").upper() == code:
            score += 25
        sp_id = extracted.get("service_provider_id") or ""
        if sp_id and s.get("service_provider_id") == sp_id:
            score += 20
        elif vendor and s.get("vendor_name", "").lower() in vendor:
            score += 10
        if route:
            shipment_route = s.get("route", "").lower()
            if any(word in shipment_route for word in route.split() if len(word) > 3):
                score += 10
        tol = float(s.get("tolerance_amount", 100))
        diff = abs(float(s.get("expected_amount", 0)) - amount)
        if diff <= tol:
            score += 20
        elif amount > 0:
            score += max(0, 10 - int(diff / 1000))
        scored.append((score, diff, s))

    scored.sort(key=lambda x: (-x[0], x[1]))
    best_score, best_diff, best = scored[0]
    # Require at least one identifying signal (10 pts = charge code or partial amount alone is not enough)
    if best_score < 10:
        return None
    return best


def enrich_invoice(
    extracted: Dict[str, Any],
    matched_shipment: Optional[Dict],
    matched_sp: Optional[Dict],
    matched_charge: Optional[Dict],
) -> Dict[str, Any]:
    """Fill missing OTM fields using matched reference data. Returns enriched copy."""
    result = dict(extracted)

    if matched_shipment:
        if not result.get("shipment_id"):
            result["shipment_id"] = matched_shipment.get("shipment_id")
        if not result.get("route_or_port"):
            result["route_or_port"] = matched_shipment.get("route")
        # Only fill currency from shipment when invoice has none; never overwrite a known currency
        if not result.get("currency"):
            shipment_currency = matched_shipment.get("currency")
            if shipment_currency:
                result["currency"] = shipment_currency

    if matched_sp:
        if not result.get("service_provider_id"):
            result["service_provider_id"] = matched_sp.get("service_provider_id")
        if not result.get("vendor_name"):
            result["vendor_name"] = matched_sp.get("name")

    if matched_charge:
        if not result.get("charge_description"):
            result["charge_description"] = matched_charge.get("description")
        if not result.get("invoice_type"):
            result["invoice_type"] = matched_charge.get("invoice_type")
        if not result.get("invoice_category"):
            result["invoice_category"] = matched_charge.get("category")

    return result
