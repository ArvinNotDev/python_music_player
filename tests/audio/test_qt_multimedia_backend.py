from __future__ import annotations

import wave

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from core.audio.audio_backend import QtMultimediaBackend


def test_qt_backend_volume_mute_and_repeated_shutdown(qcore_application):
    backend = QtMultimediaBackend()
    values: list[float] = []
    muted: list[bool] = []
    backend.volume_changed.connect(values.append)
    backend.muted_changed.connect(muted.append)

    backend.set_volume(0.3)
    backend.set_muted(True)
    backend.set_muted(False)
    assert backend.volume == pytest.approx(0.3)
    assert not backend.is_muted
    assert values[-1] == pytest.approx(0.3)
    assert muted == [True, False]

    backend.shutdown()
    backend.shutdown()


def test_qt_backend_reports_generated_wav_loading_status(tmp_path, qcore_application):
    wav_path = tmp_path / "generated.wav"
    with wave.open(str(wav_path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8_000)
        file.writeframes(b"\x00\x00" * 800)

    backend = QtMultimediaBackend()
    statuses: list[str] = []
    loop = QEventLoop()
    backend.media_status_changed.connect(statuses.append)
    backend.media_status_changed.connect(
        lambda status: loop.quit() if status in ("loadedmedia", "invalidmedia") else None
    )
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5_000)
    backend.set_source(str(wav_path))
    loop.exec()
    timer.stop()
    backend.shutdown()

    assert "loadingmedia" in statuses
    assert "loadedmedia" in statuses, f"Qt Multimedia did not load WAV: {statuses!r}"
