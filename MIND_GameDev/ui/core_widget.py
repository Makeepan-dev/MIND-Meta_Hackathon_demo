"""
MIND Universal Studio — Meta Hackathon Edition
JARVIS-Inspired Animated Circular AI Core Widget.

Implements a multi-layered, state-reactive holographic HUD:
- Concentric technical rings with tick marks, degree indicators, and crosshairs
- Outer orbital segmented arcs rotating at differential velocities
- Central luminous pulsating energy sphere
- Orbiting subsystem nodes (Brain, Code, Voice, Models, Security)
- Real-time reactive state animation (IDLE, LISTENING, THINKING, GENERATING, SPEAKING, ERROR)
"""

from __future__ import annotations

import math
import time
from enum import Enum
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QRadialGradient,
    QFont,
    QPainterPath,
)
from PyQt6.QtWidgets import QWidget

from .theme import MindPalette


class CoreState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    GENERATING = "GENERATING"
    SPEAKING = "SPEAKING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class JarvisAICoreWidget(QWidget):
    """
    High-performance QPainter widget rendering the holographic circular JARVIS reactor core.
    """

    def __init__(self, parent: Optional[QWidget] = None, reduced_motion: bool = False) -> None:
        super().__init__(parent)
        self.reduced_motion = reduced_motion
        self.state = CoreState.IDLE
        self.status_text = "SYSTEM STANDBY"
        self.active_subsystem = "CORTEX ONLINE"
        self.progress_value = 0.0  # 0.0 to 1.0 for GENERATING

        # Animation state angles (in degrees)
        self.angle_outer = 0.0
        self.angle_mid = 0.0
        self.angle_inner = 0.0
        self.angle_ticks = 0.0
        self.pulse_phase = 0.0
        self.waveform_phase = 0.0

        # Subsystems to display on the orbit ring
        self.subsystems = [
            ("BRAIN", "#00F5FF"),
            ("CODE", "#397BFF"),
            ("STUDIO", "#8B5CFF"),
            ("VOICE", "#4DFFAA"),
            ("SHIELD", "#00F5FF"),
        ]

        # 60 FPS animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance_animation)
        self.timer.start(16)

        self.setMinimumSize(320, 320)

    def set_state(self, state: CoreState, status_text: Optional[str] = None) -> None:
        """Updates the core reactor state and HUD label."""
        self.state = state
        if status_text:
            self.status_text = status_text.upper()
        self.update()

    def set_progress(self, progress: float) -> None:
        """Sets task progress (0.0 to 1.0) when state == GENERATING."""
        self.progress_value = max(0.0, min(1.0, progress))
        self.update()

    def set_active_subsystem(self, text: str) -> None:
        self.active_subsystem = text.upper()
        self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = enabled
        if self.reduced_motion:
            self.timer.setInterval(40)  # Drop to 25 FPS
        else:
            self.timer.setInterval(16)  # 60 FPS

    def _advance_animation(self) -> None:
        """Increments rotation and pulse phases according to current core state."""
        if self.reduced_motion:
            speed_mult = 0.3
        else:
            speed_mult = 1.0

        if self.state == CoreState.THINKING:
            speed_mult *= 3.0
        elif self.state == CoreState.GENERATING:
            speed_mult *= 2.2
        elif self.state == CoreState.LISTENING:
            speed_mult *= 1.5
        elif self.state == CoreState.ERROR:
            speed_mult *= 0.2

        # Rotate layers in alternating directions
        self.angle_outer = (self.angle_outer + 0.45 * speed_mult) % 360.0
        self.angle_mid = (self.angle_mid - 0.70 * speed_mult) % 360.0
        self.angle_inner = (self.angle_inner + 1.10 * speed_mult) % 360.0
        self.angle_ticks = (self.angle_ticks - 0.25 * speed_mult) % 360.0

        # Breathing / pulsating energy phase
        pulse_speed = 0.05 * (2.5 if self.state in (CoreState.LISTENING, CoreState.THINKING) else 1.0)
        self.pulse_phase = (self.pulse_phase + pulse_speed) % (2 * math.pi)
        self.waveform_phase = (self.waveform_phase + 0.12) % (2 * math.pi)

        self.update()

    def paintEvent(self, event) -> None:
        """Renders the holographic JARVIS circular reactor HUD."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        center_x = w / 2.0
        center_y = h / 2.0
        max_radius = min(w, h) / 2.0 - 15.0

        if max_radius < 50:
            return

        # 1. Background radial glow
        self._draw_ambient_glow(painter, center_x, center_y, max_radius)

        # 2. Outer Technical Coordinate Ring
        self._draw_outer_tech_ring(painter, center_x, center_y, max_radius * 0.96)

        # 3. Rotating Segmented Outer Arcs
        self._draw_segmented_arcs(painter, center_x, center_y, max_radius * 0.86)

        # 4. Technical Tick Marks and Crosshairs
        self._draw_tick_marks(painter, center_x, center_y, max_radius * 0.75)

        # 5. Orbiting Subsystems Nodes
        self._draw_orbiting_nodes(painter, center_x, center_y, max_radius * 0.65)

        # 6. Inner Dashed Gyro Ring
        self._draw_inner_gyro_ring(painter, center_x, center_y, max_radius * 0.52)

        # 7. Central Glowing Energy Core & Waveform
        self._draw_central_core(painter, center_x, center_y, max_radius * 0.38)

        # 8. HUD Center Text Overlay
        self._draw_hud_text(painter, center_x, center_y, max_radius * 0.38)

    def _draw_ambient_glow(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Soft radial ambient illumination."""
        grad = QRadialGradient(cx, cy, r)
        glow_alpha = int(35 + 20 * math.sin(self.pulse_phase))
        
        if self.state == CoreState.ERROR:
            grad.setColorAt(0.0, QColor(255, 85, 119, glow_alpha))
            grad.setColorAt(0.7, QColor(255, 85, 119, int(glow_alpha * 0.3)))
        elif self.state == CoreState.GENERATING:
            grad.setColorAt(0.0, QColor(139, 92, 255, glow_alpha))
            grad.setColorAt(0.7, QColor(0, 245, 255, int(glow_alpha * 0.3)))
        elif self.state == CoreState.LISTENING:
            grad.setColorAt(0.0, QColor(77, 255, 170, glow_alpha))
            grad.setColorAt(0.7, QColor(0, 245, 255, int(glow_alpha * 0.3)))
        else:
            grad.setColorAt(0.0, QColor(0, 245, 255, glow_alpha))
            grad.setColorAt(0.6, QColor(57, 123, 255, int(glow_alpha * 0.25)))
            
        grad.setColorAt(1.0, QColor(5, 8, 17, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_outer_tech_ring(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Thin outer perimeter with bracket accents."""
        pen = QPen(QColor(27, 42, 71, 180), 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Four corner brackets / reticles
        reticle_pen = QPen(QColor(0, 245, 255, 140), 1.5)
        p.setPen(reticle_pen)
        bracket_len = 16.0
        
        for deg in (0, 90, 180, 270):
            rad = math.radians(deg + self.angle_ticks * 0.2)
            px = cx + r * math.cos(rad)
            py = cy + r * math.sin(rad)
            p.drawPoint(QPointF(px, py))
            # Cross marks
            p.drawLine(QPointF(px - 4, py), QPointF(px + 4, py))
            p.drawLine(QPointF(px, py - 4), QPointF(px, py + 4))

    def _draw_segmented_arcs(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Differential rotating arc segments with varying line widths."""
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        # Primary cyan segmented arc
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen_cyan = QPen(QColor(0, 245, 255, 220), 2.5)
        pen_cyan.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_cyan)
        
        # Arc 1: 80 degrees
        start_angle_1 = int((self.angle_outer * 16))
        p.drawArc(rect, start_angle_1, 80 * 16)
        
        # Arc 2: 120 degrees opposite
        p.drawArc(rect, start_angle_1 + 180 * 16, 70 * 16)

        # Electric blue counter-rotating secondary arcs
        pen_blue = QPen(QColor(57, 123, 255, 160), 1.5)
        p.setPen(pen_blue)
        start_angle_2 = int((self.angle_mid * 16))
        p.drawArc(rect, start_angle_2 + 90 * 16, 45 * 16)
        p.drawArc(rect, start_angle_2 + 270 * 16, 45 * 16)

        # Generating progress ring overlay
        if self.state == CoreState.GENERATING and self.progress_value > 0.0:
            pen_prog = QPen(QColor(77, 255, 170, 240), 4.0)
            pen_prog.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_prog)
            span_angle = int(self.progress_value * 360 * 16)
            p.drawArc(rect, 90 * 16, -span_angle)

    def _draw_tick_marks(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Radial technical tick marks around the ring."""
        num_ticks = 48
        p.setBrush(Qt.BrushStyle.NoBrush)
        
        for i in range(num_ticks):
            deg = (i * (360.0 / num_ticks) + self.angle_ticks) % 360.0
            rad = math.radians(deg)
            is_major = (i % 6 == 0)
            tick_len = 8.0 if is_major else 4.0
            
            if is_major:
                p.setPen(QPen(QColor(0, 245, 255, 190), 1.5))
            else:
                p.setPen(QPen(QColor(27, 42, 71, 140), 1.0))
                
            x1 = cx + (r - tick_len) * math.cos(rad)
            y1 = cy + (r - tick_len) * math.sin(rad)
            x2 = cx + r * math.cos(rad)
            y2 = cy + r * math.sin(rad)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_orbiting_nodes(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Satellite orbital nodes representing MIND subsystems."""
        num_nodes = len(self.subsystems)
        font = QFont("Consolas", 7, QFont.Weight.Bold)
        p.setFont(font)

        for i, (name, color_hex) in enumerate(self.subsystems):
            angle_offset = i * (360.0 / num_nodes)
            deg = (self.angle_mid + angle_offset) % 360.0
            rad = math.radians(deg)
            
            node_x = cx + r * math.cos(rad)
            node_y = cy + r * math.sin(rad)
            
            # Draw glowing node dot
            c = QColor(color_hex)
            p.setPen(QPen(c, 1.0))
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(node_x, node_y), 3.5, 3.5)

            # Node label
            p.setPen(QColor(128, 149, 172, 180))
            p.drawText(int(node_x + 6), int(node_y + 3), name)

    def _draw_inner_gyro_ring(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Dashed technical inner ring rotating opposite outer ring."""
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        pen = QPen(QColor(0, 245, 255, 120), 1.2, Qt.PenStyle.DashLine)
        pen.setDashPattern([3, 5])
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # Crosshair lines through the center
        p.setPen(QPen(QColor(27, 42, 71, 120), 1.0))
        p.drawLine(QPointF(cx - r * 0.9, cy), QPointF(cx - r * 0.4, cy))
        p.drawLine(QPointF(cx + r * 0.4, cy), QPointF(cx + r * 0.9, cy))
        p.drawLine(QPointF(cx, cy - r * 0.9), QPointF(cx, cy - r * 0.4))
        p.drawLine(QPointF(cx, cy + r * 0.4), QPointF(cx, cy + r * 0.9))

    def _draw_central_core(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """Pulsating reactor core with reactive waveform."""
        # Modulate radius with pulse phase
        pulse_scale = 1.0 + 0.08 * math.sin(self.pulse_phase)
        active_r = r * pulse_scale

        grad = QRadialGradient(cx, cy, active_r)
        
        if self.state == CoreState.ERROR:
            grad.setColorAt(0.0, QColor(255, 85, 119, 230))
            grad.setColorAt(0.5, QColor(255, 85, 119, 140))
            grad.setColorAt(1.0, QColor(5, 8, 17, 0))
        elif self.state == CoreState.LISTENING:
            grad.setColorAt(0.0, QColor(77, 255, 170, 240))
            grad.setColorAt(0.5, QColor(0, 245, 255, 150))
            grad.setColorAt(1.0, QColor(5, 8, 17, 0))
        elif self.state == CoreState.THINKING:
            grad.setColorAt(0.0, QColor(0, 245, 255, 255))
            grad.setColorAt(0.5, QColor(139, 92, 255, 180))
            grad.setColorAt(1.0, QColor(5, 8, 17, 0))
        elif self.state == CoreState.GENERATING:
            grad.setColorAt(0.0, QColor(139, 92, 255, 240))
            grad.setColorAt(0.6, QColor(57, 123, 255, 150))
            grad.setColorAt(1.0, QColor(5, 8, 17, 0))
        else:  # IDLE / CONNECTED
            grad.setColorAt(0.0, QColor(0, 245, 255, 210))
            grad.setColorAt(0.5, QColor(57, 123, 255, 120))
            grad.setColorAt(1.0, QColor(5, 8, 17, 0))

        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), active_r, active_r)

        # Waveform bars when SPEAKING or LISTENING
        if self.state in (CoreState.SPEAKING, CoreState.LISTENING, CoreState.THINKING):
            self._draw_reactive_waveform(p, cx, cy, r * 0.7)

    def _draw_reactive_waveform(self, p: QPainter, cx: float, cy: float, max_w: float) -> None:
        """Simulated reactive audio frequency bars centered in the core."""
        num_bars = 16
        bar_w = 2.5
        spacing = 3.5
        total_w = num_bars * (bar_w + spacing)
        start_x = cx - total_w / 2.0

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(num_bars):
            dist_from_center = abs(i - num_bars / 2.0) / (num_bars / 2.0)
            amp = math.sin(self.waveform_phase + i * 0.4) * 0.5 + 0.5
            bar_h = (1.0 - dist_from_center * 0.5) * amp * 22.0 + 4.0
            
            bx = start_x + i * (bar_w + spacing)
            by = cy - bar_h / 2.0
            
            c = QColor(0, 245, 255, int(180 + 70 * amp))
            p.setBrush(QBrush(c))
            p.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), 1.0, 1.0)

    def _draw_hud_text(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        """HUD status badges and text indicators below and above core."""
        # Top title: MIND CORTEX
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor(0, 245, 255, 220))
        title = "MIND // JARVIS CORE"
        p.drawText(QRectF(cx - 100, cy - r - 26, 200, 20), Qt.AlignmentFlag.AlignCenter, title)

        # Bottom status pill
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        status_color = QColor(0, 245, 255)
        if self.state == CoreState.ERROR:
            status_color = QColor(255, 85, 119)
        elif self.state == CoreState.LISTENING:
            status_color = QColor(77, 255, 170)
        elif self.state == CoreState.GENERATING:
            status_color = QColor(139, 92, 255)

        p.setPen(status_color)
        p.drawText(QRectF(cx - 120, cy + r + 10, 240, 20), Qt.AlignmentFlag.AlignCenter, f"● {self.status_text}")

        # Subtitle
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(128, 149, 172, 200))
        p.drawText(QRectF(cx - 120, cy + r + 28, 240, 18), Qt.AlignmentFlag.AlignCenter, self.active_subsystem)
