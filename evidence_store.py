"""Shared, UI-independent evidence file utilities."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_name(value: str, fallback: str = "case") -> str:
    """Convert user-controlled text to a safe, short directory component."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return (cleaned[:80] or fallback)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted runs do not leave partial metadata."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)



def write_manifest(case_dir: Path) -> None:
    entries = []
    for path in sorted(case_dir.rglob("*")):
        if path.is_file() and path != case_dir / "manifest.sha256" and not path.name.endswith(".tmp"):
            entries.append(f"{sha256_file(path)}  {path.relative_to(case_dir).as_posix()}")
    temporary = case_dir / "manifest.sha256.tmp"
    temporary.write_text("\n".join(entries) + "\n", encoding="utf-8")
    temporary.replace(case_dir / "manifest.sha256")
