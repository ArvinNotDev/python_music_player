"""Sleep timer dialog for scheduled playback pause."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)


class SleepTimerDialog(QDialog):
    """Choose a one-shot sleep timer duration in minutes."""

    def __init__(self, parent: QWidget | None = None, default_minutes: int = 30):
        super().__init__(parent)
        self.setObjectName("SleepTimerDialog")
        self.setWindowTitle("Sleep timer")
        self.setModal(True)
        self.setMinimumWidth(390)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(14)

        title = QLabel("Wind down with RW Player")
        title.setStyleSheet("font-size: 20px; font-weight: 750;")
        subtitle = QLabel("Playback will pause automatically when the timer ends.")
        subtitle.setProperty("role", "secondary")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("Surface")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)
        label_row = QHBoxLayout()
        label = QLabel("Pause playback in")
        self.minutes_input = QSpinBox()
        self.minutes_input.setRange(1, 240)
        self.minutes_input.setValue(max(1, min(240, int(default_minutes))))
        self.minutes_input.setSuffix(" min")
        self.minutes_input.setFixedWidth(112)
        label_row.addWidget(label)
        label_row.addStretch(1)
        label_row.addWidget(self.minutes_input)
        card_layout.addLayout(label_row)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        self.preset_buttons: dict[int, QPushButton] = {}
        for minutes in (15, 30, 45, 60, 90):
            button = QPushButton(f"{minutes}m")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(
                lambda _checked=False, value=minutes: self.minutes_input.setValue(value)
            )
            presets.addWidget(button)
            self.preset_buttons[minutes] = button
        card_layout.addLayout(presets)
        root.addWidget(card)

        note = QLabel("This timer is active for the current session only.")
        note.setProperty("role", "muted")
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start timer")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def duration_minutes(self) -> int:
        return int(self.minutes_input.value())
