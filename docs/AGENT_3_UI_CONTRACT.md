# Agent 3 — UI Architecture and Integration Contract

## Architecture

The presentation layer is a PySide6 package rooted at `ui/main_window.py`. `MainWindow` is created with injected services and owns navigation, page registration, controller signal connections, UI action routing, and user-facing errors. Page widgets do not open databases or access an audio backend.

Large track collections use `QTableView` with `TrackTableModel` and `TrackFilterProxyModel`; artwork is painted by a delegate. Album and artist browsing uses responsive artwork cards. Artwork reads run on `QThreadPool`, return `QImage` values to the GUI thread, and use a bounded 160-entry cache. Library, history, playlist-track, metadata, lyrics, scan, and storage reads/writes that can take longer run in worker tasks.

The shell uses Qt layouts: a scrollable left navigation rail, a `QStackedWidget` content area, an optional right queue panel, and a persistent playback bar. The default minimum window size is 1000 × 680. At widths below 1160 px the optional queue panel closes to preserve page width.

## Main window constructor

```python
MainWindow(
    *,
    library_service,
    playlist_service,
    metadata_service,
    lyrics_service,
    settings_service,
    history_service,
    playback_controller,
)
```

Import with `from ui.main_window import MainWindow`. Agent 4 should instantiate it after constructing the application services and set it as the application’s main window.

## Required service methods and data

All records may be mappings or plain objects. UI-facing track records should expose an identifier (`id`, `track_id`, or a stable path), title, artist, album, duration in seconds, and any available `date_added`, genre, year, album artist, track/disc number, composer, comment, and artwork fields. The canonical domain `Track` stores `duration_ms`; the integrated adapter converts it to seconds at the UI boundary.

| Injected object | Required methods used by the UI |
|---|---|
| `library_service` | `list_tracks()`, `list_albums()`, `list_artists()`, `scan_library(...)` |
| `playlist_service` | `list_playlists()`, `get_playlist_tracks(playlist_id)`, `create_playlist(name)`, `add_track(playlist_id, track_id)`, `remove_track(playlist_id, track_id)` |
| `metadata_service` | `read_metadata(track)`, `write_metadata(track, metadata_dict)`, `read_artwork(track)` |
| `lyrics_service` | `get_lyrics(track)`, `save_lyrics(track, text, ...)` |
| `settings_service` | `get(key, default=None)`, `set(key, value)` |
| `history_service` | `recently_played(limit=...)`, `recently_added(limit=...)` (zero-argument methods are also accepted) |
| `playback_controller` | See the playback contract below |

`metadata_service.read_artwork` may return a `QImage`, `QPixmap`, encoded image bytes, a local image path, or a mapping containing `image`, `data`, or `path`. It is read off the GUI thread. `read_metadata` should return a mapping. `write_metadata` receives ordinary editable metadata fields; `artwork_path` requests a replacement and `artwork: None` requests artwork removal. Return `False` or raise an exception on failure so the dialog can report it.

Lyrics may be returned as plain text, LRC text, or an object exposing `text`, `lyrics`, or `content`. The editor supports service methods accepting `mode="plain"|"lrc"`, `is_lrc=bool`, a positional mode boolean, or just `(track, text)`.

Optional playlist methods are `rename_playlist(playlist_id, new_name)`, `delete_playlist(playlist_id)`, and `move_track(playlist_id, track_id, new_index)`. Favorites are represented by a protected playlist named `Favorites`; `list_favorites()` may be supplied as a convenience. The UI never stores playlist membership locally.

Optional settings used by the page include `clear_artwork_cache()`, `export_data(path)`, and `reset()`. Corresponding buttons remain disabled when those service operations do not exist. Playback speed (`set_speed`) and crossfade (`set_crossfade`) controls appear only when supported.

## Playback controller contract

The UI calls only the injected controller. Required methods and conventions:

```text
play_track(track)
play_queue(tracks, start_index=0)   # also accepts (tracks, index)
toggle_play_pause()
next()
previous()
seek(position_seconds)
set_volume(0.0_to_1.0)
set_shuffle(enabled: bool)
set_repeat_mode("off" | "all" | "one")
add_to_queue(track)
play_next(track)
remove_from_queue(index)            # track/track_id also accepted by UI adapter
move_queue_item(from_index, to_index)
clear_queue()
```

For queue display, expose `get_queue()` or a `queue`/`current_queue` property and an active index as `current_index`, `queue_index`, `current_queue_index`, `song_index`, or `song_pointer`. The view displays snapshots from that API and submits remove/reorder requests back to the controller; it does not keep a second playback queue.

The window connects these optional Qt signals when present:

```text
track_changed(track) / current_track_changed(track)
playback_state_changed(state) / is_playing_changed(bool)
position_changed(position_seconds[, duration_seconds])
duration_changed(duration_seconds)
volume_changed(volume)
shuffle_changed(enabled)
repeat_mode_changed(mode)
queue_changed(queue[, current_index])
```

