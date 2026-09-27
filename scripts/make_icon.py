"""Regenerates assets/murmur.ico from the logo drawn in murmur/ui/style.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from murmur.ui import style  # noqa: E402

app = QGuiApplication(sys.argv)
(ROOT / "assets").mkdir(exist_ok=True)
style.write_ico(ROOT / "assets" / "murmur.ico")
style.logo_image(512).save(str(ROOT / "assets" / "murmur.png"))
print("Wrote assets/murmur.ico and assets/murmur.png")
