"""Application composition and adapters for the presentation contracts."""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from core.audio import PlaybackController
from core.models import LyricsDocument
from services.domain_services import DomainServices

logger = logging.getLogger(__name__)


def _track_identity(track: Any):
    if track is None:
        return None
    for key in ("id", "track_id", "path", "file_path"):
        value = track.get(key) if isinstance(track, dict) else getattr(track, key, None)
        if value is not None:
            return value
    return track


def _identifier(track: Any) -> int:
    identifier = _track_identity(track)
    if isinstance(identifier, bool) or not isinstance(identifier, int):
        raise ValueError("The selected track is not stored in the music library")
    return identifier


class MetadataUiAdapter:
    """Translate the UI's Track-object API to the domain's integer-ID API."""

    def __init__(self, metadata_service):
        self._service = metadata_service

    def read_metadata(self, track: Any) -> dict[str, Any]:
        result = self._service.read_metadata(_identifier(track))
        if isinstance(result, dict):
            return result
        if is_dataclass(result):
            return asdict(result)
        return dict(vars(result))

    def write_metadata(self, track: Any, changes: dict[str, Any]):
        values = dict(changes)
        artwork_path = values.pop("artwork_path", None)
        artwork = values.pop("artwork", ...)
        identifier = _identifier(track)

        if artwork_path is not None:
            image_bytes = Path(artwork_path).expanduser().read_bytes()
            self._service.write_artwork(identifier, image_bytes)
        elif artwork is None:
            self._service.write_artwork(identifier, None)
        elif isinstance(artwork, (bytes, bytearray)):
            self._service.write_artwork(identifier, bytes(artwork))
        elif isinstance(artwork, (str, Path)):
            self._service.write_artwork(identifier, Path(artwork).expanduser().read_bytes())

        updated = self._service.write_metadata(identifier, values) if values else None
        return updated or self._service.tracks.get(identifier)

    def read_artwork(self, track: Any) -> bytes | None:
        return self._service.read_artwork(_identifier(track))


class LyricsUiAdapter:
    """Translate Track objects and editor choices to the lyrics service API."""

    def __init__(self, lyrics_service, settings_service=None):
        self._service = lyrics_service
        self._settings = settings_service

    @property
    def default_storage(self) -> str:
        storage = self._settings.get("lyrics.storage", "sidecar") if self._settings else "sidecar"
        return storage if storage in {"sidecar", "embedded"} else "sidecar"

    def get_lyrics(self, track: Any) -> str:
        document = self._service.get_lyrics(_identifier(track))
        if isinstance(document, LyricsDocument):
            return document.to_lrc() if document.format == "lrc" else document.to_plain_text()
        if isinstance(document, str):
            return document
        return str(getattr(document, "text", "") or "")

    def save_lyrics(
        self,
        track: Any,
        content: str,
        *,
        mode: str = "plain",
        storage: str = "sidecar",
    ):
        if storage not in {"sidecar", "embedded"}:
            raise ValueError("storage must be 'sidecar' or 'embedded'")
        result = self._service.save_lyrics(_identifier(track), content, mode, storage)
        if self._settings is not None:
            self._settings.set("lyrics.storage", storage)
        return result


class PlaylistUiAdapter:
    """Keep Favorites special while exposing the operations the UI needs."""

    def __init__(self, playlist_service):
        self._service = playlist_service

    def __getattr__(self, name: str):
        return getattr(self._service, name)

    @staticmethod
    def _is_favorites(playlist: Any) -> bool:
        return bool(getattr(playlist, "is_favorite", False)) or str(
            getattr(playlist, "name", "")
        ).casefold() == "favorites"

    def list_favorites(self):
        favorites = next((p for p in self._service.list_playlists() if self._is_favorites(p)), None)
        return self._service.get_playlist_tracks(favorites.id) if favorites is not None else []

    def add_track(self, playlist_id: int, track_id_: int):
        playlist = next((p for p in self._service.list_playlists() if p.id == playlist_id), None)
        if playlist is not None and self._is_favorites(playlist):
            if not self._service.is_favorite(track_id_):
                self._service.toggle_favorite(track_id_)
            return True
        return self._service.add_track(playlist_id, track_id_)

    def remove_track(self, playlist_id: int, track_id_: int):
        playlist = next((p for p in self._service.list_playlists() if p.id == playlist_id), None)
        if playlist is not None and self._is_favorites(playlist):
            if self._service.is_favorite(track_id_):
                self._service.toggle_favorite(track_id_)
                return True
            return False
        return self._service.remove_track(playlist_id, track_id_)

    def move_track(self, playlist_id: int, track_id_: int, destination_index: int) -> None:
        tracks = self._service.get_playlist_tracks(playlist_id)
        source_index = next((i for i, track in enumerate(tracks) if track.id == track_id_), None)
        if source_index is None:
            raise KeyError(f"Track {track_id_} is not in playlist {playlist_id}")
        self._service.reorder_tracks(playlist_id, source_index, destination_index)


