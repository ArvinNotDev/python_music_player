"""Compact, consistent SVG icon set rendered through Qt's SVG support."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_PATHS = {
    "home": '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-6v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    "play": '<path d="m8 5 11 7-11 7z" fill="currentColor" stroke="none"/>',
    "pause": '<path d="M7 5h4v14H7zM15 5h4v14h-4z" fill="currentColor" stroke="none"/>',
    "next": '<path d="m4 5 10 7-10 7zM17 5h3v14h-3z" fill="currentColor" stroke="none"/>',
    "previous": '<path d="m20 5-10 7 10 7zM4 5h3v14H4z" fill="currentColor" stroke="none"/>',
    "songs": '<path d="M9 18V5l12-2v13M9 18a3 3 0 1 1-3-3c1.66 0 3 1.34 3 3Zm12-2a3 3 0 1 1-3-3c1.66 0 3 1.34 3 3ZM9 8l12-2"/>',
    "album": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
    "artist": '<circle cx="9" cy="8" r="4"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 4a4 4 0 0 1 0 8m2 3a5 5 0 0 1 3 4v2"/>',
    "recent": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2M4 4v5h5"/>',
    "playlist": '<path d="M4 6h12M4 11h12M4 16h8M19 14v7m-3.5-3.5h7"/>',
    "heart": '<path d="M20.8 8.8c0 5.5-8.8 11-8.8 11s-8.8-5.5-8.8-11a4.8 4.8 0 0 1 8.8-2.5 4.8 4.8 0 0 1 8.8 2.5Z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.5.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.5-.9l-1.7.7L6.3 16l1.4-1.1a8 8 0 0 1 0-1.8L6.3 12l1.4-2.4 1.7.7a8 8 0 0 1 1.5-.9l.3-1.8H14l.3 1.8a8 8 0 0 1 1.5.9l1.7-.7 1.4 2.4-1.4 1.1a8 8 0 0 1-.1 1.9Z" transform="translate(-1 -1)"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "queue": '<path d="M4 6h15M4 11h15M4 16h9M18 15v7m-3.5-3.5h7"/>',
    "lyrics": '<path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/>',
    "more": '<circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/>',
    "shuffle": '<path d="m18 14 3 3-3 3M3 7h2c5 0 7 10 12 10h4M18 4l3 3-3 3M3 17h2c2 0 3.4-1.5 4.6-3.3M14.4 10.3C15.2 8.6 16 7 17 7h4"/>',
    "repeat": '<path d="m17 2 4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4m14-3v2a3 3 0 0 1-3 3H3"/>',
    "repeat_one": '<path d="m17 2 4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4m14-3v2a3 3 0 0 1-3 3H3"/><path d="M10.5 10.2 12 9v6m-1.8 0h3.6"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "volume": '<path d="M4 10v4h4l5 4V6l-5 4zM17 9a5 5 0 0 1 0 6m2-9a9 9 0 0 1 0 12"/>',
    "mute": '<path d="M4 10v4h4l5 4V6l-5 4zM17 9l5 6m0-6-5 6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "back": '<path d="m15 18-6-6 6-6"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "edit": '<path d="m4 16-.8 4.8L8 20l12-12-4-4zM13 7l4 4"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 14h12l1-14M9 7V4h6v3"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2h6M12 2v3"/>',
    "command": '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
}


@lru_cache(maxsize=128)
def icon(name: str, color: str = "#F4F5F8", size: int = 20) -> QIcon:
    path = _PATHS.get(name, _PATHS["album"])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" color="{color}">{path}</g></svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
