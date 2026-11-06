# Sonora

Sonora is a local desktop music player for organizing and playing a personal music library. It uses a persistent SQLite catalog, a PySide6 interface, and Qt Multimedia playback. Music stays in its existing folders; Sonora stores library records, playlists, history, settings, and cached artwork in the user's application-data directory.

## Features

- Scan and browse local music folders with song, album, artist, recently played, and recently added views.
- Search songs, albums, artists, and playlists; browse album and artist collections.
- Play, pause, resume, stop, seek, change volume, and mute through one playback controller.
- Build a queue, add tracks to Play Next, remove or reorder upcoming tracks, and use shuffle and repeat off/all/one.
- Create, rename, delete, reorder, and persist playlists. Favorites is a built-in collection.
- Read and edit supported audio tags, replace or remove embedded artwork, and display artwork from embedded tags or nearby cover files.
- Read plain-text or timestamped LRC lyrics, follow timed lines during playback, and save lyrics as a sidecar file or embedded tag when the format supports it.
- Persist appearance, library, playback, and lyrics preferences.
- Launch a keyboard-first command palette with `Ctrl+K` for navigation and common playback/library actions.
- Set a one-shot sleep timer to pause playback automatically, with quick 15/30/45/60/90-minute presets.
- Enjoy subtle cover-art reveal transitions, refined collection-card hover elevation, and a lightweight animated playback activity cue; motion follows the appearance animation preference.
- Import legacy `playlists.json` data on startup. Successful imports are backed up, repeated launches do not import them again, and unresolved paths remain in playlists.

## Technology

- Python 3.10 or newer
- PySide6, including Qt Widgets, Qt Multimedia, and Qt SVG
- Mutagen for audio metadata, embedded artwork, and embedded lyrics
- Pillow for validating, resizing, and caching artwork
- SQLite for the library, playlists, settings, and playback history

The application uses one PySide6 binding and one `PlaybackController`. UI code uses injected services; repositories own SQLite access, and widgets do not control the multimedia backend directly.

## Audio and file support

The library scanner recognizes MP3, FLAC, WAV, OGG/OGA, Opus, Speex, M4A/M4B/M4P, MP4, AAC, AIFF/AIF, ASF/WMA, APE, Musepack, WavPack, True Audio, and TAK file extensions. Mutagen's tag support differs by container, so not every tag can be edited in every format.

Playback uses Qt Multimedia's `QMediaPlayer` and `QAudioOutput`. Decoding depends on the Qt/FFmpeg runtime and codecs available in the packaged build and on the target platform. A file that can be scanned or tagged is not necessarily playable. Gapless playback, crossfade, equalizer, ReplayGain, playback speed, and output-device selection are not currently provided.

Artwork replacement supports PNG, JPEG, GIF, and WebP image data. The editor displays supported fields for title, artist, album, album artist, track/disc number, year, genre, composer, and comment; file-format limitations can still prevent a particular write.

Lyrics can be saved as UTF-8 `.txt` or `.lrc` sidecars beside the audio file. Embedded lyric writes are available only when Mutagen and the audio container support them. The editor remembers the last selected storage method.

## Install and run

From the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

`requirements.txt` installs the project and runtime dependencies. To install developer and packaging tools too:

```powershell
python -m pip install -e ".[dev]"
```

On first launch, Sonora opens with an empty library. Add a music folder in **Settings → Library**, then choose **Rescan library**; the Home and Songs pages can also add selected audio files directly. Enable automatic scanning in Settings to scan registered folders on later launches. Sonora reads files in place and does not move or modify audio during scanning.

## Library and playlists

Library folders are stored in Settings and registered with the library database. Scans run in a background Qt worker and report progress and errors in the application. New and changed tracks appear after the scan completes. Missing files remain in the catalog with an unavailable status so playlist references are not silently dropped.

Playlist membership and order are stored in SQLite. Favorites uses the built-in Favorites collection. If an older `playlists.json` file is found, Sonora merges its playlists and paths into the database, makes a timestamped backup after a successful import, and records a migration marker. Malformed data is left untouched and reported in the log.

## Metadata, artwork, and lyrics

Open a track's context menu or track details to edit supported tags. Metadata is written to the audio file and the catalog is refreshed. Artwork can be embedded, removed, or read from supported nearby cover filenames. The display cache is bounded and is invalidated after artwork changes.

The lyrics page reads plain text and LRC timestamps. Timed lines follow playback position; manual scrolling pauses automatic following briefly. Use **Edit lyrics** to select plain text or LRC and a sidecar or embedded destination. Unsupported embedded writes show an error and leave the editor open.

## Quick actions and sleep timer

