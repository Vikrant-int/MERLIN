"""The MERLIN assistant core: one widget, six states, one timer.

Animation is a single 30 fps timer driving a float phase, so every state is
purely a function of that phase. Nothing here blocks, and the timer stops
entirely when the widget is hidden or when the system asks for reduced
motion, so an idle window costs nothing.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ..theme import BASE_FONT, prefers_reduced_motion

IDLE = "IDLE"
LISTENING = "LISTENING"
THINKING = "THINKING"
SPEAKING = "SPEAKING"
ERROR = "ERROR"
OFFLINE = "OFFLINE"

STATES = (IDLE, LISTENING, THINKING, SPEAKING, ERROR, OFFLINE)

_STATE_COLOR = {
    IDLE: "#4FD1FF",
    LISTENING: "#5B8CFF",
    THINKING: "#7C6CFF",
    SPEAKING: "#4FD1FF",
    ERROR: "#FF6B7A",
    OFFLINE: "#6B7488",
}


def _mix(base: str, other: str, amount: float) -> QColor:
    a = QColor(base)
    b = QColor(other)
    amount = max(0.0, min(1.0, amount))
    return QColor(
        int(a.red() + (b.red() - a.red()) * amount),
        int(a.green() + (b.green() - a.green()) * amount),
        int(a.blue() + (b.blue() - a.blue()) * amount),
    )


class AssistantCore(QWidget):
    """Status orb for the Dashboard and Voice pages."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = IDLE
        self._phase = 0.0
        self._reduced = prefers_reduced_motion()
        self.setMinimumSize(200, 200)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- public ------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in _STATE_COLOR:
            state = IDLE
        if state != self._state:
            self._state = state
            self.update()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced = bool(value)
        self._apply_timer()
        self.update()

    # -- lifecycle ---------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _apply_timer(self) -> None:
        if self.isVisible() and not self._reduced:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    # -- animation ---------------------------------------------------------
    def _tick(self) -> None:
        self._phase = (self._phase + 0.033) % 1000.0
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2, h / 2
        base = min(w, h) / 2 - 14
        t = self._phase if not self._reduced else 0.0
        colour = QColor(_STATE_COLOR[self._state])

        self._paint_backdrop(painter, cx, cy, base, t, colour)
        self._paint_state(painter, cx, cy, base, t, colour)
        self._paint_core(painter, cx, cy, base, t, colour)
        self._paint_label(painter, cx, cy, base, colour)
        painter.end()

    # -- layers ------------------------------------------------------------
    def _paint_backdrop(self, p: QPainter, cx, cy, base, t, colour) -> None:
        if self._state == OFFLINE:
            return
        breath = 1.0 if self._state == IDLE else 1.06
        if self._state == IDLE:
            breath = 1.0 + 0.10 * math.sin(t * 1.15)
        radius = base * (1.18 + 0.05 * breath)

        glow = QRadialGradient(cx, cy, radius)
        alpha = 60 if self._state != ERROR else 70
        if self._state == THINKING:
            alpha = 66
        glow.setColorAt(0.0, QColor(colour.red(), colour.green(),
                                    colour.blue(), alpha))
        glow.setColorAt(0.55, QColor(colour.red(), colour.green(),
                                     colour.blue(), int(alpha * 0.35)))
        glow.setColorAt(1.0, QColor(colour.red(), colour.green(),
                                    colour.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

    def _paint_state(self, p: QPainter, cx, cy, base, t, colour) -> None:
        state = self._state

        if state == LISTENING:
            # Soft rings expanding outward from the core.
            for i in range(3):
                progress = (t * 0.55 + i / 3.0) % 1.0
                radius = base * (0.72 + progress * 0.72)
                fade = (1.0 - progress) ** 1.6
                pen = QPen(_mix(colour, _STATE_COLOR[LISTENING], 1.0), 2.0)
                pen.setColor(QColor(colour.red(), colour.green(),
                                    colour.blue(), int(150 * fade)))
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), radius, radius)

        elif state == THINKING:
            # Three arcs drifting at different speeds: a flowing indicator.
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i, (start, span, thick, speed) in enumerate(
                ((0, 95, 3.0, 1.55), (120, 70, 2.4, -1.05), (240, 55, 2.0, 2.1))
            ):
                radius = base * (0.80 + i * 0.13)
                gradient = QConicalGradient(cx, cy, start + t * 260 * speed)
                gradient.setColorAt(0.0, QColor(colour.red(), colour.green(),
                                                colour.blue(), 235))
                gradient.setColorAt(0.55, QColor(colour.red(), colour.green(),
                                                 colour.blue(), 60))
                gradient.setColorAt(1.0, QColor(colour.red(), colour.green(),
                                                colour.blue(), 0))
                pen = QPen(gradient, thick)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(
                    QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
                    int((start + t * 260 * speed) * 16),
                    int(span * 16),
                )

        elif state == SPEAKING:
            # Ripples emitted on a steady beat, plus a quick core pulse.
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(3):
                progress = (t * 2.1 + i / 3.0) % 1.0
                radius = base * (0.70 + progress * 0.62)
                fade = (1.0 - progress) ** 1.5
                pen = QPen(QColor(colour.red(), colour.green(),
                                  colour.blue(), int(170 * fade)), 2.4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawEllipse(QPointF(cx, cy), radius, radius)

        elif state == ERROR:
            p.setBrush(Qt.BrushStyle.NoBrush)
            pulse = 0.5 + 0.5 * math.sin(t * 2.2)
            pen = QPen(QColor(255, 107, 122, int(90 + 90 * pulse)), 2.0)
            p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), base * 1.06, base * 1.06)

        elif state == OFFLINE:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(107, 116, 136, 90), 1.4))
            p.drawEllipse(QPointF(cx, cy), base * 1.06, base * 1.06)

        else:  # IDLE -- a faint static orbit to give the core some depth
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
            p.drawEllipse(QPointF(cx, cy), base * 1.16, base * 1.16)

    def _paint_core(self, p: QPainter, cx, cy, base, t, colour) -> None:
        radius = base * 0.66

        if self._state == IDLE:
            radius *= 1.0 + 0.035 * math.sin(t * 1.15)
        elif self._state == SPEAKING:
            radius *= 1.0 + 0.045 * abs(math.sin(t * 7.0))
        elif self._state == LISTENING:
            radius *= 1.0 + 0.030 * (0.5 + 0.5 * math.sin(t * 3.4))
        elif self._state == OFFLINE:
            radius *= 0.96

        if self._state == OFFLINE:
            top = QColor("#1A1F2B")
            bottom = QColor("#11151D")
        else:
            top = _mix(colour, "#FFFFFF", 0.32)
            bottom = _mix(colour, _STATE_COLOR[self._state], 0.0)

        gradient = QLinearGradient(cx - radius, cy - radius,
                                   cx + radius, cy + radius)
        if self._state == ERROR:
            top = _mix("#FF6B7A", "#FFFFFF", 0.28)
            bottom = QColor("#8E2A36")
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Inner highlight, kept subtle so the core reads as glass not neon.
        inner = QRadialGradient(cx - radius * 0.3, cy - radius * 0.35,
                                radius * 0.95)
        inner.setColorAt(0.0, QColor(255, 255, 255, 70))
        inner.setColorAt(0.6, QColor(255, 255, 255, 8))
        inner.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(inner)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Thin rim.
        rim_alpha = 110 if self._state != OFFLINE else 50
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, rim_alpha), 1.2))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        if self._state == ERROR:
            self._paint_mark(p, cx, cy, radius)

    def _paint_mark(self, p: QPainter, cx, cy, radius) -> None:
        pen = QPen(QColor("#FFE7EA"), max(2.6, radius * 0.13))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy - radius * 0.40),
                   QPointF(cx, cy + radius * 0.05))
        p.setBrush(QColor("#FFE7EA"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy + radius * 0.40),
                      radius * 0.085, radius * 0.085)

    def _paint_label(self, p: QPainter, cx, cy, base, colour) -> None:
        if self._state == OFFLINE:
            text = "OFFLINE"
        elif self._state == ERROR:
            text = "ERROR"
        else:
            return
        font = QFont(BASE_FONT)
        font.setPixelSize(max(10, int(base * 0.17)))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(colour))
        rect = QRectF(cx - base, cy + base * 0.86, base * 2, base * 0.4)
        p.drawText(rect, Qt.AlignmentFlag.AlignHCenter, text)
