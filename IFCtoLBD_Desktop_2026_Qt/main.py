#!/usr/bin/env python3
"""Launch the Qt replica of IFCtoLBD_Desktop_2026 (Python converter edition)."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_ifctolbd_importable() -> None:
    try:
        import ifctolbd  # noqa: F401
    except ImportError:
        parent = str(Path(__file__).resolve().parents[1])
        sys.path.insert(0, parent)


def main() -> int:
    _ensure_ifctolbd_importable()
    from desktop.main_window import main as run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
