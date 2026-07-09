"""
Vendor classifier — identifies which vendor issued a raw invoice.

Priority order:
  1. Pattern-based rules (fast, deterministic) from vendor_registry
  2. AI-based fallback via OpenAI (when pattern match confidence < threshold)

Returns (vendor_id, confidence_0_to_1, method_string)
"""

import re
from typing import Optional, Tuple

from .vendor_registry import VENDOR_REGISTRY


def _score_vendor(raw_text: str, vendor_id: str) -> Tuple[int, int, str]:
    """
    Score raw_text against one vendor's identification patterns.

    Returns (total_score, best_single_weight, best_matched_desc).

    - best_single_weight: used for threshold check (one strong signal must exist)
    - total_score: used for ranking (sum of ALL matched weights — breaks ties
      in favour of vendors whose name, invoice prefix, AND account code all match)
    """
    vendor = VENDOR_REGISTRY.get(vendor_id, {})
    patterns = vendor.get("identification", {}).get("patterns", [])
    text_lower = raw_text.lower()

    total_score = 0
    best_single = 0
    best_desc = ""

    for rule in patterns:
        rule_type = rule.get("type", "")
        weight = rule.get("weight", 50)
        matched = False

        if rule_type == "contains":
            matched = rule["value"].lower() in text_lower
        elif rule_type == "regex":
            matched = bool(re.search(rule["pattern"], raw_text, re.IGNORECASE))

        if matched:
            total_score += weight
            if weight > best_single:
                best_single = weight
                best_desc = rule.get("value", rule.get("pattern", ""))

    return total_score, best_single, best_desc


def classify_vendor(raw_text: str) -> Tuple[str, float, str]:
    """
    Identify vendor from raw OCR text using pattern rules.
    Returns: (vendor_id, confidence_0_to_1, method_used)
    """
    best_vendor_id = "UNKNOWN"
    best_total = 0
    best_desc = ""

    for vendor_id, vendor in VENDOR_REGISTRY.items():
        threshold = vendor.get("identification", {}).get("threshold", 80)
        total, single, desc = _score_vendor(raw_text, vendor_id)

        # Must have at least one strong signal (single >= threshold) to qualify,
        # then rank by total accumulated score.
        if single >= threshold and total > best_total:
            best_total = total
            best_vendor_id = vendor_id
            best_desc = desc

    if best_vendor_id == "UNKNOWN":
        return "UNKNOWN", 0.0, "no_pattern_matched"

    # Confidence capped at 1.0; scale on 100 (single perfect match = 1.0)
    confidence = min(best_total / 100.0, 1.0)
    method = f"pattern_match:{best_desc[:40]}" if best_desc else "pattern_match"
    return best_vendor_id, confidence, method


def classify_vendor_with_ai(
    raw_text: str,
    openai_client=None,
) -> Tuple[str, float, str]:
    """
    AI-based vendor classification (fallback when pattern match fails or confidence < 0.5).
    Uses OpenAI to classify from the vendor registry list.
    """
    if openai_client is None:
        return "UNKNOWN", 0.0, "ai_client_not_provided"

    vendor_list_lines: list = [
        f"  - {vid}: {v['name']} (category: {v['category']})"
        for vid, v in VENDOR_REGISTRY.items()
    ]
    vendor_list = "\n".join(vendor_list_lines)

    prompt = f"""You are classifying a logistics invoice to identify which vendor issued it.

Known vendors:
{vendor_list}
  - UNKNOWN: vendor not in the list

Respond ONLY with a valid JSON object:
{{
  "vendor_id": "VENDOR_ID_FROM_LIST_OR_UNKNOWN",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<brief one-line reason>"
}}

Invoice text (first 2000 chars):
{raw_text[:2000]}"""

    try:
        import json
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        vendor_id = result.get("vendor_id", "UNKNOWN")
        if vendor_id not in VENDOR_REGISTRY:
            vendor_id = "UNKNOWN"
        confidence = float(result.get("confidence", 0.5))
        reasoning = result.get("reasoning", "")
        return vendor_id, confidence, f"ai_classification:{reasoning[:60]}"
    except Exception as exc:
        return "UNKNOWN", 0.0, f"ai_error:{exc}"


def classify_vendor_full(
    raw_text: str,
    ai_mode: str = "mock",
    openai_client=None,
    ai_fallback_threshold: float = 0.5,
) -> Tuple[str, float, str]:
    """
    Full classification pipeline:
      1. Try pattern-based classification
      2. If confidence < ai_fallback_threshold AND ai_mode == "openai" → try AI
      3. Return best result
    """
    vendor_id, confidence, method = classify_vendor(raw_text)

    if confidence < ai_fallback_threshold and ai_mode == "openai" and openai_client is not None:
        ai_vid, ai_conf, ai_method = classify_vendor_with_ai(raw_text, openai_client)
        if ai_conf > confidence:
            return ai_vid, ai_conf, ai_method

    return vendor_id, confidence, method
