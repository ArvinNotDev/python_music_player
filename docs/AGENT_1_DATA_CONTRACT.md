# Agent 1 Data, Library, and Metadata Contract

This document describes the data-domain implementation on `agent/01-data-library`.
The other application layers should use these objects and services instead of creating
parallel track models or writing directly to SQLite.

## Implemented modules

- `core/models/`: canonical `Track`, grouping entities, playlists, lyrics, and scan results.
- `core/library/`: folder registration, recursive scanner, asynchronous `LibraryService`.
- `core/metadata/`: Mutagen tagging adapter, metadata service, artwork cache, and lyrics service.
- `core/playlists/`: playlist, Favorites, and M3U/M3U8 service.
- `database/database_manager.py`: user-data path, short-lived SQLite connections, WAL, transactions.
- `database/migrations/`: ordered schema migrations.
- `database/repositories/`: track, folder, playlist, settings, and playback-history repositories.
- `services/`: settings/history wrappers, playlist import/export and legacy migration, and `DomainServices` composition root.
- `tests/`: isolated database, library, metadata, playlist, lyrics, import/export, and migration tests.

## Canonical models

`core.models.Track` is the only track representation. Its fields are:

| Field | Type | Notes |
|---|---|---|
| `id` | `int | None` | SQLite integer ID; `None` before insertion. |
| `path` | `str` | Absolute, normalized local file path. |
| `title`, `artist`, `album`, `album_artist` | `str` | Empty string when metadata is absent. |
| `duration_ms` | `int` | Non-negative milliseconds. |
| `track_number`, `disc_number`, `year` | `int | None` | Positive when provided. |
| `genre`, `composer`, `comment` | `str` | Empty string when absent. |
| `bitrate`, `sample_rate` | `int | None` | Positive values when available. |
| `artwork_path` | `str | None` | Path to optimized cached artwork. |
| `date_added` | `datetime` | UTC-aware; defaults to the current UTC time. |
| `last_played` | `datetime | None` | UTC-aware when available. |
| `play_count` | `int` | Non-negative. |
| `is_available` | `bool` | False after a completed scan no longer finds the file. |
| `bpm` | `float | None` | Extra supported tag field. |

Other models are `Album(id, title, album_artist, year, track_count, duration_ms,
artwork_path)`, `Artist(id, name, album_count, track_count, artwork_path)`,
`Playlist(id, name, is_favorite, track_count, created_at, updated_at)`,
`LyricsLine(text, timestamp_ms)`, `LyricsDocument(lines, format, language, metadata)`,
and `ScanResult(scanned, added, updated, unchanged, missing, errors, canceled, total)`.
Models are dataclasses from `core.models`.

## Service APIs

### LibraryService

```python
list_tracks(query="", sort_by="title", descending=False, filters=None) -> list[Track]
list_albums(query="") -> list[Album]
list_artists(query="") -> list[Artist]
get_track(track_id) -> Track | None
add_library_folder(path) -> str
remove_library_folder(path) -> bool
list_library_folders() -> list[str]
scan_library(paths=None) -> QThread
cancel_scan() -> bool
```

`scan_library` starts a background `QThread` and returns its worker. Connect to these
`LibraryService` signals (also emitted by its worker where applicable):

```text
scan_progress(int current, int total, str path)
scan_completed(object ScanResult)
scan_error(str message)
library_changed(str event, object payload)
```

`library_changed` events currently include `folder_added`, `folder_removed`,
`scan_completed`, and `track_changed`. Metadata edits publish `track_changed` when the
service was created through `DomainServices`.

Recognized scan extensions cover MP3, FLAC, WAV, OGG/OGA, OPUS, Speex, M4A/M4B/M4P,
MP4, AAC, AIFF/AIF, ASF/WMA, APE, Musepack, WavPack, True Audio, and TAK. Actual parsing
is delegated to Mutagen; an unsupported or corrupt file is reported in `ScanResult.errors`.
Unchanged files are skipped using stored size and nanosecond modification time.
`filters` accepts exact `artist`, `album`, and `genre` matches, `is_available`, and
`favorite`/`is_favorite` booleans.

### PlaylistService

```python
list_playlists() -> list[Playlist]
get_playlist_tracks(playlist_id) -> list[Track]
get_playlist_entries(playlist_id) -> list[dict[str, object]]
create_playlist(name) -> Playlist
rename_playlist(playlist_id, new_name) -> Playlist
delete_playlist(playlist_id) -> None
add_track(playlist_id, track_id) -> bool
remove_track(playlist_id, track_id) -> bool
reorder_tracks(playlist_id, source_index, destination_index) -> None
is_favorite(track_id) -> bool
toggle_favorite(track_id) -> bool
import_playlist(path, name=None) -> PlaylistImportResult
export_playlist(playlist_id, path) -> PlaylistExportResult
```

`get_playlist_tracks` returns indexed audio tracks. `get_playlist_entries` also returns
unresolved imported paths (`entry_track_id` is `None`), so missing M3U entries survive and
can be linked when the scanner later indexes the file. Import/export results list missing
paths and invalid source lines. Favorites is a protected built-in playlist, mirrored in the
`favorites` table. Duplicate source paths within a playlist are ignored.

