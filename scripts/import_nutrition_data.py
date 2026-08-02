"""Explicit offline normalizer for a pinned local FDC JSON subset.

This command never reads an API key and never performs network I/O. Download
and checksum verification are deliberate operator steps documented in the
source manifest; runtime application code does not import or call this script.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.nutrition.importers import import_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    import_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
