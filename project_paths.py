"""Repository root and capture paths shared by analysis scripts."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CAPTURES_DIR = REPO_ROOT / "captures"


def find_latest_capture_pair(captures_dir: Path | None = None) -> tuple[Path, Path]:
    """Return (path_650, path_850) for the newest timestamp that has both wavelengths."""
    d = captures_dir or CAPTURES_DIR
    if not d.is_dir():
        raise FileNotFoundError(f"Captures folder missing: {d}. Run capture on Pi then sync.")

    by_prefix: dict[str, Path] = {}
    for p in d.glob("*_850nm.png"):
        prefix = p.name.replace("_850nm.png", "")
        by_prefix[prefix] = p

    candidates = sorted(d.glob("*_650nm.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p650 in candidates:
        prefix = p650.name.replace("_650nm.png", "")
        if prefix in by_prefix:
            return p650, by_prefix[prefix]

    raise FileNotFoundError(
        f"No matching *_650nm.png + *_850nm.png pair under {d}."
    )


def pair_from_basenames(
    name_650: str, name_850: str, captures_dir: Path | None = None
) -> tuple[Path, Path]:
    """Resolve a 650/850 pair under captures/ by filename."""
    d = captures_dir or CAPTURES_DIR
    p650 = d / name_650
    p850 = d / name_850
    if not p650.is_file():
        raise FileNotFoundError(f"Missing 650 image: {p650}")
    if not p850.is_file():
        raise FileNotFoundError(f"Missing 850 image: {p850}")
    return p650, p850
