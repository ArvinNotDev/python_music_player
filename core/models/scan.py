"""Library scan outcome."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScanResult:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
    errors: list[str] = field(default_factory=list)
    canceled: bool = False
    total: int = 0

    @property
    def succeeded(self) -> bool:
        return not self.errors
