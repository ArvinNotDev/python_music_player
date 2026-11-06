"""Validated, optimized on-disk artwork cache with a bounded in-memory LRU."""

from __future__ import annotations

import hashlib
import io
import os
import threading
from collections import OrderedDict
from pathlib import Path

from database.database_manager import app_data_dir


class ArtworkError(RuntimeError):
    """Artwork could not be decoded or cached safely."""


class ArtworkManager:
    EXTERNAL_NAMES = ("cover", "folder", "front", "album", "artwork")
    EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

    def __init__(self, cache_dir: str | Path | None = None, *, max_entries: int = 256,
                 memory_entries: int = 64, thumbnail_size: tuple[int, int] = (512, 512)):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else app_data_dir() / "artwork"
        self.max_entries = max(1, int(max_entries))
        self.memory_entries = max(1, int(memory_entries))
        self.thumbnail_size = thumbnail_size
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._track_keys: OrderedDict[int, str] = OrderedDict()
        self._track_source_signatures: dict[int, tuple[int, int] | None] = {}
        self._lock = threading.RLock()

    def _external(self, audio_path: Path) -> Path | None:
        try:
            files = {child.name.casefold(): child for child in audio_path.parent.iterdir() if child.is_file()}
        except OSError:
            return None
        for stem in self.EXTERNAL_NAMES:
            for ext in self.EXTENSIONS:
                candidate = files.get(f"{stem}{ext}".casefold())
                if candidate:
                    return candidate
        return None

    @staticmethod
    def _embedded(path: Path) -> bytes | None:
        from .tagging import MetadataDependencyError, embedded_artwork
        try:
            return embedded_artwork(path)
        except MetadataDependencyError:
            raise
        except Exception:
            return None

    @staticmethod
    def _audio_signature(audio_path: Path) -> tuple[int, int] | None:
        try:
            audio_stat = audio_path.stat()
            return audio_stat.st_size, audio_stat.st_mtime_ns
        except OSError:
            return None

    @staticmethod
    def _digest_key(track_id: int, audio_path: Path, content_digest: str) -> str:
        return hashlib.sha256(f"{track_id}|{audio_path.resolve(strict=False)}|{content_digest}".encode("utf-8")).hexdigest()

    def validate(self, image_bytes: bytes) -> bytes:
        """Validate and optimize image data in memory without creating a cache entry."""
        return self._thumbnail_bytes(image_bytes)

    def prepare(self, image_bytes: bytes, *, cache_key: str | None = None) -> tuple[bytes, Path]:
        data = self._thumbnail_bytes(image_bytes)
        key = cache_key or hashlib.sha256(bytes(image_bytes)).hexdigest()
        output_format = "PNG" if data.startswith(b"\x89PNG\r\n\x1a\n") else "JPEG"
        suffix = ".png" if output_format == "PNG" else ".jpg"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        destination = self.cache_dir / f"{key}{suffix}"
        temporary = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, destination)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ArtworkError(f"Could not save artwork cache: {exc}") from exc
        with self._lock:
            self._remember(key, data)
            self._prune()
        return data, destination

    def _thumbnail_bytes(self, image_bytes: bytes) -> bytes:
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise ArtworkError("Pillow is required to validate and optimize artwork images") from exc
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            raise ArtworkError("Artwork must be non-empty encoded image bytes")
        if len(image_bytes) > 50 * 1024 * 1024:
            raise ArtworkError("Artwork exceeds the 50 MiB safety limit")
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
                has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
                output_format = "PNG" if has_alpha else "JPEG"
                if has_alpha:
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")
                out = io.BytesIO()
                image.save(out, format=output_format, optimize=True, quality=88)
                data = out.getvalue()
        except Exception as exc:
            raise ArtworkError(f"Invalid or unreadable artwork image: {exc}") from exc
        return data

    def get_artwork_path(self, track_id: int, audio_path: str | Path, *, force: bool = False) -> str | None:
        audio = Path(audio_path)
        external = self._external(audio)
        if external is not None:
            try:
                stat = external.stat()
                external_signature = f"{external.resolve(strict=False)}|{stat.st_size}|{stat.st_mtime_ns}"
            except OSError:
                external_signature = str(external)
            external_key = self._digest_key(track_id, audio, hashlib.sha256(external_signature.encode("utf-8")).hexdigest())
            with self._lock:
                cached = self._cache_path(external_key)
                if not force and cached is not None:
                    self._remember_track_key(track_id, external_key, None)
                    return str(cached)
            try:
                source_bytes = external.read_bytes()
            except OSError:
                source_bytes = None
            if source_bytes is not None:
                try:
                    _, path = self.prepare(source_bytes, cache_key=external_key)
                except ArtworkError:
                    pass
                else:
                    with self._lock:
                        self._remember_track_key(track_id, external_key, None)
                    return str(path)

        signature = self._audio_signature(audio)
        with self._lock:
            known_key = self._track_keys.get(track_id)
            if not force and self._track_source_signatures.get(track_id) == signature and known_key:
                cached = self._cache_path(known_key)
                if cached is not None:
                    self._track_keys.move_to_end(track_id)
                    return str(cached)
        source_bytes = self._embedded(audio)
        if source_bytes is None:
            self.invalidate(track_id)
            return None
        content_hash = hashlib.sha256(source_bytes).hexdigest()
        key = self._digest_key(track_id, audio, content_hash)
        with self._lock:
            cached = self._cache_path(key)
            if not force and cached is not None:
                self._remember_track_key(track_id, key, signature)
                return str(cached)
        try:
            _, path = self.prepare(source_bytes, cache_key=key)
        except ArtworkError:
            self.invalidate(track_id)
            return None
        with self._lock:
            self._remember_track_key(track_id, key, signature)
        return str(path)

    def read_artwork(self, track_id: int, audio_path: str | Path) -> bytes | None:
        path = self.get_artwork_path(track_id, audio_path)
        if path is None:
            return None
        with self._lock:
            key = self._track_keys.get(track_id)
            if key and key in self._memory:
                self._memory.move_to_end(key)
                return self._memory[key]
        try:
            data = Path(path).read_bytes()
        except OSError:
            return None
        if key:
            with self._lock:
                self._remember(key, data)
        return data

    def invalidate(self, track_id: int) -> None:
        with self._lock:
            key = self._track_keys.pop(track_id, None)
            self._track_source_signatures.pop(track_id, None)
            if key:
                self._memory.pop(key, None)

    def _cache_path(self, key: str) -> Path | None:
        for suffix in (".jpg", ".png"):
            candidate = self.cache_dir / f"{key}{suffix}"
            if candidate.is_file():
                try:
                    candidate.touch()
                except OSError:
                    pass
                return candidate
        return None

    def _remember(self, key: str, data: bytes) -> None:
        self._memory[key] = data
        self._memory.move_to_end(key)
        while len(self._memory) > self.memory_entries:
            self._memory.popitem(last=False)

    def _remember_track_key(self, track_id: int, key: str, signature: tuple[int, int] | None) -> None:
        self._track_keys[track_id] = key
        self._track_keys.move_to_end(track_id)
        self._track_source_signatures[track_id] = signature
        while len(self._track_keys) > self.max_entries:
            evicted_id, _ = self._track_keys.popitem(last=False)
            self._track_source_signatures.pop(evicted_id, None)

    def _prune(self) -> None:
        try:
            files = sorted((p for p in self.cache_dir.iterdir() if p.suffix in {".jpg", ".png"}), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        except OSError:
            return
        for candidate in files[self.max_entries:]:
            try:
                candidate.unlink()
            except OSError:
                pass
