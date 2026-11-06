"""Public playback state values emitted by :class:`PlaybackController`."""

from enum import Enum


class PlaybackState(str, Enum):
    """Playback lifecycle state.

    ``loading`` is entered when a source is requested. ``playing`` and
    ``paused`` are only entered after the backend reports those actual states.
    """

    STOPPED = "stopped"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"
