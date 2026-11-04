"""
Unit tests for MIND Desktop Application GUI, Core Widget, and BackendBridge.
Verifies JARVIS Circular Core states, view transitions, credential safety, and worker signals.
"""

import os
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from MIND_GameDev.ui.core_widget import JarvisAICoreWidget, CoreState
from MIND_GameDev.ui.theme import MindPalette
from MIND_GameDev.ui.backend_bridge import BackendBridge, AIWorker, DevStudioWorker
from MIND_GameDev.ui.main_window import MINDMainWindow
from MIND_GameDev.ui.views.chat_view import ChatView
from MIND_GameDev.ui.views.studio_view import StudioView


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_jarvis_core_widget_states(qapp):
    widget = JarvisAICoreWidget()
    assert widget.state == CoreState.IDLE
    assert widget.status_text == "SYSTEM STANDBY"

    widget.set_state(CoreState.THINKING, "NEURAL SYNTHESIS")
    assert widget.state == CoreState.THINKING
    assert widget.status_text == "NEURAL SYNTHESIS"

    widget.set_state(CoreState.GENERATING, "CODE SYNTHESIS")
    widget.set_progress(0.75)
    assert widget.state == CoreState.GENERATING
    assert widget.progress_value == 0.75

    widget.set_state(CoreState.ERROR, "FAULT DETECTED")
    assert widget.state == CoreState.ERROR


def test_jarvis_core_reduced_motion(qapp):
    widget = JarvisAICoreWidget()
    assert widget.reduced_motion is False
    assert widget.timer.interval() == 16

    widget.set_reduced_motion(True)
    assert widget.reduced_motion is True
    assert widget.timer.interval() == 40


def test_backend_bridge_credential_redaction(qapp):
    bridge = BackendBridge()
    providers = bridge.get_configured_providers()
    assert len(providers) >= 5

    for p in providers:
        key = p.get("key_masked", "")
        # Assert secret is redacted and contains masking ellipsis or N/A
        if p.get("configured") and p.get("name") != "Ollama Local":
            assert "..." in key or "N/A" in key
            # Ensure full raw key from env is never exposed directly
            raw_groq = os.getenv("GROQ_API_KEY", "")
            raw_or = os.getenv("OPENROUTER_API_KEY", "")
            if raw_groq:
                assert key != raw_groq
            if raw_or:
                assert key != raw_or


def test_main_window_navigation(qapp):
    win = MINDMainWindow()
    assert win.stack.count() == 7

    # Navigate to each tab and verify
    for i in range(7):
        win.set_active_view(i)
        assert win.stack.currentIndex() == i
        assert win.nav_buttons[i].isChecked() is True


def test_chat_view_message_handling(qapp):
    view = ChatView()
    initial_count = view.messages_layout.count()

    view.add_message("USER", "Test prompt", is_user=True)
    assert view.messages_layout.count() == initial_count + 1

    view.add_message("MIND", "Test response", model_tag="Groq", is_user=False)
    assert view.messages_layout.count() == initial_count + 2

    view._clear_chat()
    assert view.messages_layout.count() == 1  # Only bottom stretch remaining


def test_studio_view_progress_and_logs(qapp):
    view = StudioView()
    view.append_log("Test step initialized")
    assert "Test step initialized" in view.log_text.toPlainText()

    view.update_progress("Synthesizing HTML", 0.5)
    assert view.progress_bar.value() == 50
