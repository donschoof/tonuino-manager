import os
import sys
from pathlib import Path

# Qt-Tests (gui.*) brauchen keinen Bildschirm
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