Press `Ctrl+K` to open the command palette. It searches navigation destinations and common actions such as playback controls, queue visibility, library scanning, playlist creation, and theme switching. The palette is designed for keyboard use: type to filter, use the arrow keys to move through results, press Enter to run an action, or Escape to close it.

Choose **Start Sleep Timer** from the command palette to pause playback after 1–240 minutes. Presets are provided for common durations. The sleep timer is a session-only timer and does not modify or clear the playback queue.

Artwork transitions and collection-card hover elevation are intentionally restrained. A compact animated activity cue indicates whether playback is active; it is a visual status indicator, not an audio-spectrum analyzer. The existing **Settings → Appearance → Motion** preference disables the added motion effects.

## Settings and user data

Settings currently cover theme, accent, density, animations, library folders and auto-scan, default volume, shuffle and repeat, and lyrics display/storage preferences. System tray, playback notifications, media keys, speed, crossfade, data export, reset, and artwork-cache cleanup are not available in this build; unsupported controls are disabled or omitted.

On Windows, the default application-data directory is:

```text
%APPDATA%\PythonMusicPlayer
```

It contains `library.sqlite3`, the artwork cache, and rotating application logs under `logs`. macOS uses `~/Library/Application Support/PythonMusicPlayer`. Linux uses `$XDG_DATA_HOME/PythonMusicPlayer` or `~/.local/share/PythonMusicPlayer` when `XDG_DATA_HOME` is unset. Automated tests pass a temporary database path and do not scan or modify a personal music library.

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Play / pause | Space |
| Next / previous | Ctrl + Right / Ctrl + Left |
| Search | Ctrl + F |
| Command palette | Ctrl + K |
| Add music | Ctrl + O |
| Toggle queue | Ctrl + Q |
| Lyrics | Ctrl + L |
| Toggle current favorite | Ctrl + D |
| Settings | Ctrl + , |

## Development and tests

Install development dependencies and run the headless test suite:

```powershell
python -m pip install -e ".[dev]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q app core database services ui tests
```

Tests cover database migrations and repositories, scanner behavior, metadata and lyrics, playlist persistence and migration, audio queue/controller behavior, Qt Multimedia initialization, UI construction, and application-level service adapters. Audio-device output and visual layout still need manual acceptance on a desktop.

## Windows packaging

With Python and the project dependencies installed on Windows, run:

```powershell
scripts\build_windows.ps1
```

The PyInstaller configuration builds an onedir application under `dist\Sonora`. PyInstaller's PySide6 hooks collect the Qt runtime and platform plugins; the spec includes Qt Multimedia and Qt SVG hidden imports. The resulting build must be checked on a clean Windows machine for codec availability, audio-device behavior, Qt/FFmpeg DLL deployment, and licensing notices before distribution. No signed installer or release is included in this repository.

Qt for Python and the multimedia runtime have their own license terms. Review the notices and redistribution requirements for the exact Qt and FFmpeg binaries included in a release, and check codec patent obligations for the distribution regions.

## Troubleshooting

- **A track is listed but will not play:** scanner/tag support is separate from decoder support. Check whether the target Qt Multimedia build includes a decoder for the file and review the playback error shown by Sonora.
- **No sound:** confirm that Windows has an available output device and that the system volume is not muted. Sonora uses the default output device and does not yet offer a device picker.
- **A tag edit fails:** tag write support depends on the audio container. The editor reports write errors; keep a backup of important source files before bulk external tag edits.
- **Lyrics cannot be embedded:** save as a sidecar file, or use a container that supports embedded lyrics through Mutagen.
- **A legacy playlist does not appear:** malformed JSON is intentionally left in place. Check the application log in the `logs` directory for the import error.
- **Qt platform plugin errors in a packaged build:** rebuild with the provided spec and verify the deployed Qt platform plugin folder and runtime DLLs are present beside the executable.

## Manual acceptance checklist

- Launch `python main.py`, add a folder containing supported audio files, and scan it.
- Browse songs, albums, artists, recent history, Favorites, and playlists; verify search and metadata edits update the displayed library.
- Play a track through a real output device. Verify pause/resume, seeking, volume, mute, next/previous, shuffle, repeat, queue removal, and Play Next.
- Replace artwork and confirm it refreshes in the track details, now-playing view, playback bar, and queue.
- Load plain and LRC lyrics, seek during playback, and save sidecar and supported embedded lyrics.
- Restart the application and verify playlists, Favorites, settings, and history persist.
- Test dark/light/system themes at common desktop window sizes and check that long titles, dialogs, and the queue remain usable.
- Test the packaged build on a clean Windows machine with the intended codecs and audio devices.