### MetadataService

```python
read_metadata(track_id) -> Track
write_metadata(track_id, changes: Mapping[str, Any]) -> Track
read_artwork(track_id) -> bytes | None
write_artwork(track_id, image_bytes: bytes | None) -> str | None
```

Writable metadata keys: `title`, `artist`, `album`, `album_artist`, `track_number`,
`disc_number`, `year`, `genre`, `composer`, `comment`, and `bpm`. Technical fields are
read-only. A successful tag edit is saved to the audio file, then the SQLite cache is
refreshed. Unsupported tag keys/formats raise `MetadataWriteError`. Unrelated ID3 frames,
including artwork and lyrics, are preserved; the ID3 preservation path is covered by tests.

`write_artwork` accepts the original encoded PNG, JPEG, GIF, or WebP bytes. `read_artwork`
returns optimized thumbnail bytes (maximum 512 x 512 by default), not the original image.
The cache is kept outside ordinary track rows and bounded by an on-disk LRU-style prune and
a bounded in-memory LRU.

### LyricsService

```python
get_lyrics(track_id) -> LyricsDocument
save_lyrics(track_id, content, format, storage) -> LyricsSaveResult
```

`format` is `plain` or `lrc`; `storage` is `embedded` or `sidecar`. Sidecars use UTF-8 and
the sibling `.txt` or `.lrc` path. When both exist, the most recently modified one is read.
Embedded saves raise `LyricsError` when the selected audio format cannot store lyrics;
`LyricsSaveResult.embedded` is true only after an embedded write succeeds. LRC timestamps
are represented as millisecond `LyricsLine.timestamp_ms` values. Malformed timestamp lines
are retained as untimed text.

### SettingsService and HistoryService

```python
SettingsService.get(key, default=None) -> Any
SettingsService.set(key, value) -> None
SettingsService.all() -> dict[str, Any]

HistoryService.record_play(track_id) -> None
HistoryService.recently_played(limit=20) -> list[Track]
HistoryService.recently_added(limit=20) -> list[Track]
```

Settings values are JSON-serialized inside SQLite. `record_play` is a meaningful play event
and updates history, play count, and last-played time in one transaction; position updates
are not recorded by this layer.

## SQLite schema and lifecycle

`DatabaseManager()` places `library.sqlite3` in the OS per-user application-data directory
(`%APPDATA%/PythonMusicPlayer`, macOS Application Support, or `$XDG_DATA_HOME` / `.local/share`).
It never chooses a path from the current working directory. Pass an explicit path for tests
or portable integration.

Migrations are forward-only and tracked with `PRAGMA user_version`:

1. Artists, albums, tracks, their foreign keys, field checks, and common query indexes.
2. Scanner file signatures, library folders, playlists/ordered entries, Favorites, playback
   history, settings, and their indexes.

Connections are opened per operation, enable foreign keys and a busy timeout, and use WAL
with `synchronous=NORMAL` for file databases. `DatabaseManager.transaction(write=True)` uses
`BEGIN IMMEDIATE`; exceptions roll back. SQLite errors surface as `DatabaseError`.

## Legacy JSON migration

`DomainServices.migrate_legacy_playlists(candidates=None)` (or
`ImportExportService.migrate_legacy_playlists`) explicitly checks existing `playlists.json`
files in the current directory, executable directory, project package directory, home, and
common project subdirectories. Tests and the service never modify the legacy file in place.
Successful imports are backed up beside the original as `playlists.json.backup-<UTC time>`;
per-file settings markers prevent repeat migration. Malformed JSON is reported and left in
place. Missing tracks remain as unresolved playlist paths.

Call migration once during application startup after constructing `DomainServices`; the
existing `main.py` was intentionally left untouched for the integration agent.

## Dependencies and limitations

- Python 3.10 or newer.
- PySide6 is the single Qt binding used by the application and worker APIs.
- `mutagen>=1.47` is required for metadata, embedded artwork, and embedded lyrics.
- `Pillow>=9.1` is required for artwork validation, resizing, and thumbnail caching.
- The repository dependency file was not changed because this task explicitly excludes root
  dependency configuration. The integration agent should add Mutagen and Pillow there.
- Format-specific tagging varies by container. Automated audio-file round-trip coverage in
  this branch uses a generated synthetic MP3/ID3 fixture; other formats rely on Mutagen's
  reader/easy-tag adapters and should be exercised with real fixtures before claiming every
  individual tag mapping works on them.
- The scanner reads file extensions supported by the implemented Mutagen set; actual decoder
  playback support remains the audio engine's responsibility.
- M3U playlist positions and resolved/unresolved local file paths are preserved. Remote URLs
  are reported as invalid because queue/network playback is outside this data layer.

## Tests

From the repository root, with project dependencies installed:

```powershell
python -m pytest -q
python -m compileall -q core database services tests
```

Validation on November 6, 2026: **22 passed**. The environment did not include Mutagen in
the root interpreter, so `mutagen 1.48.1` was installed into a temporary directory for the
test run; no repository dependency files or user music files were changed. The test suite
uses temporary databases and generated audio fixtures and runs headlessly with Qt's offscreen
platform.
