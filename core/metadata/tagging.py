"""Mutagen-backed metadata adapter with explicit dependency and format errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Track


class MetadataDependencyError(RuntimeError):
    """Mutagen must be installed to read or write common music tags."""


class MetadataReadError(RuntimeError):
    """A file could not be parsed as a supported audio file."""


class MetadataWriteError(RuntimeError):
    """A tag update was unsupported or could not be saved to the source file."""


def _mutagen_file(path: str | Path, *, easy: bool):
    try:
        from mutagen import File
    except ImportError as exc:
        raise MetadataDependencyError("Mutagen is required for audio metadata operations (install mutagen>=1.47).") from exc
    try:
        audio = File(str(path), easy=easy)
    except Exception as exc:
        raise MetadataReadError(f"Could not read audio metadata from {path}: {exc}") from exc
    if audio is None:
        raise MetadataReadError(f"Unsupported or corrupted audio file: {path}")
    return audio


def _first(tags: Any, *keys: str) -> str:
    if tags is None:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except (AttributeError, KeyError, TypeError):
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if value is not None:
            return str(value).strip()
    return ""


def _number(value: str) -> int | None:
    try:
        head = value.split("/", 1)[0].strip()
        number = int(head)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _year(value: str) -> int | None:
    for token in value.strip().split("T", 1)[0].split("-", 1)[:1]:
        try:
            year = int(token[:4])
            return year if year > 0 else None
        except ValueError:
            pass
    return None


def read_metadata(path: str | Path, *, track_id: int | None = None) -> Track:
    audio = _mutagen_file(path, easy=True)
    tags = audio.tags
    info = getattr(audio, "info", None)
    try:
        duration = round(float(getattr(info, "length", 0) or 0) * 1000)
    except (TypeError, ValueError):
        duration = 0
    try:
        bitrate = int(getattr(info, "bitrate", 0) or 0) or None
    except (TypeError, ValueError):
        bitrate = None
    try:
        sample_rate = int(getattr(info, "sample_rate", 0) or 0) or None
    except (TypeError, ValueError):
        sample_rate = None
    bpm_text = _first(tags, "bpm")
    try:
        bpm = float(bpm_text) if bpm_text else None
    except ValueError:
        bpm = None
    comment = _first(tags, "comment", "description")
    if not comment and (hasattr(tags, "getall") or "easyid3" in type(tags).__module__.casefold()):
        try:
            raw = _mutagen_file(path, easy=False)
            frames = raw.tags.getall("COMM") if raw.tags is not None and hasattr(raw.tags, "getall") else []
            frame = next((frame for frame in frames if not getattr(frame, "desc", "")), frames[0] if frames else None)
            if frame is not None:
                comment = str(frame.text[0] if isinstance(frame.text, list) and frame.text else frame.text)
        except MetadataReadError:
            pass
    return Track(
        id=track_id,
        path=str(path),
        title=_first(tags, "title"),
        artist=_first(tags, "artist"),
        album=_first(tags, "album"),
        album_artist=_first(tags, "albumartist", "album artist"),
        duration_ms=max(0, duration),
        track_number=_number(_first(tags, "tracknumber", "track")),
        disc_number=_number(_first(tags, "discnumber", "disc")),
        year=_year(_first(tags, "date", "year", "originaldate")),
        genre=_first(tags, "genre"),
        composer=_first(tags, "composer"),
        comment=comment,
        bitrate=bitrate,
        sample_rate=sample_rate,
        bpm=bpm,
    )


WRITE_KEYS = {
    "title": "title", "artist": "artist", "album": "album", "album_artist": "albumartist",
    "track_number": "tracknumber", "disc_number": "discnumber", "year": "date",
    "genre": "genre", "composer": "composer", "comment": "comment", "bpm": "bpm",
}


def write_metadata(path: str | Path, changes: dict[str, Any]) -> None:
    unsupported_fields = set(changes) - set(WRITE_KEYS)
    if unsupported_fields:
        raise MetadataWriteError(f"These fields cannot be written as tags: {', '.join(sorted(unsupported_fields))}")
    audio = _mutagen_file(path, easy=False)
    if audio.tags is None:
        add_tags = getattr(audio, "add_tags", None)
        if add_tags is None:
            raise MetadataWriteError(f"This file format does not support metadata tags: {path}")
        try:
            add_tags()
        except Exception as exc:
            raise MetadataWriteError(f"Could not create tags in {path}: {exc}") from exc
    tags = audio.tags
    prepared: list[tuple[str, str, list[str]]] = []
    for field, value in changes.items():
        key = WRITE_KEYS[field]
        if value is None or value == "":
            prepared.append((field, key, []))
            continue
        if field in {"track_number", "disc_number", "year"}:
            try:
                converted = str(int(value))
                if int(converted) <= 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise MetadataWriteError(f"{field} must be a positive integer") from exc
        elif field == "bpm":
            try:
                converted = str(float(value))
                if float(converted) < 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise MetadataWriteError("bpm must be a non-negative number") from exc
        else:
            converted = str(value)
        prepared.append((field, key, [converted] if converted else []))

    # ID3 has native frames for every shared field, including comments; update only the
    # matching text frames and leave artwork, lyrics, and unrelated frames untouched.
    if hasattr(tags, "getall"):
        _write_id3_metadata(tags, prepared)
        try:
            audio.save()
            return
        except Exception as exc:
            raise MetadataWriteError(f"Could not write metadata to {path}: {exc}") from exc

    # MP4 uses four-character native keys and compound track/disc fields.
    if type(audio).__module__.startswith("mutagen.mp4"):
        _write_mp4_metadata(tags, prepared)
        try:
            audio.save()
            return
        except Exception as exc:
            raise MetadataWriteError(f"Could not write metadata to {path}: {exc}") from exc

    # Easy tags are the common abstraction for FLAC, Vorbis, Opus, WAV, AIFF, APE, ASF,
    # and Musepack. They modify only requested keys while Mutagen preserves other tags.
    audio = _mutagen_file(path, easy=True)
    if audio.tags is None:
        add_tags = getattr(audio, "add_tags", None)
        if add_tags is None:
            raise MetadataWriteError(f"This file format does not support metadata tags: {path}")
        add_tags()
    tags = audio.tags
    # Mutagen easy tags route supported fields to the format's native tags and retain other frames.
    try:
        for field, key, values in prepared:
            if values:
                tags[key] = values
            else:
                try:
                    del tags[key]
                except KeyError:
                    # Probe support before treating a no-op deletion as a successful edit.
                    try:
                        tags[key] = ["__music_player_tag_probe__"]
                        del tags[key]
                    except Exception as exc:
                        raise MetadataWriteError(f"The {field} tag is not supported by this file format") from exc
        audio.save()
    except MetadataWriteError:
        raise
    except Exception as exc:
        raise MetadataWriteError(f"Could not write metadata to {path}: {exc}") from exc


def _write_id3_metadata(tags: Any, prepared: list[tuple[str, str, list[str]]]) -> None:
    try:
        from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TRCK, TPOS, TDRC, TCON, TCOM, COMM, TBPM
    except ImportError as exc:
        raise MetadataDependencyError("Mutagen is required to write ID3 tags") from exc
    frame_by_field = {
        "title": ("TIT2", TIT2), "artist": ("TPE1", TPE1), "album": ("TALB", TALB),
        "album_artist": ("TPE2", TPE2), "track_number": ("TRCK", TRCK), "disc_number": ("TPOS", TPOS),
        "year": ("TDRC", TDRC), "genre": ("TCON", TCON), "composer": ("TCOM", TCOM),
        "bpm": ("TBPM", TBPM),
    }
    for field, _, values in prepared:
        if field == "comment":
            old = tags.getall("COMM")
            tags.delall("COMM")
            for frame in old:
                if getattr(frame, "desc", ""):
                    tags.add(frame)
            if values:
                tags.add(COMM(encoding=3, lang="eng", desc="", text=values))
            continue
        frame_id, frame_type = frame_by_field[field]
        tags.delall(frame_id)
        if values:
            tags.add(frame_type(encoding=3, text=values))


def _write_mp4_metadata(tags: Any, prepared: list[tuple[str, str, list[str]]]) -> None:
    key_by_field = {
        "title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "album_artist": "aART",
        "year": "\xa9day", "genre": "\xa9gen", "composer": "\xa9wrt", "comment": "\xa9cmt",
        "track_number": "trkn", "disc_number": "disk", "bpm": "tmpo",
    }
    try:
        for field, _, values in prepared:
            key = key_by_field[field]
            if not values:
                tags.pop(key, None)
            elif field in {"track_number", "disc_number"}:
                old = tags.get(key, [(0, 0)])
                total = old[0][1] if old and isinstance(old[0], tuple) else 0
                tags[key] = [(int(values[0]), int(total))]
            elif field == "bpm":
                tags[key] = [int(float(values[0]))]
            else:
                tags[key] = values
    except Exception as exc:
        raise MetadataWriteError(f"MP4 does not support the requested tag update: {exc}") from exc


def embedded_artwork(path: str | Path) -> bytes | None:
    audio = _mutagen_file(path, easy=False)
    tags = audio.tags
    if tags is None:
        return None
    try:
        from mutagen.id3 import APIC
        if hasattr(tags, "getall"):
            frames = tags.getall("APIC")
            if frames:
                return bytes(frames[0].data)
    except (ImportError, AttributeError, TypeError):
        pass
    try:
        pictures = getattr(audio, "pictures", None) or getattr(tags, "pictures", None)
        if pictures:
            return bytes(pictures[0].data)
    except (AttributeError, TypeError):
        pass
    try:
        cover = tags.get("covr")
        if cover:
            return bytes(cover[0])
    except (AttributeError, KeyError, TypeError):
        pass
    try:
        from base64 import b64decode
        from mutagen.flac import Picture
        encoded = tags.get("metadata_block_picture")
        if encoded:
            return bytes(Picture(b64decode(encoded[0])).data)
    except (ImportError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return None


def write_artwork(path: str | Path, image_bytes: bytes | None) -> None:
    audio = _mutagen_file(path, easy=False)
    if audio.tags is None:
        add_tags = getattr(audio, "add_tags", None)
        if add_tags is None:
            raise MetadataWriteError(f"This file format does not support embedded artwork: {path}")
        try:
            add_tags()
        except Exception as exc:
            raise MetadataWriteError(f"Could not initialize tags in {path}: {exc}") from exc
    tags = audio.tags
    try:
        from mutagen.id3 import APIC
        if hasattr(tags, "getall"):
            tags.delall("APIC")
            if image_bytes is not None:
                tags.add(APIC(encoding=3, mime=_image_mime(image_bytes), type=3, desc="Cover", data=image_bytes))
        elif hasattr(audio, "clear_pictures") and hasattr(audio, "add_picture"):
            audio.clear_pictures()
            if image_bytes is not None:
                from mutagen.flac import Picture
                picture = Picture()
                picture.data = image_bytes
                picture.type = 3
                picture.mime = _image_mime(image_bytes)
                audio.add_picture(picture)
        elif type(audio).__module__.startswith("mutagen.mp4"):
            if image_bytes is None:
                tags.pop("covr", None)
            else:
                from mutagen.mp4 import MP4Cover
                mp4_bytes = image_bytes
                mime = _image_mime(mp4_bytes)
                if mime not in {"image/png", "image/jpeg"}:
                    from PIL import Image
                    import io
                    with Image.open(io.BytesIO(mp4_bytes)) as image:
                        output = io.BytesIO()
                        image.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
                        mp4_bytes = output.getvalue()
                    mime = "image/jpeg"
                image_format = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
                tags["covr"] = [MP4Cover(mp4_bytes, imageformat=image_format)]
        elif tags is not None and type(audio).__module__.startswith(("mutagen.ogg", "mutagen.flac")):
            from base64 import b64encode
            from mutagen.flac import Picture
            if image_bytes is None:
                tags.pop("metadata_block_picture", None)
            else:
                picture = Picture()
                picture.data = image_bytes
                picture.type = 3
                picture.mime = _image_mime(image_bytes)
                tags["metadata_block_picture"] = [b64encode(picture.write()).decode("ascii")]
        else:
            raise MetadataWriteError(f"This file format does not support embedded artwork: {path}")
        audio.save()
    except MetadataWriteError:
        raise
    except Exception as exc:
        raise MetadataWriteError(f"Could not write artwork to {path}: {exc}") from exc


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise MetadataWriteError("Artwork data must be a PNG, JPEG, GIF, or WebP image")


def read_embedded_lyrics(path: str | Path) -> str | None:
    audio = _mutagen_file(path, easy=False)
    tags = audio.tags
    if tags is None:
        return None
    try:
        from mutagen.id3 import USLT
        frames = tags.getall("USLT") if hasattr(tags, "getall") else []
        if frames:
            return str(frames[0].text)
    except (ImportError, AttributeError, TypeError):
        pass
    for key in ("©lyr", "lyrics", "LYRICS", "UNSYNCEDLYRICS"):
        try:
            value = tags.get(key)
            if value:
                return str(value[0] if isinstance(value, (list, tuple)) else value)
        except (AttributeError, KeyError, TypeError):
            continue
    return None


def write_embedded_lyrics(path: str | Path, content: str | None) -> None:
    audio = _mutagen_file(path, easy=False)
    if audio.tags is None:
        add_tags = getattr(audio, "add_tags", None)
        if add_tags is None:
            raise MetadataWriteError(f"This file format does not support embedded lyrics: {path}")
        add_tags()
    tags = audio.tags
    try:
        if hasattr(tags, "getall"):
            from mutagen.id3 import USLT
            tags.delall("USLT")
            if content is not None:
                tags.add(USLT(encoding=3, lang="eng", desc="", text=content))
        elif hasattr(tags, "get") and "©lyr" in tags or type(tags).__module__.startswith("mutagen.mp4"):
            if content is None:
                tags.pop("©lyr", None)
            else:
                tags["©lyr"] = [content]
        elif hasattr(tags, "__setitem__"):
            if content is None:
                for key in ("lyrics", "LYRICS", "UNSYNCEDLYRICS"):
                    try:
                        del tags[key]
                    except KeyError:
                        pass
            else:
                try:
                    tags["lyrics"] = [content]
                except Exception:
                    tags["LYRICS"] = [content]
        else:
            raise MetadataWriteError(f"This file format does not support embedded lyrics: {path}")
        audio.save()
    except MetadataWriteError:
        raise
    except Exception as exc:
        raise MetadataWriteError(f"Could not write embedded lyrics to {path}: {exc}") from exc
