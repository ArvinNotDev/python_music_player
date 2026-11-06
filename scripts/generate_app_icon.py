"""Generate the Windows ICO file from the shared SVG application icon."""

from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets" / "rw_player.svg"
ICO_PATH = ROOT / "assets" / "rw_player.ico"


def main() -> int:
    # Rendering SVG text/fonts requires a Qt GUI application instance.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QGuiApplication([])
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        raise RuntimeError(f"Could not load application icon: {SVG_PATH}")

    size = 256
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()

    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open an in-memory image buffer.")
    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Could not render SVG application icon to PNG.")
        png_bytes = bytes(buffer.data())
    finally:
        buffer.close()

    with Image.open(io.BytesIO(png_bytes)) as source:
        source.save(ICO_PATH, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Generated {ICO_PATH}")
    application.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
