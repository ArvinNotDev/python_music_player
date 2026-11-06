"""Dependency-injected PySide6 application shell and presentation wiring."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QGraphicsOpacityEffect, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from .components import IconButton, SearchBox, Sidebar
from .dialogs import LyricsEditorDialog, MetadataEditorDialog, PlaylistSelectDialog, TrackPickerDialog
from .pages import (
    CollectionDetailPage, EntityGridPage, HomePage, LyricsPage, NowPlayingPage,
    PlaylistsPage, SearchPage, SettingsPage, SongsPage,
)
from .player.playback_bar import PlaybackBar
from .player.queue_panel import QueuePanel
from .services import track_id, value
from .theme import PALETTES, resolve_theme, stylesheet


def _as_list(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    try:
        return list(result)
    except TypeError:
        return []


def _call_compatible(method: Callable, *, keyword: str | None = None, value: Any = None) -> Any:
    """Call service methods with their documented and common compatible shapes."""
    if keyword:
        try:
            return method(**{keyword: value})
        except TypeError:
            pass
    if value is not None:
        try:
            return method(value)
        except TypeError:
            pass
    return method()


class _CallSignals(QObject):
    done = Signal(object, object)


class _BackgroundCall(QRunnable):
    def __init__(self, method: Callable, args: tuple = (), kwargs: dict | None = None):
        super().__init__()
        self.method, self.args, self.kwargs = method, args, kwargs or {}
        self.signals = _CallSignals()

    def run(self):
        try:
            self.signals.done.emit(self.method(*self.args, **self.kwargs), None)
        except Exception as exc:
            self.signals.done.emit(None, exc)


class _LibraryLoadSignals(QObject):
    done = Signal(object)


class _LibraryLoadTask(QRunnable):
    def __init__(self, library, playlists, history):
        super().__init__()
        self.library, self.playlists, self.history = library, playlists, history
        self.signals = _LibraryLoadSignals()

    @staticmethod
    def _list(service, method_name, **kwargs):
        method = getattr(service, method_name, None) if service else None
        if not callable(method):
            return [], None
        try:
            try:
                result = method(**kwargs)
            except TypeError:
                result = method()
            return _as_list(result), None
        except Exception as exc:
            return [], exc

    def run(self):
        tracks, track_error = self._list(self.library, "list_tracks")
        albums, album_error = self._list(self.library, "list_albums")
        artists, artist_error = self._list(self.library, "list_artists")
        playlists, playlist_error = self._list(self.playlists, "list_playlists")
        recent, recent_error = self._list(self.history, "recently_played", limit=30)
        added, added_error = self._list(self.history, "recently_added", limit=30)
        favorites, favorite_error = self._list(self.playlists, "list_favorites")
        errors = [str(err) for err in (track_error, album_error, artist_error, playlist_error, recent_error, added_error, favorite_error) if err]
        if not favorites:
            fav_playlist = next((p for p in playlists if str(value(p, "name", "title", default=p)).casefold() == "favorites"), None)
            getter = getattr(self.playlists, "get_playlist_tracks", None) if self.playlists else None
            if fav_playlist is not None and callable(getter):
                try:
                    favorites = _as_list(getter(value(fav_playlist, "id", "playlist_id", "name", default=fav_playlist)))
                except Exception as exc:
                    errors.append(str(exc))
        by_id = {str(track_id(track)): track for track in tracks}
        favorites = [by_id.get(str(track_id(item)), item) for item in favorites]
        recent = [value(item, "track", default=item) for item in recent]
        added = [value(item, "track", default=item) for item in added]
        self.signals.done.emit({"tracks": tracks, "albums": albums, "artists": artists, "playlists": playlists, "favorites": favorites, "recent": recent, "added": added, "errors": errors})


class MainWindow(QMainWindow):
    """Premium music-player UI. Services are injected and remain the source of truth."""

    def __init__(
        self,
        *,
        library_service,
        playlist_service,
        metadata_service,
        lyrics_service,
        settings_service,
        history_service,
        playback_controller,
    ):
        super().__init__()
        self.library_service = library_service
        self.playlist_service = playlist_service
        self.metadata_service = metadata_service
        self.lyrics_service = lyrics_service
        self.settings_service = settings_service
        self.history_service = history_service
        self.playback_controller = playback_controller
        self._tracks: list[Any] = []
        self._albums: list[Any] = []
        self._artists: list[Any] = []
        self._playlists: list[Any] = []
        self._favorites: list[Any] = []
        self._recent: list[Any] = []
        self._added: list[Any] = []
        self._current_track = None
        self._active_page = "home"
        self._return_page = "home"
        self._playlist_page_open = False
        self._queue_visible = False
        self._page_animation = None
        self._animated_page = None
        self._last_query = ""
        self._art_accent = "#8B7CFF"
        self._thread_pool = QThreadPool.globalInstance()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(lambda: self._run_search(self._last_query))

        self.setWindowTitle("Sonora — Music Player")
        self.setMinimumSize(1000, 680)
        self.resize(1440, 900)
        self.setStatusBar(QStatusBar(self))
        self._build_shell()
        self._build_pages()
        self._wire_actions()
        self._connect_controller_signals()
        self._load_initial_preferences()
        self.home_page.set_loading(True)
        self._load_library_async()
        self._sync_controller_state()
        self._install_shortcuts()

    def _build_shell(self):
        self.shell = QWidget()
        root = QVBoxLayout(self.shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        workspace = QWidget()
        row = QHBoxLayout(workspace)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar()
        row.addWidget(self.sidebar)
        self.main_region = QWidget()
        main_col = QVBoxLayout(self.main_region)
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(24, 14, 24, 12)
        top_layout.setSpacing(14)
        self.page_heading = QLabel("Home")
        self.page_heading.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.global_search = SearchBox("Search songs, albums, artists, playlists")
        self.global_search.setMaximumWidth(480)
        self.global_search.setMinimumWidth(250)
        top_layout.addWidget(self.page_heading)
        top_layout.addStretch(1)
        top_layout.addWidget(self.global_search)
        self.queue_button = IconButton("queue", "Show queue")
        self.queue_button.setCheckable(True)
        top_layout.addWidget(self.queue_button)
        main_col.addWidget(top)
        self.page_stack = QStackedWidget()
        main_col.addWidget(self.page_stack, 1)
        row.addWidget(self.main_region, 1)
        self.queue_panel = QueuePanel(self.metadata_service)
        self.queue_panel.setVisible(False)
        self.queue_panel.setMaximumWidth(420)
        self.queue_panel.setStyleSheet("border-left: 1px solid palette(mid);")
        row.addWidget(self.queue_panel)
        root.addWidget(workspace, 1)
        self.playback_bar = PlaybackBar(self.playback_controller, self.metadata_service)
        root.addWidget(self.playback_bar)
        self.setCentralWidget(self.shell)

    def _build_pages(self):
        self.pages: dict[str, QWidget] = {}
        self.home_page = HomePage(self.metadata_service)
        self.songs_page = SongsPage([], self.metadata_service)
        self.albums_page = EntityGridPage("album", self.metadata_service)
        self.artists_page = EntityGridPage("artist", self.metadata_service)
        self.recent_page = SongsPage([], self.metadata_service)
        self.recent_page.header.findChild(QLabel).setText("Recently played")
        self.favorites_page = SongsPage([], self.metadata_service)
        self.favorites_page.header.findChild(QLabel).setText("Favorites")
        self.playlists_page = PlaylistsPage(self.metadata_service)
        self.playlists_page.set_reorder_supported(callable(getattr(self.playlist_service, "move_track", None)))
        self.now_playing_page = NowPlayingPage(self.metadata_service)
        self.lyrics_page = LyricsPage(bool(self._get_setting("lyrics.auto_scroll", True)))
        self.settings_page = SettingsPage(self.settings_service, self.library_service, self.playback_controller)
        self.detail_page = CollectionDetailPage(self.metadata_service)
        self.search_page = SearchPage(self.metadata_service)
        for key, page in (
            ("home", self.home_page), ("now_playing", self.now_playing_page),
            ("songs", self.songs_page), ("albums", self.albums_page),
            ("artists", self.artists_page), ("recently_played", self.recent_page),
            ("favorites", self.favorites_page), ("playlists", self.playlists_page),
            ("lyrics", self.lyrics_page), ("settings", self.settings_page),
            ("entity_detail", self.detail_page), ("search", self.search_page),
        ):
            self.pages[key] = page
            self.page_stack.addWidget(page)
        self.favorites_page.table.allow_remove = True
        self.playlists_page.table.allow_remove = True
        self._connect_table(self.songs_page.table)
        self._connect_table(self.recent_page.table)
        self._connect_table(self.favorites_page.table)
        self._connect_table(self.playlists_page.table)
        self._connect_table(self.detail_page.table)
        self._connect_table(self.search_page.tracks)

    def _connect_table(self, table):
        # Context actions are wired once per reusable track table.
        table.playNextRequested.connect(self._play_next)
        table.queueRequested.connect(self._add_to_queue)
        table.favoriteRequested.connect(self._add_favorite)
        table.playlistRequested.connect(self._prompt_add_to_playlist)
        table.metadataRequested.connect(self._edit_metadata)
        table.removeRequested.connect(lambda track, source=table: self._remove_from_collection(source, track))
        table.activated.connect(lambda track, source=table: self._play_from_table(source, track))

    def _wire_actions(self):
        self.sidebar.navigate.connect(self.navigate)
        self.sidebar.playlistSelected.connect(self._open_playlist)
        self.sidebar.createPlaylist.connect(self._create_playlist)
        self.global_search.textChanged.connect(self._search_text_changed)
        self.global_search.returnPressed.connect(lambda: self.navigate("search"))
        self.queue_button.clicked.connect(self._toggle_queue)

        self.home_page.playRequested.connect(self._play_track)
        self.home_page.navigateRequested.connect(self._home_navigate)
        self.home_page.addFilesRequested.connect(self._add_files_dialog)
        self.songs_page.addFilesRequested.connect(self._add_files_dialog)
        self.albums_page.itemActivated.connect(lambda item: self._open_entity(item, "album"))
        self.artists_page.itemActivated.connect(lambda item: self._open_entity(item, "artist"))
        self.playlists_page.createRequested.connect(self._create_playlist)
        self.playlists_page.playlistSelected.connect(self._load_playlist_tracks)
        self.playlists_page.renameRequested.connect(self._rename_playlist)
        self.playlists_page.deleteRequested.connect(self._delete_playlist)
        self.playlists_page.playAllRequested.connect(self._play_current_playlist)
        self.playlists_page.shuffleRequested.connect(self._shuffle_current_playlist)
        self.playlists_page.addSongsRequested.connect(self._add_songs_to_current_playlist)
        self.playlists_page.queueRequested.connect(self._queue_current_playlist)
        self.playlists_page.moveTrackRequested.connect(self._move_playlist_track)
        self.detail_page.backRequested.connect(self._go_back_from_detail)
        self.detail_page.playAllRequested.connect(self._play_detail_tracks)
        self.detail_page.shuffleRequested.connect(self._shuffle_detail_tracks)
        self.detail_page.relatedAlbumActivated.connect(lambda item: self._open_entity(item, "album"))
        self.now_playing_page.favoriteRequested.connect(self._toggle_favorite)
        self.now_playing_page.playlistRequested.connect(self._prompt_add_to_playlist)
        self.now_playing_page.moreRequested.connect(self._show_track_menu)
        self.now_playing_page.lyricsRequested.connect(lambda: self.navigate("lyrics"))
        self.lyrics_page.editRequested.connect(self._edit_lyrics)
        self.lyrics_page.autoScrollChanged.connect(lambda enabled: self._set_setting("lyrics.auto_scroll", enabled))
        self.settings_page.themeChanged.connect(lambda _theme: self._apply_theme())
        self.settings_page.appearanceChanged.connect(self._apply_theme)
        self.settings_page.lyricsDisplayChanged.connect(self.lyrics_page.set_large_text)
        self.settings_page.statusChanged.connect(self._status)
        self.lyrics_page.set_large_text(bool(self._get_setting("lyrics.large_text", False)))
        self.search_page.albumActivated.connect(lambda item: self._open_entity(item, "album"))
        self.search_page.artistActivated.connect(lambda item: self._open_entity(item, "artist"))
        self.search_page.playlistActivated.connect(self._open_playlist)

        self.playback_bar.queueRequested.connect(self._toggle_queue)
        self.playback_bar.lyricsRequested.connect(lambda: self.navigate("lyrics"))
        self.playback_bar.favoriteRequested.connect(self._toggle_favorite)
        self.playback_bar.playlistRequested.connect(self._prompt_add_to_playlist)
        self.playback_bar.metadataRequested.connect(self._edit_metadata)
        self.playback_bar.moreRequested.connect(self._show_track_menu)
        self.playback_bar.errorOccurred.connect(self._status)
        self.playback_bar.positionUpdated.connect(self.lyrics_page.set_position)

        self.queue_panel.removeRequested.connect(self._remove_queue_item)
        self.queue_panel.moveRequested.connect(self._move_queue_item)
        self.queue_panel.playRequested.connect(self._play_queue_index)
        self.queue_panel.clearRequested.connect(self._clear_queue)
        self.queue_panel.addMoreRequested.connect(self._queue_add_more)

    def _load_initial_preferences(self):
        self._apply_theme()
        volume = self._get_setting("playback.default_volume", None)
        if volume is not None:
            self.playback_bar.set_volume(float(volume))
            if callable(getattr(self.playback_controller, "set_volume", None)):
                self._controller_call("set_volume", float(volume))
        shuffle = bool(self._get_setting("playback.shuffle", False))
        if shuffle and callable(getattr(self.playback_controller, "set_shuffle", None)):
            self._controller_call("set_shuffle", True)
        repeat = self._get_setting("playback.repeat", "off")
        repeat_mode = {0: "off", 1: "all", 2: "one"}.get(repeat, repeat)
        if repeat_mode not in (None, "off", 0) and callable(getattr(self.playback_controller, "set_repeat_mode", None)):
            self._controller_call("set_repeat_mode", repeat_mode)
        app = QApplication.instance()
        if app:
            try:
                app.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme() if self._get_setting("appearance.theme", "dark") == "system" else None)
            except (AttributeError, TypeError):
                pass

    def _get_setting(self, key: str, default=None):
        try:
            return self.settings_service.get(key, default) if self.settings_service else default
        except Exception:
            return default

    def _set_setting(self, key: str, value_: Any):
        try:
            if self.settings_service and callable(getattr(self.settings_service, "set", None)):
                self.settings_service.set(key, value_)
        except Exception as exc:
            self._status(f"Couldn't save setting: {exc}")

    def _apply_theme(self):
        theme = str(self._get_setting("appearance.theme", "dark"))
        density = str(self._get_setting("appearance.density", "comfortable"))
        accent = str(self._get_setting("appearance.accent", "#8B7CFF"))
        self._art_accent = accent
        self.setStyleSheet(stylesheet(theme, density, accent))
        resolved = resolve_theme(theme)
        color = PALETTES[resolved].text
        from .components.icons import icon
        for button in self.findChildren(IconButton):
            active_color = "#FFFFFF" if button is self.playback_bar.play_button else accent if button.isChecked() else color
            button.setIcon(icon(button.icon_name, active_color))
        from .components.sidebar import NavigationButton
        for button in self.sidebar.findChildren(NavigationButton):
            button.setIcon(icon(button.icon_name, color))
        self.playback_bar.set_theme_colors(color, accent)

    def _load_library_async(self):
        task = _LibraryLoadTask(self.library_service, self.playlist_service, self.history_service)
        task.signals.done.connect(self._library_loaded)
        self._thread_pool.start(task)

    def _library_loaded(self, snapshot: dict[str, Any]):
        self.home_page.set_loading(False)
        previous_track = self._current_track
        self._tracks = snapshot["tracks"]
        self._albums = snapshot["albums"]
        self._artists = snapshot["artists"]
        self._playlists = snapshot["playlists"]
        self._favorites = snapshot["favorites"]
        self._recent = snapshot["recent"]
        self._added = snapshot["added"]
        if previous_track is not None:
            refreshed = next((track for track in self._tracks if track_id(track) == track_id(previous_track)), None)
            if refreshed is not None:
                signature = lambda track: tuple(str(value(track, key, default="")) for key in ("title", "artist", "album", "year", "genre"))
                if signature(refreshed) != signature(previous_track):
                    self._set_current_track(refreshed, force=True)
                else:
                    self._current_track = refreshed
        self.songs_page.set_tracks(self._tracks)
        self.recent_page.set_tracks(self._recent)
        self.favorites_page.set_tracks(self._favorites)
        self.albums_page.set_items(self._albums)
        self.artists_page.set_items(self._artists)
        self.sidebar.set_playlists(self._playlists)
        self.playlists_page.set_playlists(self._playlists)
        self.home_page.set_data(self._recent, self._added, self._favorites, self._tracks)
        self._update_current_favorite()
        self.search_page.set_data(self._tracks, self._albums, self._artists, self._playlists)
        self._refresh_queue()
        if snapshot["errors"]:
            self._status("Some library sections couldn't load. Check the connected services.")
        else:
            self._status(f"Library ready · {len(self._tracks)} songs")
        selected = self.playlists_page.current_playlist()
        if selected:
            self._load_playlist_tracks(selected)

    def navigate(self, destination: str):
        if destination == "search" and self._active_page != "search":
            self._return_page = self._active_page
        if destination == "now_playing":
            self.now_playing_page.set_track(self._current_track)
        if destination == "lyrics":
            self._load_lyrics(self._current_track)
        self._navigate(destination)

    def _navigate(self, destination: str):
        if destination not in self.pages:
            return
        self._active_page = destination
        self.page_heading.setText({"entity_detail": "Collection", "recently_played": "Recently played", "search": "Search"}.get(destination, destination.replace("_", " ").title()))
        target = self.pages[destination]
        previous = self.page_stack.currentWidget()
        if self._page_animation:
            self._page_animation.stop()
        if self._animated_page is not None:
            self._animated_page.setGraphicsEffect(None)
            self._animated_page = None
        self.page_stack.setCurrentWidget(target)
        if previous is not target and bool(self._get_setting("appearance.animations", True)):
            effect = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(160)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(lambda page=target: page.setGraphicsEffect(None))
            self._page_animation = animation
            self._animated_page = target
            animation.start()
        self.sidebar.set_active(destination if destination in ("home", "now_playing", "songs", "albums", "artists", "recently_played", "playlists", "favorites", "settings") else "")
        if destination == "search" and self.global_search.input.text().strip():
            self.search_page.search(self.global_search.input.text())
        self._apply_theme()

    def _home_navigate(self, section: str):
        self.navigate({"recent": "recently_played", "added": "songs", "favorites": "favorites"}.get(section, "home"))

    def _search_text_changed(self, text: str):
        self._last_query = text
        if text.strip():
            self._search_timer.start()
        elif self._active_page == "search":
            self._search_timer.stop()
            self._navigate(self._return_page)

    def _run_search(self, query: str):
        if query != self._last_query or not query.strip():
            return
        self.search_page.search(query)
        self.navigate("search")

    def _open_entity(self, item: Any, kind: str):
        self._return_page = "albums" if kind == "album" else "artists"
        name = str(value(item, "title", "name", "album", "artist", default=""))
        if kind == "album":
            matches = [track for track in self._tracks if str(value(track, "album", default="")).casefold() == name.casefold()]
            related_albums = []
        else:
            matches = [track for track in self._tracks if name.casefold() in str(value(track, "artist", "artists", "album_artist", default="")).casefold()]
            related_albums = [album for album in self._albums if name.casefold() in str(value(album, "artist", "album_artist", default="")).casefold()]
        self.detail_page.set_item(item, matches, kind, self.metadata_service, related_albums)
        self._navigate("entity_detail")

    def _go_back_from_detail(self):
        self._navigate(self._return_page)

    def _play_track(self, track: Any):
        if not track:
            return
        method = getattr(self.playback_controller, "play_track", None)
        if not callable(method):
            self._status("The playback controller cannot play tracks.")
            return
        try:
            method(track)
            self._set_current_track(track)
            self.playback_bar.set_playback_state(True)
        except Exception as exc:
            self._status(f"Playback failed: {exc}")

    def _play_from_table(self, table, track: Any):
        if not track:
            return
        tracks = table.tracks()
        index = next((i for i, item in enumerate(tracks) if track_id(item) == track_id(track)), 0)
        play_queue = getattr(self.playback_controller, "play_queue", None)
        if callable(play_queue) and tracks:
            try:
                play_queue(tracks, index)
                self._set_current_track(track)
                self.playback_bar.set_playback_state(True)
                return
            except TypeError:
                try:
                    play_queue(tracks, start_index=index)
                    self._set_current_track(track)
                    self.playback_bar.set_playback_state(True)
                    return
                except TypeError:
                    pass
                except Exception as exc:
                    self._status(f"Playback failed: {exc}")
                    return
            except Exception as exc:
                self._status(f"Playback failed: {exc}")
                return
        self._play_track(track)

    def _play_next(self, track):
        self._controller_call("play_next", track)
        self._refresh_queue()

    def _add_to_queue(self, track):
        self._controller_call("add_to_queue", track)
        self._refresh_queue()

    def _controller_call(self, method_name: str, *args):
        method = getattr(self.playback_controller, method_name, None) if self.playback_controller else None
        if not callable(method):
            self._status(f"Playback action unavailable: {method_name.replace('_', ' ')}")
            return None
        try:
            return method(*args)
        except Exception as exc:
            self._status(f"Playback action failed: {exc}")
            return None

    def _set_current_track(self, track, *, force: bool = False):
        changed = force or track_id(track) != track_id(self._current_track)
        self._current_track = track
        if changed:
            self.playback_bar.set_track(track)
            self.now_playing_page.set_track(track)
        self._update_current_favorite()
        if changed and self._active_page == "lyrics":
            self._load_lyrics(track)

    def _add_favorite(self, track):
        if not track:
            return
        if any(track_id(item) == track_id(track) for item in self._favorites):
            self._status("Already in Favorites.")
            return
        favorites = next((item for item in self._playlists if str(value(item, "name", "title", default=item)).casefold() == "favorites"), None)
        if favorites is None:
            create = getattr(self.playlist_service, "create_playlist", None)
            if not callable(create):
                self._status("Favorites are unavailable from the playlist service.")
                return
            try:
                favorites = create("Favorites")
            except TypeError:
                favorites = create(name="Favorites")
            except Exception as exc:
                self._status(f"Couldn't create Favorites: {exc}")
                return
            if favorites is None:
                favorites = {"name": "Favorites", "id": "Favorites"}
                self._playlists.append(favorites)
        add = getattr(self.playlist_service, "add_track", None)
        if not callable(add):
            self._status("The playlist service cannot add tracks.")
            return
        try:
            add(value(favorites, "id", "playlist_id", "name", default=favorites), track_id(track))
            self._status("Added to Favorites.")
            self._reload_collections()
        except Exception as exc:
            self._status(f"Couldn't add favorite: {exc}")

    def _prompt_add_to_playlist(self, track):
        if not track:
            return
        dialog = PlaylistSelectDialog(self._playlists, self)
        if not dialog.exec():
            return
        playlist = dialog.selected_playlist
        if isinstance(playlist, str):
            playlist = next((item for item in self._playlists if str(value(item, "name", "title", default=item)) == playlist), None)
        if playlist is None and isinstance(dialog.selected_playlist, str):
            create = getattr(self.playlist_service, "create_playlist", None)
            if not callable(create):
                self._status("The playlist service cannot create playlists.")
                return
            try:
                playlist = create(dialog.selected_playlist)
                if playlist is None:
                    playlist = {"id": dialog.selected_playlist, "name": dialog.selected_playlist}
            except Exception as exc:
                self._status(f"Couldn't create playlist: {exc}")
                return
        add = getattr(self.playlist_service, "add_track", None)
        if not callable(add) or not playlist:
            self._status("The selected playlist is unavailable.")
            return
        try:
            add(value(playlist, "id", "playlist_id", "name", default=playlist), track_id(track))
            self._status("Track added to playlist.")
            self._reload_collections()
        except Exception as exc:
            self._status(f"Couldn't add track: {exc}")

    def _create_playlist(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New playlist", "Playlist name")
        if not ok or not name.strip():
            return
        create = getattr(self.playlist_service, "create_playlist", None)
        if not callable(create):
            self._status("The playlist service cannot create playlists.")
            return
        try:
            create(name.strip())
            self._reload_collections()
            self._navigate("playlists")
            self._status("Playlist created.")
        except Exception as exc:
            self._status(f"Couldn't create playlist: {exc}")

    def _rename_playlist(self, playlist):
        from PySide6.QtWidgets import QInputDialog
        old_name = str(value(playlist, "name", "title", default=playlist))
        new_name, ok = QInputDialog.getText(self, "Rename playlist", "Playlist name", text=old_name)
        if not ok or not new_name.strip():
            return
        method = getattr(self.playlist_service, "rename_playlist", None)
        if not callable(method):
            self._status("The playlist service cannot rename playlists.")
            return
        try:
            try:
                method(value(playlist, "id", "playlist_id", "name", default=playlist), new_name.strip())
            except TypeError:
                method(old_name, new_name.strip())
            self._reload_collections()
        except Exception as exc:
            self._status(f"Couldn't rename playlist: {exc}")

    def _delete_playlist(self, playlist):
        name = str(value(playlist, "name", "title", default=playlist))
        if name.casefold() == "favorites":
            self._status("Favorites cannot be deleted.")
            return
        answer = QMessageBox.question(self, "Delete playlist", f"Delete '{name}'?", QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Delete:
            return
        method = getattr(self.playlist_service, "delete_playlist", None)
        if not callable(method):
            self._status("The playlist service cannot delete playlists.")
            return
        try:
            method(value(playlist, "id", "playlist_id", "name", default=playlist))
            self._reload_collections()
            self._status("Playlist deleted.")
        except Exception as exc:
            self._status(f"Couldn't delete playlist: {exc}")

    def _open_playlist(self, playlist):
        self._navigate("playlists")
        self.playlists_page.select_playlist(playlist)
        self.playlists_page.set_playlist_tracks(playlist, [])
        self._load_playlist_tracks(playlist)

    def _load_playlist_tracks(self, playlist):
        method = getattr(self.playlist_service, "get_playlist_tracks", None) if self.playlist_service else None
        if not callable(method):
            self.playlists_page.set_playlist_tracks(playlist, [])
            return
        identifier = value(playlist, "id", "playlist_id", "name", default=playlist)
        task = _BackgroundCall(method, (identifier,))
        task.signals.done.connect(lambda result, error, p=playlist: self._playlist_tracks_loaded(p, result, error))
        self._thread_pool.start(task)

    def _playlist_tracks_loaded(self, playlist, result, error):
        if error:
            self._status(f"Couldn't load playlist: {error}")
            return
        current = self.playlists_page.current_playlist()
        if current is not None and value(current, "id", "playlist_id", "name", default=current) != value(playlist, "id", "playlist_id", "name", default=playlist):
            return
        tracks = _as_list(result)
        by_id = {str(track_id(track)): track for track in self._tracks}
        tracks = [by_id.get(str(track_id(item)), item) for item in tracks]
        self.playlists_page.set_playlist_tracks(playlist, tracks)

    def _current_playlist_tracks(self):
        return self.playlists_page.table.tracks()

    def _play_current_playlist(self):
        self._play_table(self.playlists_page.table)

    def _play_table(self, table):
        track = table.current_track() or (table.tracks()[0] if table.tracks() else None)
        if track:
            self._play_from_table(table, track)

    def _shuffle_current_playlist(self):
        tracks = self._current_playlist_tracks()
        if tracks:
            set_shuffle = getattr(self.playback_controller, "set_shuffle", None)
            play_queue = getattr(self.playback_controller, "play_queue", None)
            if callable(set_shuffle) and callable(play_queue):
                try:
                    set_shuffle(True)
                    self.playback_bar.set_shuffle(True)
                    play_queue(tracks, 0)
                    self._set_current_track(tracks[0])
                    self.playback_bar.set_playback_state(True)
                except Exception as exc:
                    self._status(f"Playback failed: {exc}")

    def _queue_current_playlist(self):
        for track in self._current_playlist_tracks():
            self._controller_call("add_to_queue", track)
        self._refresh_queue()

    def _move_playlist_track(self, delta: int):
        playlist = self.playlists_page.current_playlist()
        table = self.playlists_page.table
        index = table.table.currentIndex()
        if not playlist or not index.isValid():
            return
        source_row = table.proxy_model.mapToSource(index).row()
        target_row = source_row + delta
        tracks = table.tracks()
        if not 0 <= target_row < len(tracks):
            return
        move = getattr(self.playlist_service, "move_track", None)
        if not callable(move):
            self._status("Track reordering is unavailable.")
            return
        identifier = value(playlist, "id", "playlist_id", "name", default=playlist)
        try:
            try:
                move(identifier, track_id(tracks[source_row]), target_row)
            except TypeError:
                move(identifier, source_row, target_row)
            self._load_playlist_tracks(playlist)
        except Exception as exc:
            self._status(f"Couldn't reorder playlist: {exc}")

    def _play_detail_tracks(self):
        self._play_table(self.detail_page.table)

    def _shuffle_detail_tracks(self):
        tracks = self.detail_page.table.tracks()
        if tracks:
            self._controller_call("set_shuffle", True)
            self.playback_bar.set_shuffle(True)
            method = getattr(self.playback_controller, "play_queue", None)
            if callable(method):
                try:
                    method(tracks, 0)
                    self._set_current_track(tracks[0])
                    self.playback_bar.set_playback_state(True)
                except Exception as exc:
                    self._status(f"Playback failed: {exc}")

    def _add_songs_to_current_playlist(self):
        playlist = self.playlists_page.current_playlist()
        if not playlist:
            return
        dialog = TrackPickerDialog(self._tracks, self.metadata_service, self)
        if not dialog.exec():
            return
        add = getattr(self.playlist_service, "add_track", None)
        if not callable(add):
            self._status("The playlist service cannot add tracks.")
            return
        identifier = value(playlist, "id", "playlist_id", "name", default=playlist)
        try:
            for track in dialog.selected_tracks():
                add(identifier, track_id(track))
            self._load_playlist_tracks(playlist)
            self._status("Playlist updated.")
        except Exception as exc:
            self._status(f"Couldn't update playlist: {exc}")

    def _reload_collections(self):
        task = _LibraryLoadTask(self.library_service, self.playlist_service, self.history_service)
        task.signals.done.connect(self._library_loaded)
        self._thread_pool.start(task)

    def _edit_metadata(self, track):
        if not callable(getattr(self.metadata_service, "read_metadata", None)) or not callable(getattr(self.metadata_service, "write_metadata", None)):
            self._status("Metadata editing is unavailable from the metadata service.")
            return
        dialog = MetadataEditorDialog(track, self.metadata_service, self)
        if dialog.exec():
            self._reload_collections()
            if track_id(track) == track_id(self._current_track):
                self._set_current_track(track, force=True)

    def _load_lyrics(self, track):
        self.lyrics_page.set_track_lyrics(track, None)
        if not track:
            return
        method = getattr(self.lyrics_service, "get_lyrics", None) if self.lyrics_service else None
        if not callable(method):
            self._status("Lyrics are unavailable from the lyrics service.")
            return
        identifier = track
        self.lyrics_page.title.setText("Lyrics · Loading…")
        task = _BackgroundCall(method, (identifier,))
        task.signals.done.connect(lambda result, error, selected=track: self._lyrics_loaded(selected, result, error))
        self._thread_pool.start(task)

    def _lyrics_loaded(self, track, lyrics, error):
        if track_id(track) != track_id(self._current_track):
            return
        self.lyrics_page.title.setText("Lyrics")
        self.lyrics_page.set_track_lyrics(track, lyrics if not error else None)
        if error:
            self._status(f"Couldn't load lyrics: {error}")

    def _edit_lyrics(self, track, lyrics):
        if not callable(getattr(self.lyrics_service, "save_lyrics", None)):
            self._status("Lyrics editing is unavailable from the lyrics service.")
            return
        dialog = LyricsEditorDialog(track, self.lyrics_service, lyrics, self)
        if dialog.exec():
            self._load_lyrics(track)

    def _show_track_menu(self, track):
        if not track:
            return
        menu = QMenu(self)
        menu.addAction("Play next", lambda: self._play_next(track))
        menu.addAction("Add to queue", lambda: self._add_to_queue(track))
        menu.addSeparator()
        menu.addAction("Add to favorites", lambda: self._add_favorite(track))
        menu.addAction("Add to playlist…", lambda: self._prompt_add_to_playlist(track))
        menu.addAction("Edit track details…", lambda: self._edit_metadata(track))
        menu.exec(self.mapToGlobal(self.rect().center()))

    def _toggle_queue(self):
        self._queue_visible = not self._queue_visible
        self.queue_panel.setVisible(self._queue_visible)
        self.queue_button.setChecked(self._queue_visible)
        self.queue_button.setProperty("active", self._queue_visible)
        self.queue_button.style().unpolish(self.queue_button)
        self.queue_button.style().polish(self.queue_button)
        self._refresh_queue()

    def _queue_add_more(self):
        if not self._tracks:
            self._navigate("songs")
            return
        dialog = TrackPickerDialog(self._tracks, self.metadata_service, self)
        if dialog.exec():
            for track in dialog.selected_tracks():
                self._controller_call("add_to_queue", track)
            self._refresh_queue()

    def _read_queue(self):
        controller = self.playback_controller
        for name in ("get_queue", "queue", "current_queue"):
            result = getattr(controller, name, None) if controller else None
            if result is not None:
                try:
                    return _as_list(result() if callable(result) else result)
                except Exception:
                    pass
        return []

    def _read_current_index(self):
        controller = self.playback_controller
        for name in ("current_index", "queue_index", "current_queue_index", "song_index", "song_pointer"):
            result = getattr(controller, name, None) if controller else None
            if result is not None:
                try:
                    return int(result() if callable(result) else result)
                except (TypeError, ValueError):
                    pass
        return -1

    def _refresh_queue(self):
        if hasattr(self, "queue_panel"):
            self.queue_panel.set_queue(self._read_queue(), self._read_current_index(), self._current_track)

    def _remove_queue_item(self, index):
        method = getattr(self.playback_controller, "remove_from_queue", None)
        if not callable(method):
            self._status("Queue removal is unavailable.")
            return
        queue = self._read_queue()
        if not 0 <= index < len(queue):
            return
        try:
            try:
                parameter = next(iter(inspect.signature(method).parameters.values())).name.casefold()
            except (StopIteration, TypeError, ValueError):
                parameter = "index"
            argument = index if any(token in parameter for token in ("index", "position", "row", "idx")) else track_id(queue[index]) if "id" in parameter else queue[index]
            method(argument)
            self._refresh_queue()
        except Exception as exc:
            self._status(f"Couldn't remove queue item: {exc}")

    def _move_queue_item(self, old, new):
        self._controller_call("move_queue_item", old, new)
        self._refresh_queue()

    def _play_queue_index(self, index):
        queue = self._read_queue()
        if not 0 <= index < len(queue):
            return
        track = queue[index]
        method = getattr(self.playback_controller, "play_queue", None)
        if callable(method):
            try:
                method(queue, index)
                self._set_current_track(track)
                self.playback_bar.set_playback_state(True)
            except Exception as exc:
                self._status(f"Couldn't play queue item: {exc}")
        else:
            self._play_track(track)

    def _clear_queue(self):
        self._controller_call("clear_queue")
        self._refresh_queue()

    def _connect_controller_signals(self):
        mapping = {
            "track_changed": self._on_track_changed,
            "current_track_changed": self._on_track_changed,
            "playback_state_changed": self._on_playback_state,
            "is_playing_changed": self._on_playback_state,
            "position_changed": self._on_position_changed,
            "duration_changed": self._on_duration_changed,
            "volume_changed": self.playback_bar.set_volume,
            "shuffle_changed": self.playback_bar.set_shuffle,
            "repeat_mode_changed": self.playback_bar.set_repeat_mode,
            "queue_changed": self._on_queue_changed,
        }
        for name, slot in mapping.items():
            signal = getattr(self.playback_controller, name, None) if self.playback_controller else None
            if hasattr(signal, "connect"):
                try:
                    signal.connect(slot)
                except (RuntimeError, TypeError):
                    pass

    def _sync_controller_state(self):
        controller = self.playback_controller
        track = value(controller, "current_track", "track", default=None) if controller else None
        if track:
            self._set_current_track(track)
        state = value(controller, "is_playing", "playing", default=False)
        playing = state.lower() in ("playing", "play", "started") if isinstance(state, str) else bool(state)
        self.playback_bar.set_playback_state(playing)
        self.playback_bar.set_position(float(value(controller, "position", "position_seconds", default=0) or 0), float(value(controller, "duration", "duration_seconds", default=0) or 0))
        self.playback_bar.set_shuffle(bool(value(controller, "shuffle", "is_shuffle", default=False)))
        repeat = value(controller, "repeat_mode", default=self._get_setting("playback.repeat", "off"))
        repeat = {0: "off", 1: "all", 2: "one"}.get(repeat, repeat)
        self.playback_bar.set_repeat_mode(str(repeat))
        self._refresh_queue()

    def _on_track_changed(self, track, *args):
        if isinstance(track, dict) and "track" in track:
            track = track["track"]
        self._set_current_track(track)

    def _on_playback_state(self, state, *args):
        if isinstance(state, str):
            playing = state.lower() in ("playing", "play", "started")
        else:
            playing = bool(state)
        self.playback_bar.set_playback_state(playing)

    def _on_position_changed(self, position, *args):
        duration = args[0] if args else None
        self.playback_bar.set_position(float(position), float(duration) if duration is not None else None)

    def _on_duration_changed(self, duration, *args):
        self.playback_bar.set_position(self.playback_bar.position, float(duration))

    def _on_queue_changed(self, *args):
        self._refresh_queue()

    def _toggle_favorite(self, track):
        if not track:
            return
        if not any(track_id(item) == track_id(track) for item in self._favorites):
            self._add_favorite(track)
            return
        playlist = next((item for item in self._playlists if str(value(item, "name", "title", default=item)).casefold() == "favorites"), None)
        remove = getattr(self.playlist_service, "remove_track", None)
        if playlist is None or not callable(remove):
            self._status("Favorites cannot be updated right now.")
            return
        try:
            remove(value(playlist, "id", "playlist_id", "name", default=playlist), track_id(track))
            self._status("Removed from Favorites.")
            self._reload_collections()
        except Exception as exc:
            self._status(f"Couldn't remove favorite: {exc}")

    def _update_current_favorite(self):
        favorite = bool(self._current_track and any(track_id(item) == track_id(self._current_track) for item in self._favorites))
        self.playback_bar.set_favorite(favorite)

    def _remove_from_collection(self, table, track):
        if table is self.favorites_page.table:
            playlist = next((item for item in self._playlists if str(value(item, "name", "title", default=item)).casefold() == "favorites"), None)
        else:
            playlist = self.playlists_page.current_playlist()
        remove = getattr(self.playlist_service, "remove_track", None)
        if playlist is None or not callable(remove):
            self._status("This collection cannot remove tracks.")
            return
        try:
            remove(value(playlist, "id", "playlist_id", "name", default=playlist), track_id(track))
            self._reload_collections()
            if table is self.playlists_page.table:
                self._load_playlist_tracks(playlist)
        except Exception as exc:
            self._status(f"Couldn't remove track: {exc}")

    def _install_shortcuts(self):
        self._shortcuts = []
        for sequence, callback in (
            ("Space", self._shortcut_play), ("Ctrl+Right", lambda: self._controller_call("next")),
            ("Ctrl+Left", lambda: self._controller_call("previous")), ("Ctrl+F", self.global_search.setFocus),
            ("Ctrl+O", self._add_files_dialog), ("Ctrl+Q", self._toggle_queue),
            ("Ctrl+L", lambda: self.navigate("lyrics")), ("Ctrl+D", self._toggle_favorite_current),
            ("Ctrl+,", lambda: self.navigate("settings")),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda cb=callback: self._shortcut_dispatch(cb))
            self._shortcuts.append(shortcut)

    def _shortcut_dispatch(self, callback):
        focus = QApplication.focusWidget()
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QSpinBox, QTextEdit
        if focus is not None and not self.isAncestorOf(focus):
            return
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox)):
            return
        callback()

    def _shortcut_play(self):
        focus = QApplication.focusWidget()
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QSpinBox, QTextEdit
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox)):
            return
        self._controller_call("toggle_play_pause")

    def _toggle_favorite_current(self):
        if self._current_track:
            self._toggle_favorite(self._current_track)

    def _add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add music files", "", "Audio files (*.mp3 *.flac *.wav *.ogg *.m4a *.aac *.opus);;All files (*.*)")
        if not files:
            return
        method = getattr(self.library_service, "scan_library", None)
        if not callable(method):
            self._status("The library service cannot scan files.")
            return
        self._status("Adding music in the background…")
        task = _BackgroundCall(_call_compatible, (method,), {"keyword": "paths", "value": files})
        task.signals.done.connect(self._files_added)
        self._thread_pool.start(task)

    def _files_added(self, result, error):
        if error:
            self._status(f"Couldn't add music: {error}")
        else:
            self._status("Music added. Refreshing library…")
            self._load_library_async()

    def _status(self, message: str):
        self.statusBar().showMessage(str(message), 5000)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.width() < 1160 and self._queue_visible:
            self._queue_visible = False
            self.queue_panel.setVisible(False)
            self.queue_button.setChecked(False)
