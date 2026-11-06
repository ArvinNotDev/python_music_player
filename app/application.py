"""Executable application lifecycle."""

from __future__ import annotations

from collections.abc import Sequence

from .bootstrap import build_runtime


def run_application(argv: Sequence[str] | None = None) -> int:
    runtime = build_runtime(argv)
    try:
        runtime.window.show()
        return runtime.app.exec()
    finally:
        runtime.shutdown()
