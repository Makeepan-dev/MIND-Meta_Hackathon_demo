"""
MIND Universal Development Studio — Live Visual Website Preview Widget.
Implements real-time visual website rendering, responsive viewport presets
(Desktop, Tablet, Mobile), hot reload, dev logs drawer, and error recovery.
"""

from __future__ import annotations

import logging
import os
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QTextBrowser,
    QPlainTextEdit,
    QScrollArea,
    QButtonGroup,
    QSizePolicy,
)

logger = logging.getLogger("mind.ui.live_preview")

# Check for PyQt6.QtWebEngineWidgets dynamically
HAS_WEBENGINE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False

WELCOME_CANVAS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; }
  body {
    background-color: #050811;
    color: #EAF7FF;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    margin: 0;
    padding: 28px 24px;
    line-height: 1.5;
  }
  .container {
    max-width: 680px;
    margin: 0 auto;
  }
  .badge {
    display: inline-block;
    background-color: #0A1E14;
    color: #4DFFAA;
    border: 1px solid #1A4D30;
    border-radius: 4px;
    padding: 4px 10px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    margin-bottom: 12px;
  }
  h1 {
    color: #00F5FF;
    font-size: 22px;
    margin: 0 0 6px 0;
    font-weight: 700;
    letter-spacing: 0.5px;
  }
  .subtitle {
    color: #8095AC;
    font-size: 12px;
    margin: 0 0 20px 0;
  }
  .notice {
    background-color: #0A1020;
    border-left: 3px solid #00F5FF;
    border-radius: 4px;
    padding: 12px 14px;
    margin-bottom: 20px;
  }
  .notice-title {
    color: #00F5FF;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
    font-family: 'Consolas', monospace;
  }
  .notice-body {
    color: #B4C6D8;
    font-size: 12px;
    margin: 0;
  }
  .workflow-grid {
    margin-bottom: 20px;
  }
  .step-card {
    background-color: #0A1020;
    border: 1px solid #1B2A47;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
  }
  .step-num {
    color: #00F5FF;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: bold;
  }
  .step-title {
    color: #EAF7FF;
    font-size: 12px;
    font-weight: bold;
    margin-left: 6px;
  }
  .step-desc {
    color: #8095AC;
    font-size: 11px;
    margin: 4px 0 0 0;
  }
  .examples-box {
    background-color: #080D18;
    border: 1px solid #142036;
    border-radius: 6px;
    padding: 12px 14px;
  }
  .examples-header {
    color: #8095AC;
    font-family: 'Consolas', monospace;
    font-size: 10px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
  }
  .example-item {
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: #4DFFAA;
    padding: 3px 0;
  }
  .example-tag {
    color: #8095AC;
  }
</style>
</head>
<body>
<div class="container">
  <div class="badge">● LIVE VISUAL WORKSPACE // STANDING BY</div>
  <h1>MIND Visual Development Studio</h1>
  <div class="subtitle">Meta Global AI Hackathon Edition — Universal JARVIS Autonomous Workspace</div>

  <div class="notice">
    <div class="notice-title">Ready-To-Build Visual Canvas</div>
    <p class="notice-body">
      When you instruct MIND to create a website, game, 3D asset, or technical document,
      its live interactive prototype will be rendered directly in this viewport in real time.
    </p>
  </div>

  <div class="workflow-grid">
    <div class="step-card">
      <span class="step-num">01</span><span class="step-title">Understand & Decompose</span>
      <p class="step-desc">Enter your goal in chat. OrchestratorBrain plans tasks and assigns specialist brains.</p>
    </div>
    <div class="step-card">
      <span class="step-num">02</span><span class="step-title">Prototype & Interactive Review</span>
      <p class="step-desc">MIND crafts a reviewable prototype here first. Test layout, features, and interactions.</p>
    </div>
    <div class="step-card">
      <span class="step-num">03</span><span class="step-title">Real-Time Revisions</span>
      <p class="step-desc">Request styling or logic tweaks in chat. The preview reloads and updates automatically.</p>
    </div>
    <div class="step-card">
      <span class="step-num">04</span><span class="step-title">Approved Production Build</span>
      <p class="step-desc">Click "Approve & Develop" to run production builds, automated tests, and architectural audits.</p>
    </div>
  </div>

  <div class="examples-box">
    <div class="examples-header">Sample Commands To Get Started:</div>
    <div class="example-item"><span class="example-tag">🌐 Web: </span>"Build a modern portfolio website for a creative technologist"</div>
    <div class="example-item"><span class="example-tag">🎮 Game: </span>"Create a 3D endless runner cyber arcade game"</div>
    <div class="example-item"><span class="example-tag">🧊 3D: </span>"Generate and verify 3d mesh of a cylinder"</div>
    <div class="example-item"><span class="example-tag">📄 Research: </span>"Research and technical document report on quantum computing"</div>
  </div>
