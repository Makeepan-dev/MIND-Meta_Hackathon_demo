"""
MIND — Mageepan's Intelligence Network Device
Meta Global AI Hackathon Desktop Application Launcher.

Launches the complete PC desktop interface with the JARVIS-inspired circular AI core.
"""

import sys
import os
from pathlib import Path

# Set paths
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MIND_GameDev"))
sys.path.insert(0, str(ROOT / "MIND_Code"))
sys.path.insert(0, str(ROOT / "MIND_Public"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from MIND_GameDev.ui.main_window import MINDMainWindow


def main():
    # Enable high DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    app.setApplicationName("MIND — Meta Global AI Hackathon Edition")
    app.setOrganizationName("MIND Artificial Intelligence")

    window = MINDMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
