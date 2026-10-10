"""Render assets/api-client.svg into assets/api-client.ico for the Windows build.

Run inside the project's venv (PySide6 is already a dependency; Pillow is installed
on demand by build.ps1 just for this step, it is not an app dependency).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent.parent
SVG_PATH = ROOT / "assets" / "api-client.svg"
ICO_PATH = ROOT / "assets" / "api-client.ico"
RENDER_SIZE = 256


def main() -> int:
    if not SVG_PATH.exists():
        print(f"error: {SVG_PATH} not found", file=sys.stderr)
        return 1

    app = QApplication.instance() or QApplication([])  # noqa: F841  (QSvgRenderer needs a QApplication)
    renderer = QSvgRenderer(QByteArray(SVG_PATH.read_bytes()))
    image = QImage(RENDER_SIZE, RENDER_SIZE, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    png_path = ICO_PATH.with_suffix(".png")
    image.save(str(png_path), "PNG")

    from PIL import Image

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    with Image.open(png_path) as im:
        im.save(ICO_PATH, format="ICO", sizes=sizes)
    png_path.unlink()

    print(f"wrote {ICO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