class PlaybackUiAdapter(QObject):
    """Expose the controller in the UI's seconds-based presentation units.

    The adapter owns no playback state. It forwards controller state and actions,
    converting only millisecond time values at the boundary.
    """

    current_track_changed = Signal(object)
    playback_state_changed = Signal(str)
    position_changed = Signal(float)
    duration_changed = Signal(float)
    volume_changed = Signal(float)
    muted_changed = Signal(bool)
    shuffle_changed = Signal(bool)
    repeat_mode_changed = Signal(str)
    queue_changed = Signal(object, object)
    error_occurred = Signal(str)

    def __init__(self, controller: PlaybackController, parent: QObject | None = None):
        super().__init__(parent)
        self.controller = controller
        controller.current_track_changed.connect(self.current_track_changed.emit)
        controller.playback_state_changed.connect(self.playback_state_changed.emit)
        controller.position_changed.connect(lambda value: self.position_changed.emit(value / 1000.0))
        controller.duration_changed.connect(lambda value: self.duration_changed.emit(value / 1000.0))
        controller.volume_changed.connect(self.volume_changed.emit)
        controller.muted_changed.connect(self.muted_changed.emit)
        controller.shuffle_changed.connect(self.shuffle_changed.emit)
        controller.repeat_mode_changed.connect(self.repeat_mode_changed.emit)
        controller.error_occurred.connect(self.error_occurred.emit)
        controller.queue_changed.connect(self._queue_updated)
        controller.current_queue_index_changed.connect(self._queue_updated)
        self._queue_signature = None
        self._queue_updated()

    def __getattr__(self, name: str):
        controller = self.__dict__.get("controller")
        if controller is None:
            raise AttributeError(name)
        return getattr(controller, name)

    @property
    def current_track(self):
        return self.controller.current_track

    @property
    def current_state(self) -> str:
        return self.controller.current_state

    @property
    def is_playing(self) -> bool:
        return self.controller.is_playing

    @property
    def is_paused(self) -> bool:
        return self.controller.is_paused

    @property
    def position(self) -> float:
        return self.controller.position / 1000.0

    @property
    def duration(self) -> float:
        return self.controller.duration / 1000.0

    @property
    def volume(self) -> float:
        return self.controller.volume

    @property
    def is_muted(self) -> bool:
        return self.controller.is_muted

    @property
    def shuffle(self) -> bool:
        return self.controller.shuffle_enabled

    @property
    def shuffle_enabled(self) -> bool:
        return self.controller.shuffle_enabled

    @property
    def repeat_mode(self) -> str:
        return self.controller.repeat_mode

    @property
    def queue(self):
        return self.controller.queue

    @property
    def current_queue_index(self):
        return self.controller.current_queue_index

    @property
    def current_index(self):
        return self.controller.current_queue_index

    def seek(self, position_seconds: float) -> None:
        self.controller.seek(round(float(position_seconds) * 1000))

    def _queue_updated(self, *_args) -> None:
        queue = self.controller.queue
        index = self.controller.current_queue_index
        signature = (tuple((str(_track_identity(track)), id(track)) for track in queue), index)
        if signature == self._queue_signature:
            return
        self._queue_signature = signature
        self.queue_changed.emit(queue, index)


class ServiceContainer:
    """Own the long-lived domain graph and its one playback controller."""

    def __init__(self, database_path=None, *, parent: QObject | None = None, audio_engine=None):
        self.domain = DomainServices(database_path)
        self.playback = PlaybackController(engine=audio_engine, parent=parent)
        self.library = self.domain.library
        self.playlists = PlaylistUiAdapter(self.domain.playlists)
        self.metadata = MetadataUiAdapter(self.domain.metadata)
        self.lyrics = LyricsUiAdapter(self.domain.lyrics, self.domain.settings)
        self.settings = self.domain.settings
        self.history = self.domain.history
        self.playback_ui = PlaybackUiAdapter(self.playback, parent)
        self.playback.current_track_changed.connect(self._record_play)
        self._closed = False

    def migrate_legacy_playlists(self, candidates=None):
        return self.domain.migrate_legacy_playlists(candidates)

    def register_saved_folders(self) -> list[str]:
        folders = self.settings.get("library.folders", []) or []
        registered: list[str] = []
        for folder in folders:
            path = Path(str(folder)).expanduser()
            if not path.is_dir():
                logger.info("Saved library folder is not available: %s", path)
                continue
            try:
                registered.append(self.library.add_library_folder(path))
            except (OSError, ValueError) as exc:
                logger.warning("Could not register library folder %s: %s", path, exc)
        return registered

    def _record_play(self, track) -> None:
        identifier = _track_identity(track)
        if isinstance(identifier, int) and not isinstance(identifier, bool):
            try:
                self.history.record_play(identifier)
            except Exception:
                logger.exception("Could not record playback history for track %s", identifier)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.playback.shutdown()
        finally:
            self.domain.close()
