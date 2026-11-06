"""Locate bundled application assets in source and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Return an asset path for both source runs and frozen PyInstaller apps."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    base = Path(bundle_root) if bundle_root else Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)
