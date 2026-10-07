"""Vector icons drawn with QPainter.

No binary assets and no icon font, so nothing can go missing when the app is
packaged. Every icon is a thin line drawing on a transparent pixmap.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap

from ..theme import BASE_FONT

_CACHE: dict[tuple, QPixmap] = {}


def _pen(color: QColor, size: float, factor: float = 0.075) -> QPen:
    pen = QPen(color, max(1.3, size * factor))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    return pixmap, painter


# --------------------------------------------------------------------------
# painters
# --------------------------------------------------------------------------
def _p_dashboard(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.055))
    gap = s * 0.10
    half = (s - gap) / 2
    p.drawRoundedRect(QRectF(0.06 * s, 0.06 * s, half, half * 0.78), 2, 2)
    p.drawRoundedRect(
        QRectF(0.06 * s + half + gap, 0.06 * s, half, half * 1.18), 2, 2
    )
    p.drawRoundedRect(
        QRectF(0.06 * s, 0.06 * s + half * 0.78 + gap, half, half * 1.18), 2, 2
    )
    p.drawRoundedRect(
        QRectF(0.06 * s + half + gap, 0.06 * s + half * 1.18 + gap, half,
               half * 0.78),
        2, 2,
    )


def _p_chat(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    body = QRectF(0.09 * s, 0.14 * s, 0.82 * s, 0.54 * s)
    p.drawRoundedRect(body, s * 0.14, s * 0.14)
    path = QPainterPath()
    path.moveTo(0.28 * s, 0.66 * s)
    path.lineTo(0.28 * s, 0.86 * s)
    path.lineTo(0.46 * s, 0.66 * s)
    p.drawPath(path)


def _p_mic(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    w = 0.30 * s
    p.drawRoundedRect(
        QRectF((s - w) / 2, 0.10 * s, w, 0.38 * s), w / 2, w / 2
    )
    arc = QRectF(0.24 * s, 0.42 * s, 0.52 * s, 0.36 * s)
    path = QPainterPath()
    path.arcMoveTo(arc, 180)
    path.arcTo(arc, 180, -180)
    p.drawPath(path)
    p.drawLine(QPointF(s / 2, 0.78 * s), QPointF(s / 2, 0.86 * s))
    p.drawLine(QPointF(0.36 * s, 0.86 * s), QPointF(0.64 * s, 0.86 * s))


def _p_news(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.065))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.10 * s, 0.16 * s, 0.80 * s, 0.68 * s),
                      s * 0.06, s * 0.06)
    for i, y in enumerate((0.32, 0.46, 0.60)):
        width = 0.58 if i != 1 else 0.44
        p.drawLine(QPointF(0.21 * s, y * s),
                   QPointF((0.21 + width) * s, y * s))
    p.drawLine(QPointF(0.21 * s, 0.73 * s), QPointF(0.50 * s, 0.73 * s))


def _p_music(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(0.10 * s, 0.64 * s, 0.28 * s, 0.24 * s))
    p.drawEllipse(QRectF(0.52 * s, 0.58 * s, 0.28 * s, 0.24 * s))
    p.drawLine(QPointF(0.38 * s, 0.66 * s), QPointF(0.38 * s, 0.16 * s))
    p.drawLine(QPointF(0.80 * s, 0.60 * s), QPointF(0.80 * s, 0.12 * s))
    p.drawLine(QPointF(0.38 * s, 0.16 * s), QPointF(0.80 * s, 0.12 * s))


def _p_settings(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    cx = cy = s / 2
    r_out, r_in = s * 0.44, s * 0.33
    teeth = 8
    step = 2 * math.pi / teeth
    path = QPainterPath()
    for i in range(teeth):
        base = i * step - math.pi / 2
        for offset, radius in (
            (-0.5 * step, r_in),
            (-0.28 * step, r_out),
            (0.28 * step, r_out),
            (0.5 * step, r_in),
        ):
            angle = base + offset
            pt = QPointF(cx + radius * math.cos(angle),
                         cy + radius * math.sin(angle))
            if i == 0 and offset == -0.5 * step:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
    path.closeSubpath()
    path.addEllipse(QPointF(cx, cy), s * 0.15, s * 0.15)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    p.drawPath(path)


def _p_send(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.08))
    p.drawLine(QPointF(0.14 * s, s / 2), QPointF(0.82 * s, s / 2))
    path = QPainterPath()
    path.moveTo(0.58 * s, 0.30 * s)
    path.lineTo(0.84 * s, 0.50 * s)
    path.lineTo(0.58 * s, 0.70 * s)
    p.drawPath(path)


def _p_refresh(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    rect = QRectF(0.14 * s, 0.14 * s, 0.72 * s, 0.72 * s)
    path = QPainterPath()
    path.arcMoveTo(rect, 55)
    path.arcTo(rect, 55, -280)
    p.drawPath(path)
    tip = path.currentPosition()
    head = QPainterPath()
    head.moveTo(tip.x() - s * 0.14, tip.y() - s * 0.04)
    head.lineTo(tip.x(), tip.y())
    head.lineTo(tip.x() - s * 0.02, tip.y() + s * 0.15)
    p.drawPath(head)


def _p_play(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    path = QPainterPath()
    path.moveTo(0.30 * s, 0.20 * s)
    path.lineTo(0.80 * s, 0.50 * s)
    path.lineTo(0.30 * s, 0.80 * s)
    path.closeSubpath()
    p.drawPath(path)


def _p_pause(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(QRectF(0.26 * s, 0.20 * s, 0.16 * s, 0.60 * s),
                      2, 2)
    p.drawRoundedRect(QRectF(0.58 * s, 0.20 * s, 0.16 * s, 0.60 * s),
                      2, 2)


def _p_stop(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(QRectF(0.26 * s, 0.26 * s, 0.48 * s, 0.48 * s),
                      3, 3)


def _p_prev(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRect(QRectF(0.22 * s, 0.24 * s, 0.10 * s, 0.52 * s))
    path = QPainterPath()
    path.moveTo(0.78 * s, 0.24 * s)
    path.lineTo(0.36 * s, 0.50 * s)
    path.lineTo(0.78 * s, 0.76 * s)
    path.closeSubpath()
    p.drawPath(path)


def _p_next(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRect(QRectF(0.68 * s, 0.24 * s, 0.10 * s, 0.52 * s))
    path = QPainterPath()
    path.moveTo(0.22 * s, 0.24 * s)
    path.lineTo(0.64 * s, 0.50 * s)
    path.lineTo(0.22 * s, 0.76 * s)
    path.closeSubpath()
    p.drawPath(path)


def _p_external(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.12 * s, 0.30 * s, 0.52 * s, 0.52 * s),
                      s * 0.07, s * 0.07)
    p.drawLine(QPointF(0.40 * s, 0.58 * s), QPointF(0.82 * s, 0.16 * s))
    p.drawLine(QPointF(0.62 * s, 0.16 * s), QPointF(0.84 * s, 0.16 * s))
    p.drawLine(QPointF(0.84 * s, 0.16 * s), QPointF(0.84 * s, 0.38 * s))


def _p_trash(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(0.16 * s, 0.26 * s), QPointF(0.84 * s, 0.26 * s))
    p.drawLine(QPointF(0.38 * s, 0.26 * s), QPointF(0.42 * s, 0.16 * s))
    p.drawLine(QPointF(0.58 * s, 0.26 * s), QPointF(0.54 * s, 0.16 * s))
    path = QPainterPath()
    path.moveTo(0.24 * s, 0.26 * s)
    path.lineTo(0.30 * s, 0.84 * s)
    path.lineTo(0.70 * s, 0.84 * s)
    path.lineTo(0.76 * s, 0.26 * s)
    p.drawPath(path)
    p.drawLine(QPointF(0.43 * s, 0.40 * s), QPointF(0.43 * s, 0.70 * s))
    p.drawLine(QPointF(0.57 * s, 0.40 * s), QPointF(0.57 * s, 0.70 * s))


def _p_volume(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(0.14 * s, 0.40 * s)
    path.lineTo(0.30 * s, 0.40 * s)
    path.lineTo(0.48 * s, 0.22 * s)
    path.lineTo(0.48 * s, 0.78 * s)
    path.lineTo(0.30 * s, 0.60 * s)
    path.lineTo(0.14 * s, 0.60 * s)
    path.closeSubpath()
    p.drawPath(path)
    for radius in (0.16, 0.28):
        arc = QRectF(0.50 * s - radius * s, 0.50 * s - radius * s,
                     2 * radius * s, 2 * radius * s)
        arc_path = QPainterPath()
        arc_path.arcMoveTo(arc, -55)
        arc_path.arcTo(arc, -55, 110)
        p.drawPath(arc_path)


def _p_minimize(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.09))
    p.drawLine(QPointF(0.24 * s, 0.52 * s), QPointF(0.76 * s, 0.52 * s))


def _p_maximize(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.09))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(0.27 * s, 0.27 * s, 0.46 * s, 0.46 * s))


def _p_restore(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.09))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(0.36 * s, 0.24 * s, 0.40 * s, 0.40 * s))
    p.drawRect(QRectF(0.24 * s, 0.36 * s, 0.40 * s, 0.40 * s))


def _p_close(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.09))
    p.drawLine(QPointF(0.30 * s, 0.30 * s), QPointF(0.70 * s, 0.70 * s))
    p.drawLine(QPointF(0.70 * s, 0.30 * s), QPointF(0.30 * s, 0.70 * s))


def _p_check(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.09))
    path = QPainterPath()
    path.moveTo(0.22 * s, 0.52 * s)
    path.lineTo(0.42 * s, 0.72 * s)
    path.lineTo(0.78 * s, 0.28 * s)
    p.drawPath(path)


def _p_alert(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.08))
    p.drawLine(QPointF(0.50 * s, 0.22 * s), QPointF(0.50 * s, 0.56 * s))
    p.setBrush(col)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(0.50 * s, 0.74 * s), s * 0.06, s * 0.06)


def _p_power(p: QPainter, s: float, col: QColor) -> None:
    p.setPen(_pen(col, s, 0.08))
    arc = QRectF(0.20 * s, 0.20 * s, 0.60 * s, 0.60 * s)
    path = QPainterPath()
    path.arcMoveTo(arc, -60)
    path.arcTo(arc, -60, 300)
    p.drawPath(path)
    p.drawLine(QPointF(0.50 * s, 0.14 * s), QPointF(0.50 * s, 0.46 * s))


_PAINTERS = {
    "dashboard": _p_dashboard,
    "chat": _p_chat,
    "mic": _p_mic,
    "news": _p_news,
    "music": _p_music,
    "settings": _p_settings,
    "send": _p_send,
    "refresh": _p_refresh,
    "play": _p_play,
    "pause": _p_pause,
    "stop": _p_stop,
    "prev": _p_prev,
    "next": _p_next,
    "external": _p_external,
    "trash": _p_trash,
    "volume": _p_volume,
    "minimize": _p_minimize,
    "maximize": _p_maximize,
    "restore": _p_restore,
    "close": _p_close,
    "check": _p_check,
    "alert": _p_alert,
    "power": _p_power,
}


def icon(name: str, color: str, size: int = 20) -> QPixmap:
    """A line icon rendered at ``size`` px in ``color``."""
    key = (name, color, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    pixmap, painter = _canvas(size)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(QColor(color), size))
    painter_fn = _PAINTERS.get(name)
    if painter_fn is not None:
        painter_fn(painter, float(size), QColor(color))
    painter.end()

    _CACHE[key] = pixmap
    return pixmap


def logo(size: int = 40, accent: str = "#4FD1FF") -> QPixmap:
    """The MERLIN mark: a soft-gradient tile with an 'M' cut into it."""
    key = ("logo", accent, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    pixmap, painter = _canvas(size)
    rect = QRectF(1, 1, size - 2, size - 2)

    from PySide6.QtGui import QBrush, QLinearGradient

    gradient = QRectF(rect)
    grad = QLinearGradient(gradient.topLeft(), gradient.bottomRight())
    grad.setColorAt(0.0, QColor(accent))
    grad.setColorAt(1.0, QColor("#7C6CFF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRoundedRect(rect, size * 0.28, size * 0.28)

    painter.setPen(QColor("#04121B"))
    font = QFont(BASE_FONT)
    font.setPixelSize(int(size * 0.58))
    font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "M")
    painter.end()

    _CACHE[key] = pixmap
    return pixmap
