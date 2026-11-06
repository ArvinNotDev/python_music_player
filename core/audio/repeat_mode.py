"""Independent repeat behavior for queue playback."""

from enum import Enum


class RepeatMode(str, Enum):
    """Repeat policy accepted by the playback controller."""

    OFF = "off"
    ALL = "all"
    ONE = "one"

    @classmethod
    def coerce(cls, value: "RepeatMode | str") -> "RepeatMode":
        """Return a mode from an enum value or its case-insensitive string."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(f"repeat mode must be one of: {choices}") from exc
