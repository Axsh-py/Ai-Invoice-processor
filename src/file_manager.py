import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

from .config import ORIGINALS_DIR, WORKING_DIR


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _year_month_dirs(base: Path) -> Path:
    now = datetime.utcnow()
    target = base / str(now.year) / f"{now.month:02d}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_original_and_copy(uploaded_file, source: str = "manual_upload") -> Dict:
    """Accept a Streamlit UploadedFile, save original and working copy. Return file record dict."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = uploaded_file.name.replace(" ", "_")
    orig_dir = _year_month_dirs(ORIGINALS_DIR)
    work_dir = _year_month_dirs(WORKING_DIR)
    original_path = orig_dir / f"{ts}_{source}_original_{safe_name}"
    working_path = work_dir / f"{ts}_{source}_working_{safe_name}"
    data = uploaded_file.getbuffer()
    with open(original_path, "wb") as f:
        f.write(data)
    shutil.copy2(original_path, working_path)
    return {
        "source": source,
        "source_type": source,
        "original_file_path": str(original_path),
        "working_copy_path": str(working_path),
        "file_hash": sha256_file(original_path),
        "original_filename": uploaded_file.name,
        "file_size": len(data),
    }


def save_path_as_original_and_copy(path: str, source: str = "sample_email_intake") -> Dict:
    """Accept a file system path (sample/email invoice), save original and working copy. Return file record dict."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    src = Path(path)
    orig_dir = _year_month_dirs(ORIGINALS_DIR)
    work_dir = _year_month_dirs(WORKING_DIR)
    original_path = orig_dir / f"{ts}_{source}_original_{src.name}"
    working_path = work_dir / f"{ts}_{source}_working_{src.name}"
    shutil.copy2(src, original_path)
    shutil.copy2(original_path, working_path)
    return {
        "source": source,
        "source_type": source,
        "original_file_path": str(original_path),
        "working_copy_path": str(working_path),
        "file_hash": sha256_file(original_path),
        "original_filename": src.name,
        "file_size": original_path.stat().st_size,
    }