</div>
</body>
</html>
"""


class LiveWebsitePreviewWidget(QWidget):
    """
    Live visual development workspace container displaying the rendered website,
    responsive viewport controls, refresh actions, and build telemetry.
    """

    refresh_requested = pyqtSignal()
    viewport_changed = pyqtSignal(str)
    external_browser_opened = pyqtSignal(str)

    VIEWPORTS = {
        "desktop": ("🖥️ Desktop", None),      # 100% width
        "tablet": ("💻 Tablet", 768),         # 768px width
        "mobile": ("📱 Mobile", 375),         # 375px width
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_url: str = ""
        self.current_file_path: Optional[Path] = None
        self.current_viewport_mode: str = "desktop"
        self._last_valid_html: str = ""

        self._build_ui()
        self.show_welcome_canvas()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Top Control Toolbar
        # -------------------------------------------------------------
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("background-color: #0A1020; border-bottom: 1px solid #1B2A47; padding: 4px 8px;")
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(8, 6, 8, 6)
        tb_layout.setSpacing(8)

        # Status & Engine Badge
        self.status_badge = QLabel("● STANDBY")
        self.status_badge.setStyleSheet(
            "color: #8095AC; font-family: 'Consolas'; font-size: 10px; font-weight: bold; "
            "background: #101A2C; border: 1px solid #1B2A47; border-radius: 4px; padding: 3px 8px;"
        )
        tb_layout.addWidget(self.status_badge)

        self.engine_badge = QLabel(
            "🌐 Chromium Engine" if HAS_WEBENGINE else "📄 Native Browser Engine"
        )
        self.engine_badge.setStyleSheet(
            "color: #00F5FF; font-family: 'Consolas'; font-size: 10px; "
            "background: #101A2C; border: 1px solid #1B2A47; border-radius: 4px; padding: 3px 8px;"
        )
        tb_layout.addWidget(self.engine_badge)

        tb_layout.addStretch()

        # Viewport Toggle Buttons
        self.vp_btn_group = QButtonGroup(self)
        self.vp_buttons: Dict[str, QPushButton] = {}
        for mode, (label, _) in self.VIEWPORTS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(mode == "desktop")
            btn.setStyleSheet("""
                QPushButton {
                    background: #101A2C; color: #8095AC; border: 1px solid #1B2A47;
                    border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;
                }
                QPushButton:checked {
                    background: #00F5FF; color: #050811; border: 1px solid #00F5FF;
                }
                QPushButton:hover:!checked {
                    background: #1B2A47; color: #EAF7FF;
                }
            """)
            btn.clicked.connect(lambda checked, m=mode: self.set_viewport_mode(m))
            self.vp_btn_group.addButton(btn)
            self.vp_buttons[mode] = btn
            tb_layout.addWidget(btn)

        # Action Buttons
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #101A2C; color: #EAF7FF; border: 1px solid #1B2A47;
                border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background: #1B2A47; color: #00F5FF; }
        """)
        self.btn_refresh.clicked.connect(self.reload_preview)
        tb_layout.addWidget(self.btn_refresh)

        self.btn_browser = QPushButton("🌐 Open in Browser")
        self.btn_browser.setStyleSheet("""
            QPushButton {
                background: #101A2C; color: #4DFFAA; border: 1px solid #1B2A47;
                border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background: #1B2A47; color: #00F5FF; }
        """)
        self.btn_browser.clicked.connect(self._open_in_external_browser)
        tb_layout.addWidget(self.btn_browser)

        self.btn_logs = QPushButton("📜 Dev Logs")
        self.btn_logs.setCheckable(True)
        self.btn_logs.setChecked(False)
        self.btn_logs.setStyleSheet("""
            QPushButton {
                background: #101A2C; color: #8095AC; border: 1px solid #1B2A47;
                border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: bold;
            }
            QPushButton:checked { background: #397BFF; color: #FFFFFF; }
            QPushButton:hover:!checked { background: #1B2A47; color: #EAF7FF; }
        """)
        self.btn_logs.toggled.connect(self._toggle_dev_logs)
        tb_layout.addWidget(self.btn_logs)

        main_layout.addWidget(self.toolbar)

        # -------------------------------------------------------------
        # 2. Central Viewport Display Stage
        # -------------------------------------------------------------
        self.stage_scroll = QScrollArea(self)
        self.stage_scroll.setWidgetResizable(True)
        self.stage_scroll.setStyleSheet("background-color: #060A14; border: none;")
        self.stage_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.viewport_container = QFrame(self.stage_scroll)
        self.viewport_container.setStyleSheet("background-color: #050811;")
        self.vp_layout = QVBoxLayout(self.viewport_container)
        self.vp_layout.setContentsMargins(0, 0, 0, 0)
        self.vp_layout.setSpacing(0)

        # Embedded browser engine instantiation
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView(self.viewport_container)
            self.web_view.setStyleSheet("background: white;")
            self.vp_layout.addWidget(self.web_view)
            self.native_browser = None
        else:
            self.web_view = None
            self.native_browser = QTextBrowser(self.viewport_container)
            self.native_browser.setOpenExternalLinks(True)
            self.native_browser.setStyleSheet(
                "background-color: #050811; color: #EAF7FF; border: none; font-family: sans-serif; font-size: 14px;"
            )
            self.vp_layout.addWidget(self.native_browser)

        self.stage_scroll.setWidget(self.viewport_container)
        main_layout.addWidget(self.stage_scroll, stretch=1)

        # -------------------------------------------------------------
        # 3. Bottom Dev Logs Drawer (collapsible)
        # -------------------------------------------------------------
        self.logs_drawer = QFrame(self)
        self.logs_drawer.setFixedHeight(140)
        self.logs_drawer.setStyleSheet("background-color: #0A1020; border-top: 1px solid #1B2A47;")
        logs_layout = QVBoxLayout(self.logs_drawer)
        logs_layout.setContentsMargins(12, 6, 12, 6)
        logs_layout.setSpacing(4)

        lbl_logs = QLabel("LIVE DEVELOPMENT CONSOLE // SYNTHESIS & VALIDATION")
        lbl_logs.setStyleSheet("color: #8095AC; font-family: 'Consolas'; font-size: 9px; font-weight: bold;")
        logs_layout.addWidget(lbl_logs)

        self.log_text = QPlainTextEdit(self.logs_drawer)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background-color: #050811; color: #4DFFAA; border: 1px solid #1B2A47; "
            "border-radius: 4px; font-family: 'Consolas'; font-size: 11px; padding: 4px;"
        )
        logs_layout.addWidget(self.log_text)

        self.logs_drawer.hide()
        main_layout.addWidget(self.logs_drawer)

        # Default to Desktop viewport
        self.set_viewport_mode("desktop")

    def set_viewport_mode(self, mode: str) -> None:
        """Adjusts the viewport container width according to device profile."""
        if mode not in self.VIEWPORTS:
            mode = "desktop"
        self.current_viewport_mode = mode

        for m, btn in self.vp_buttons.items():
            btn.setChecked(m == mode)

        target_width = self.VIEWPORTS[mode][1]
        if target_width is None:
            # Full expanding width (Desktop)
            self.viewport_container.setMaximumWidth(16777215)
            self.viewport_container.setMinimumWidth(0)
            self.viewport_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.viewport_container.setStyleSheet("background-color: #050811; border: none;")
        else:
            # Fixed device width (Tablet / Mobile)
            self.viewport_container.setFixedWidth(target_width)
            self.viewport_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            self.viewport_container.setStyleSheet(
                f"background-color: #050811; border-left: 2px solid #1B2A47; border-right: 2px solid #1B2A47; "
                f"border-bottom: 2px solid #1B2A47; border-radius: 6px;"
            )

        self.append_log(f"Viewport adjusted to {mode.upper()} ({target_width or '100%'} width).")
        self.viewport_changed.emit(mode)

    def load_url(self, url: str) -> None:
        """Loads a given HTTP URL or file URL into the previewer."""
        self.current_url = url
        self.status_badge.setText("● RENDERING")
        self.status_badge.setStyleSheet(
            "color: #00F5FF; font-family: 'Consolas'; font-size: 10px; font-weight: bold; "
            "background: #101A2C; border: 1px solid #00F5FF; border-radius: 4px; padding: 3px 8px;"
        )

        if HAS_WEBENGINE and self.web_view:
            self.web_view.load(QUrl(url))
        elif self.native_browser:
            # If native browser, fetch content or read file
            if url.startswith("file:///"):
                local_path = url[8:].replace("/", os.sep)
                self.load_local_file(local_path)
            elif url.startswith("http://") or url.startswith("https://"):
                try:
                    import urllib.request
                    req = urllib.request.Request(url, headers={"User-Agent": "MIND-Preview/2.5"})
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        html_content = resp.read().decode("utf-8", errors="replace")
                        self.set_html(html_content, base_url=url)
                except Exception as e:
                    # Preview server unreachable: report and do NOT later flip the badge to READY.
                    self.show_build_error(f"Failed to fetch {url}: {e}")
                    return

        QTimer.singleShot(400, self._mark_rendered)

    def load_local_file(self, file_path: str | Path) -> None:
        """Loads an HTML file directly from the local workspace."""
        path = Path(file_path).resolve()
        self.current_file_path = path

        if not path.exists():
            self.show_build_error(f"HTML artifact not found: {path.name}")
            return

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                self.show_build_error(f"HTML artifact '{path.name}' is empty (0 bytes).")
                empty_placeholder = f"""
                <div style="background-color: #050811; color: #EAF7FF; font-family: 'Segoe UI', sans-serif; padding: 40px; text-align: center;">
                    <div style="font-size: 36px; margin-bottom: 12px; color: #FFB84D;">⚠️</div>
                    <h2 style="color: #00F5FF; font-size: 18px; margin-bottom: 8px;">Empty Prototype Artifact</h2>
                    <p style="color: #8095AC; font-size: 13px; max-width: 480px; margin: 0 auto 16px auto;">
                        The prototype file <code style="color: #4DFFAA; background: #101A2C; padding: 2px 6px; border-radius: 4px;">{path.name}</code> contains 0 bytes.
                    </p>
                    <p style="color: #556B82; font-size: 11px;">MIND is waiting for code synthesis or regeneration.</p>
                </div>
                """
                if HAS_WEBENGINE and self.web_view:
                    self.web_view.setHtml(empty_placeholder)
                elif self.native_browser:
                    self.native_browser.setHtml(empty_placeholder)
                return

            self._last_valid_html = content
            file_url = f"file:///{str(path).replace(os.sep, '/')}"
            self.current_url = file_url

            if HAS_WEBENGINE and self.web_view:
                self.web_view.load(QUrl(file_url))
            elif self.native_browser:
                # Load with base path so styles and images resolve
                self.native_browser.setSearchPaths([str(path.parent)])
                self.native_browser.setHtml(content)

            self._mark_rendered()
            self.append_log(f"Rendered local artifact: {path.name} ({len(content)} bytes)")
        except Exception as e:
            self.show_build_error(f"Error reading {path.name}: {e}")

    def set_html(self, html_content: str, base_url: str = "") -> None:
        """Directly injects HTML string content into the preview canvas."""
        self._last_valid_html = html_content
        if HAS_WEBENGINE and self.web_view:
            self.web_view.setHtml(html_content, QUrl(base_url))
        elif self.native_browser:
            self.native_browser.setHtml(html_content)
        self._mark_rendered()

    def show_welcome_canvas(self) -> None:
        """Displays the MIND Visual Studio welcome canvas on startup or standby."""
        self.current_url = ""
        self.current_file_path = None
        self._last_valid_html = WELCOME_CANVAS_HTML
        if HAS_WEBENGINE and self.web_view:
            self.web_view.setHtml(WELCOME_CANVAS_HTML, QUrl("about:blank"))
        elif self.native_browser:
            self.native_browser.setHtml(WELCOME_CANVAS_HTML)
        self.status_badge.setText("● CANVAS READY")
        self.status_badge.setStyleSheet(
            "color: #4DFFAA; font-family: 'Consolas'; font-size: 10px; font-weight: bold; "
            "background: #0A1E14; border: 1px solid #1A4D30; border-radius: 4px; padding: 3px 8px;"
        )
        self.append_log("Visual workspace online. Ready to render live prototypes.")

    def reload_preview(self) -> None:
        """Reloads the active page."""
        self.status_badge.setText("🔄 RELOADING")
        if HAS_WEBENGINE and self.web_view:
            if self.current_url or (self.current_file_path and self.current_file_path.exists()):
                self.web_view.reload()
            else:
                self.show_welcome_canvas()
        elif self.current_file_path and self.current_file_path.exists():
            self.load_local_file(self.current_file_path)
        elif self.current_url:
            self.load_url(self.current_url)
        else:
            self.show_welcome_canvas()

        QTimer.singleShot(400, self._mark_rendered)
        self.refresh_requested.emit()

    def show_build_error(self, error_message: str) -> None:
        """Displays build warning/error in the console and status badge."""
        self.status_badge.setText("❌ BUILD ERROR")
        self.status_badge.setStyleSheet(
            "color: #FF4D4D; font-family: 'Consolas'; font-size: 10px; font-weight: bold; "
            "background: #2A1015; border: 1px solid #FF4D4D; border-radius: 4px; padding: 3px 8px;"
        )
        self.append_log(f"[ERROR] {error_message}")
        if not self.btn_logs.isChecked():
            self.btn_logs.setChecked(True)

    def append_log(self, message: str) -> None:
        """Appends a timestamped log line to the Dev Logs drawer."""
        import time
        ts = time.strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {message}")

    def _mark_rendered(self) -> None:
        self.status_badge.setText("● LIVE PREVIEW READY")
        self.status_badge.setStyleSheet(
            "color: #4DFFAA; font-family: 'Consolas'; font-size: 10px; font-weight: bold; "
            "background: #0A1E14; border: 1px solid #4DFFAA; border-radius: 4px; padding: 3px 8px;"
        )

    def _open_in_external_browser(self) -> None:
        url = self.current_url
        if not url and self.current_file_path:
            url = f"file:///{str(self.current_file_path).replace(os.sep, '/')}"
        if url:
            webbrowser.open(url)
            self.append_log(f"Dispatched external browser view: {url}")
            self.external_browser_opened.emit(url)

    def _toggle_dev_logs(self, checked: bool) -> None:
        self.logs_drawer.setVisible(checked)
