"""Central visual tokens and application-wide Qt styles."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Palette:
    background: str
    sidebar: str
    surface: str
    elevated: str
    input: str
    text: str
    secondary: str
    muted: str
    border: str
    accent: str
    accent_hover: str
    selected: str
    success: str
    warning: str
    error: str


PALETTES = {
    "dark": Palette(
        background="#0F1117", sidebar="#141720", surface="#191E28", elevated="#222A36",
        input="#151A23", text="#F4F6FA", secondary="#AAB2C0", muted="#778294",
        border="#2A3241", accent="#8B7CFF", accent_hover="#A397FF", selected="#302D4D",
        success="#65C995", warning="#E9B86B", error="#F07883",
    ),
    "light": Palette(
        background="#F5F7FA", sidebar="#EEF1F6", surface="#FFFFFF", elevated="#FAFBFD",
        input="#F9FAFC", text="#1B2432", secondary="#566274", muted="#8792A2",
        border="#E0E6EF", accent="#6658D8", accent_hover="#5547C2", selected="#E9E6FF",
        success="#218553", warning="#A66A10", error="#C23E4C",
    ),
}

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32, "3xl": 48}
RADIUS = {"sm": 7, "md": 10, "lg": 14, "xl": 18, "pill": 999}
TYPE = {"caption": 11, "small": 12, "body": 13, "subtitle": 15, "title": 22, "display": 30}
WEIGHT = {"regular": 400, "medium": 500, "semibold": 650, "bold": 700, "heavy": 800}
FONT_FAMILY = "Inter"
SHADOWS = {"card": "0 8px 24px rgba(0, 0, 0, 0.18)", "dialog": "0 16px 48px rgba(0, 0, 0, 0.24)"}
ANIMATION_MS = {"fast": 120, "normal": 180, "slow": 260, "page": 210, "artwork": 190, "hover": 210}


def resolve_theme(theme: str) -> str:
    if theme == "system":
        scheme = QGuiApplication.styleHints().colorScheme()
        return "light" if scheme.name.lower() == "light" else "dark"
    return theme if theme in PALETTES else "dark"


def stylesheet(theme: str = "dark", density: str = "comfortable", accent: str | None = None) -> str:
    """Build the application-wide stylesheet from the active design tokens."""
    p = PALETTES[resolve_theme(theme)]
    a = accent or p.accent
    pad = 6 if density == "compact" else 9
    return f"""
        QWidget {{
            color: {p.text};
            font-family: Inter, 'Segoe UI', 'Noto Sans', sans-serif;
            font-size: 13px;
            selection-background-color: {p.selected};
        }}
        QMainWindow, QDialog {{ background: {p.background}; }}
        QStatusBar {{ color: {p.secondary}; border-top: 1px solid {p.border}; }}
        QFrame#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
        QWidget#QueuePanel {{ background: {p.sidebar}; border-left: 1px solid {p.border}; }}
        QFrame#PlaybackBar {{ background: {p.sidebar}; border-top: 1px solid {p.border}; }}
        QFrame#Surface, QFrame.surface {{
            background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
        }}
        QFrame#NowPlayingSurface {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {p.surface}, stop:1 {p.elevated});
            border: 1px solid {p.border}; border-radius: 18px;
        }}
        QFrame#NowPlayingArtworkFrame {{
            background: {p.elevated}; border: 1px solid {p.border}; border-radius: 16px;
        }}
        QLabel[role="muted"] {{ color: {p.muted}; }}
        QLabel[role="secondary"] {{ color: {p.secondary}; }}
        QLabel[role="eyebrow"] {{
            color: {a}; font-size: 10px; font-weight: 750; letter-spacing: 1.5px;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
            background: {p.input}; border: 1px solid {p.border}; border-radius: 9px;
            padding: {pad}px 10px; selection-background-color: {p.selected};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border-color: {a};
        }}
        QPushButton {{
            background: {p.elevated}; border: 1px solid {p.border}; border-radius: 9px;
            padding: 9px 14px; min-height: 18px;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {p.selected}; border-color: {p.border}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {p.accent}; }}
        QPushButton:focus, QToolButton:focus {{ border: 1px solid {a}; }}
        QPushButton[primary="true"] {{
            background: {a}; border-color: {a}; color: #FFFFFF; font-weight: 650;
        }}
        QPushButton[primary="true"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
        QToolButton {{
            background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 6px;
        }}
        QToolButton[active="true"], QToolButton:checked {{
            color: {a}; background: {p.selected}; border-color: transparent;
        }}
        QToolButton:disabled, QPushButton:disabled {{ color: {p.muted}; background: {p.surface}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {p.border}; min-width: 28px; min-height: 28px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {p.muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent; border: 0;
        }}
        QSlider::groove:horizontal {{ background: {p.border}; height: 4px; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {a}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: {p.text}; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
        }}
        QSlider::handle:horizontal:hover {{ background: {a}; width: 14px; margin: -6px 0; }}
        QTableView {{
            background: transparent; alternate-background-color: {p.sidebar}; border: 0;
            gridline-color: transparent; selection-background-color: {p.selected}; selection-color: {p.text};
        }}
        QHeaderView::section {{
            background: transparent; color: {p.muted}; border: 0; border-bottom: 1px solid {p.border};
            padding: 10px 8px; font-weight: 650;
        }}
        QTableView::item {{ padding: 6px 8px; border-bottom: 1px solid {p.border}; }}
        QTableView::item:hover {{ background: {p.elevated}; }}
        QTableView::item:selected {{ background: {p.selected}; color: {p.text}; }}
        QListWidget {{ background: transparent; border: 0; outline: 0; }}
        QMenu {{ background: {p.elevated}; border: 1px solid {p.border}; padding: 5px; }}
        QMenu::item {{ padding: 9px 26px; margin: 2px 4px; border-radius: 7px; }}
        QMenu::item:selected {{ background: {p.selected}; }}
        QMenu::separator {{ height: 1px; background: {p.border}; margin: 6px 12px; }}
        QToolTip {{
            background: {p.elevated}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 9px;
        }}
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; border: 1px solid {p.border}; border-radius: 4px; background: {p.input};
        }}
        QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
        QProgressBar {{
            background: {p.border}; border: 0; border-radius: 4px; text-align: center;
            min-height: 7px; max-height: 7px;
        }}
        QProgressBar::chunk {{ background: {a}; border-radius: 4px; }}
        QDialog#CommandPalette, QDialog#SleepTimerDialog {{ background: transparent; }}
        QFrame#CommandPaletteSurface {{ background: {p.elevated}; border: 1px solid {p.border}; border-radius: 16px; }}
        QLabel#CommandPaletteHeading {{ font-size: 16px; font-weight: 700; }}
        QLabel#CommandPaletteHint {{ color: {p.muted}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
        QLineEdit#CommandPaletteInput {{
            background: {p.input}; border: 1px solid {p.border}; border-radius: 10px; padding: 12px 14px; font-size: 14px;
        }}
        QListWidget#CommandPaletteList {{ background: transparent; border: 0; outline: 0; padding: 2px; }}
        QListWidget#CommandPaletteList::item {{ padding: 12px 10px; border-radius: 8px; min-height: 20px; }}
        QListWidget#CommandPaletteList::item:selected {{ background: {p.selected}; color: {p.text}; }}
        QLabel#CommandPaletteEmpty {{ color: {p.muted}; padding: 12px; }}
        QFrame#SleepTimerDialog QSpinBox {{ min-height: 28px; }}
    """
