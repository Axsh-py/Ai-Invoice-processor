import os
import re
from pathlib import Path

import platform as _platform
_TESSERACT_DEFAULT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if _platform.system() == "Windows" else "tesseract"
)

# Invoice keywords — if digital text has at least 2 of these it's usable
_INVOICE_KEYWORDS = [
    "invoice", "amount", "total", "date", "vendor", "currency",
    "charge", "tax", "vat", "gst", "freight", "bill", "payment",
    "due", "service", "shipment", "maersk", "dhl", "aramex",
]


def _configure_tesseract() -> bool:
    try:
        import pytesseract
        cmd = os.environ.get("TESSERACT_CMD", _TESSERACT_DEFAULT)
        pytesseract.pytesseract.tesseract_cmd = cmd
        return Path(cmd).exists()
    except ImportError:
        return False


def _text_quality_score(text: str) -> int:
    """
    Score how usable a piece of extracted text is for invoice parsing.
    Returns 0–100. Above 40 = good enough, no need for OCR.
    """
    if not text or len(text.strip()) < 30:
        return 0

    t = text.lower()

    # 1. keyword hits (each keyword = +10 points, max 50)
    keyword_hits = sum(1 for kw in _INVOICE_KEYWORDS if kw in t)
    score = min(keyword_hits * 10, 50)

    # 2. has numbers (amounts/dates) = +20
    if re.search(r"\d{2,}", text):
        score += 20

    # 3. printable ratio — scanned garbage has lots of weird chars
    printable = sum(1 for c in text if c.isprintable())
    ratio = printable / max(len(text), 1)
    if ratio >= 0.95:
        score += 20
    elif ratio >= 0.85:
        score += 10

    # 4. very short even if clean = penalty
    if len(text.strip()) < 100:
        score -= 15

    return max(score, 0)


def _digital_extract(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception:
        return ""


def _pdf_to_images(path: str):
    """Render PDF pages to PIL Images via PyMuPDF (no poppler needed)."""
    import fitz
    from PIL import Image
    import io

    doc = fitz.open(path)
    images = []
    try:
        for page in doc:
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom → ~300 DPI effective
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            images.append(img)
    finally:
        doc.close()
    return images


def _image_to_text(img) -> str:
    import pytesseract
    config = r"--oem 3 --psm 6"
    return pytesseract.image_to_string(img, config=config)


# ─── public API ──────────────────────────────────────────────────────────────

def extract_text_from_pdf(path: str) -> tuple:
    """
    Smart extraction — no manual mode selection needed.

    Logic:
      1. Try digital text extraction (fast, zero cost).
      2. Score the quality of extracted text.
      3. If quality is good (score >= 40) → use digital text directly.
      4. If quality is poor (scanned PDF, image-based) → run Tesseract OCR.
      5. If Tesseract not available → return digital text with a warning.

    Returns: (text: str, method_used: str)
      method_used is "digital" or "tesseract" — shown in UI for transparency.
    """
    digital_text = _digital_extract(path)
    score = _text_quality_score(digital_text)

    if score >= 40:
        return digital_text, "digital"

    # Digital text is poor — try Tesseract
    if not _configure_tesseract():
        # Tesseract not installed — return whatever digital gave us
        return digital_text, "digital_fallback"

    try:
        images = _pdf_to_images(path)
        pages_text = [_image_to_text(img) for img in images]
        ocr_text = "\n".join(pages_text).strip()
        return ocr_text, "tesseract"
    except Exception as exc:
        return digital_text, f"digital_fallback:{exc}"


def tesseract_ocr_image(path: str) -> tuple:
    """
    Run Tesseract on an image file (PNG, JPG, TIFF).
    Returns: (text: str, method_used: str)
    """
    if not _configure_tesseract():
        return "TESSERACT_NOT_FOUND", "error"
    try:
        from PIL import Image
        import pytesseract
        with Image.open(path) as img:
            config = r"--oem 3 --psm 6"
            text = pytesseract.image_to_string(img, config=config)
        return text, "tesseract"
    except Exception as exc:
        return f"TESSERACT_IMAGE_OCR_FAILED: {exc}", "error"


def tesseract_available() -> bool:
    return _configure_tesseract()


def ocr_space_file(path: str, api_key: str = "helloworld") -> tuple:
    """Legacy OCR.space — kept for compatibility."""
    import requests
    url = "https://api.ocr.space/parse/image"
    try:
        with open(path, "rb") as f:
            response = requests.post(
                url,
                files={"file": f},
                data={"apikey": api_key, "language": "eng", "isOverlayRequired": False, "OCREngine": 2},
                timeout=60,
            )
        data = response.json()
        if data.get("IsErroredOnProcessing"):
            return "OCR_SPACE_ERROR: " + str(data.get("ErrorMessage")), "error"
        text = "\n".join([r.get("ParsedText", "") for r in data.get("ParsedResults", [])]).strip()
        return text, "ocr_space"
    except Exception as exc:
        return f"OCR_SPACE_FAILED: {exc}", "error"
