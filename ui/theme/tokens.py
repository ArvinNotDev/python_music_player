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
        background="#101116", sidebar="#15171D", surface="#1B1E26", elevated="#222631",
        input="#171A21", text="#F4F5F8", secondary="#B0B5C1", muted="#7E8492",
        border="#2B2F3A", accent="#8B7CFF", accent_hover="#A095FF", selected="#302B50",
        success="#65C995", warning="#E9B86B", error="#F07883",
    ),
    "light": Palette(
        background="#F4F5F8", sidebar="#ECEEF3", surface="#FFFFFF", elevated="#F8F9FC",
        input="#FFFFFF", text="#181A22", secondary="#555B68", muted="#7F8592",
        border="#DDE0E7", accent="#6656D9", accent_hover="#5142C4", selected="#E7E3FF",
        success="#218553", warning="#A66A10", error="#C23E4C",
    ),
}

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32, "3xl": 48}
RADIUS = {"sm": 6, "md": 10, "lg": 14, "pill": 999}
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
    p = PALETTES[resolve_theme(theme)]
    a = accent or p.accent
    pad = 6 if density == "compact" else 9
    return f"""
        QWidget {{ color: {p.text}; font-family: Inter, 'Segoe UI', sans-serif; font-size: 13px; }}
        QMainWindow, QDialog {{ background: {p.background}; }}
        QFrame#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
        QFrame#PlaybackBar {{ background: {p.sidebar}; border-top: 1px solid {p.border}; }}
        QFrame#Surface, QFrame.surface {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
        QLabel[role="muted"] {{ color: {p.muted}; }}
        QLabel[role="secondary"] {{ color: {p.secondary}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
            background: {p.input}; border: 1px solid {p.border}; border-radius: 8px;
            padding: {pad}px 10px; selection-background-color: {p.selected};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {a}; }}
        QPushButton {{ background: {p.elevated}; border: 1px solid {p.border}; border-radius: 8px; padding: 8px 12px; }}
        QPushButton:hover, QToolButton:hover {{ background: {p.selected}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {p.accent}; }}
        QPushButton[primary="true"] {{ background: {a}; border-color: {a}; color: #FFFFFF; font-weight: 600; }}
        QPushButton[primary="true"]:hover {{ background: {p.accent_hover}; }}
        QToolButton {{ background: transparent; border: 0; border-radius: 8px; padding: 6px; }}
        QToolButton[active="true"] {{ color: {a}; background: {p.selected}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {p.border}; min-height: 28px; border-radius: 4px; }}
        QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; border: 0; }}
        QSlider::groove:horizontal {{ background: {p.border}; height: 4px; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {a}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {p.text}; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; }}
        QTableView {{ background: transparent; alternate-background-color: {p.sidebar}; border: 0; gridline-color: transparent; selection-background-color: {p.selected}; selection-color: {p.text}; }}
        QHeaderView::section {{ background: transparent; color: {p.muted}; border: 0; border-bottom: 1px solid {p.border}; padding: 8px; font-weight: 600; }}
        QMenu {{ background: {p.elevated}; border: 1px solid {p.border}; padding: 5px; }}
        QMenu::item {{ padding: 7px 24px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {p.selected}; }}
        QToolTip {{ background: {p.elevated}; color: {p.text}; border: 1px solid {p.border}; padding: 5px 8px; }}
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.border}; border-radius: 4px; background: {p.input}; }}
        QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
        QToolButton:focus, QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ outline: none; border-color: {a}; }}
        QToolButton:disabled, QPushButton:disabled {{ color: {p.muted}; background: {p.surface}; }}
        QProgressBar {{ background: {p.border}; border: 0; border-radius: 4px; text-align: center; min-height: 7px; max-height: 7px; }}
        QProgressBar::chunk {{ background: {a}; border-radius: 4px; }}
        QDialog#CommandPalette, QDialog#SleepTimerDialog {{ background: transparent; }}
        QFrame#CommandPaletteSurface {{ background: {p.elevated}; border: 1px solid {p.border}; border-radius: 16px; }}
        QLabel#CommandPaletteHeading {{ font-size: 16px; font-weight: 700; }}
        QLabel#CommandPaletteHint {{ color: {p.muted}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
        QLineEdit#CommandPaletteInput {{ background: {p.input}; border: 1px solid {p.border}; border-radius: 10px; padding: 12px 14px; font-size: 14px; }}
        QListWidget#CommandPaletteList {{ background: transparent; border: 0; outline: 0; padding: 2px; }}
        QListWidget#CommandPaletteList::item {{ padding: 12px 10px; border-radius: 8px; min-height: 20px; }}
        QListWidget#CommandPaletteList::item:selected {{ background: {p.selected}; color: {p.text}; }}
        QLabel#CommandPaletteEmpty {{ color: {p.muted}; padding: 12px; }}
        QFrame#SleepTimerDialog QSpinBox {{ min-height: 28px; }}
    """