The UI reads artwork and metadata in worker tasks. Injected services must create thread-safe database sessions per call (or otherwise permit these reads from the worker pool). Playback-control methods are called from the GUI thread and should return promptly.

## Page and component map

- `ui/pages/home.py`: recently played, recently added, favorites, and first-library empty state.
- `ui/pages/songs.py`: searchable, sortable, multi-select library table.
- `ui/pages/collections.py`: album/artist grids and detail views, including album tracks and artist albums/tracks.
- `ui/pages/playlists.py`: playlist selection, create/rename/delete, add songs, add to queue, and optional reorder.
- `ui/pages/now_playing.py`: actual service artwork, track metadata, favorite/playlist actions, and lyrics access.
- `ui/pages/lyrics.py`: plain/LRC rendering, timestamp highlight, auto-scroll and manual-scroll pause.
- `ui/pages/settings.py`: persisted appearance, library, playback, lyrics, desktop, and supported storage settings.
- `ui/pages/search.py`: grouped songs/albums/artists/playlists results.
- `ui/player/playback_bar.py`: persistent transport, seek, repeat/shuffle, volume, queue, lyrics, and track actions.
- `ui/player/queue_panel.py`: current/upcoming queue snapshot, artwork, play/remove/reorder/clear/add actions.
- `ui/dialogs/editors.py`: asynchronous metadata and lyrics editors.
- `ui/components/`: navigation, buttons, artwork, empty states, cards, search, and track table.
- `ui/models/` and `ui/delegates/`: table model/filtering and asynchronous artwork painting.

## Theme and assets

`ui/theme/tokens.py` defines dark/light palettes, system resolution, colors, typography, weights, spacing, radii, shadows, and animation durations. The stored theme setting is `appearance.theme` with values `dark`, `light`, or `system`; accent and density use `appearance.accent` and `appearance.density`. Theme changes apply through the application window stylesheet. SVG path icons are rendered with QtSvg at runtime; there are no external icon-font dependencies. Inter is preferred with Segoe UI/system fallback.

PySide6 and QtSvg are declared in the integrated project dependencies. The application bootstrap injects a playback adapter that converts the audio controller millisecond values to the UI seconds-based contract.

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Play/pause | Space |
| Next / previous | Ctrl+Right / Ctrl+Left |
| Search | Ctrl+F |
| Add files | Ctrl+O |
| Queue | Ctrl+Q |
| Lyrics | Ctrl+L |
| Toggle favorite | Ctrl+D |
| Settings | Ctrl+, |

Shortcuts are scoped to the main window and ignored while a text editor, line edit, spin box, combo box, or dialog owns focus.

## Smoke checks

Run from the repository root in PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m compileall -q ui\theme ui\components ui\models ui\delegates ui\dialogs ui\pages ui\player ui\main_window.py tests\ui
python -m unittest discover -s tests\ui -v
```

Result for this branch: all UI modules compiled and **5 offscreen smoke tests passed** (page registration/service loading, table play and seek-drag behavior, navigation/search, queue and favorite routing, dialog construction). `git diff --check` also passed. No running app screenshot or visual inspection was performed.

## Manual visual acceptance checklist

- Open at 1920 × 1080, 1600 × 900, and 1366 × 768; confirm sidebar, content, and player bar never overlap.
- Check dark, light, and system themes; verify active navigation, table selection, menus, dialogs, and artwork placeholders remain readable.
- Load a library with long titles and many rows; verify sorting, filtering, elision, multi-selection, keyboard navigation, and artwork scrolling.
- Open albums, artists, playlists, favorites, and detail pages; exercise play, shuffle, queue, playlist create/rename/delete, add/remove, and reorder.
- Change tracks while playing and verify artwork/title updates, progress duration, slider drag behavior, repeat/shuffle, and volume.
- Try timestamped and plain lyrics; verify highlight, auto-scroll, manual-scroll pause, edits, cancel, and unsaved-change prompt.
- Open metadata editor; replace/remove artwork, save supported tags, and confirm service failures are understandable.
- Test every shortcut with a table focused and with a text field/dialog focused.

## Integrated state and known limits

The production bootstrap is in `app/bootstrap.py`. Its `ServiceContainer` adapts the canonical track-ID metadata and lyrics APIs to this UI's Track-object API, and adapts the playback controller's millisecond values to the UI's seconds values. Widgets continue to use injected services and do not open SQLite connections or access the audio backend.

System tray, notifications, media keys, export/reset, cache cleanup, playback speed, and crossfade are not implemented in this build. Their unsupported controls are disabled or omitted. The legacy PyQt6/Pygame implementation has been removed; `main.py` starts the PySide6 application.
