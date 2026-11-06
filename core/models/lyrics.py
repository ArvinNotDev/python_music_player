"""Structured plain and time-synchronized lyrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class LyricsLine:
    text: str
    timestamp_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("lyrics line text must be a string")
        if self.timestamp_ms is not None and self.timestamp_ms < 0:
            raise ValueError("lyrics timestamp cannot be negative")


@dataclass(slots=True)
class LyricsDocument:
    lines: list[LyricsLine] = field(default_factory=list)
    format: str = "plain"
    language: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.format not in {"plain", "lrc"}:
            raise ValueError("format must be 'plain' or 'lrc'")

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    def to_plain_text(self) -> str:
        return self.text

    def to_lrc(self) -> str:
        out = [f"[{key}:{value}]" for key, value in self.metadata.items()]
        for line in self.lines:
            if line.timestamp_ms is None:
                out.append(line.text)
            else:
                minutes, remainder = divmod(line.timestamp_ms, 60_000)
                seconds, millis = divmod(remainder, 1000)
                out.append(f"[{minutes:02d}:{seconds:02d}.{millis // 10:02d}]{line.text}")
        return "\n".join(out)
