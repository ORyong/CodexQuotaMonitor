"""Two remaining-quota rings, sharing the client's validated window values."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QFontMetricsF
from .fonts import make_font


def ring_data(state):
    windows = (state.snapshot.primary, state.snapshot.secondary) if state.snapshot else (None, None)
    result = []
    for index, window in enumerate(windows):
        seconds = window.duration_seconds if window else (18000, 604800)[index]
        if seconds == 604800:
            label, short = '一周', '周'
        elif seconds % 86400 == 0:
            label, short = f'{seconds // 86400}天', f'{seconds // 86400}d'
        elif seconds % 3600 == 0:
            label, short = f'{seconds // 3600}小时', f'{seconds // 3600}h'
        else:
            label, short = f'{seconds / 60:g}分钟', f'{seconds / 60:g}m'
        result.append({'label':label, 'short_label':short,
                       'remaining':window.remaining if window else None,
                       'value':window.display if window else '--'})
    return result


def fitted_font(key, value, pixels, max_width, max_height, weight=400):
    font = make_font(key, pixels, weight)
    while font.pixelSize() > 6:
        box = QFontMetricsF(font).tightBoundingRect(value)
        if box.width() <= max_width and box.height() <= max_height:
            break
        font.setPixelSize(font.pixelSize()-1)
    return font


def centered_text(painter, key, value, cx, cy, pixels, max_width, max_height, weight=400):
    font = fitted_font(key, value, pixels, max_width, max_height, weight)
    box = QFontMetricsF(font).tightBoundingRect(value)
    painter.setFont(font)
    # Baseline positioning uses actual ink bounds; a short line rectangle can
    # clip CJK ascenders, percent signs or oblique glyph overhangs.
    painter.drawText(QPointF(cx-box.center().x(), cy-box.center().y()), value)


def draw_rings(painter, settings, state, compact=False):
    data = ring_data(state)
    painter.setRenderHint(painter.RenderHint.TextAntialiasing, True)
    text = QColor(settings.text)
    track = QColor(settings.icon); track.setAlpha(55)
    accent = QColor(settings.icon)
    if compact:
        centers, cy, radius, stroke = (56, 108), 17, 14, 2
    else:
        centers, cy, radius, stroke = (36, 108), 34, 26, 4
    weight = 600 if settings.font == 'noto' else (500 if settings.font == 'source_han_sans' else 400)
    for index, (center, row) in enumerate(zip(centers, data)):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(settings.background))
        outer = radius + (2 if compact else 6)
        painter.drawEllipse(QRectF(center-outer, cy-outer, outer*2, outer*2))
        rect = QRectF(center-radius, cy-radius, radius*2, radius*2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(track, stroke))
        painter.drawEllipse(rect)
        if row['remaining'] is not None and row['remaining'] > 0:
            pen = QPen(accent, stroke); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            if row['remaining'] >= 100:
                painter.drawEllipse(rect)
            else:
                painter.drawArc(rect, 90*16, -round(row['remaining']*360*16/100))
        painter.setPen(text)
        centered_text(painter, settings.font, row['value'], center, cy if compact else cy-6,
                      12 if compact else 17, radius*2-stroke*2, 24 if compact else 22, weight)
        muted = QColor(text); muted.setAlpha(235); painter.setPen(muted)
        if compact:
            centered_text(painter, settings.font, row['short_label'], (31,83)[index], cy, 9, 16, 24)
        else:
            centered_text(painter, settings.font, row['label'], center, cy+12, 11, 42, 16)
    if state.error:
        painter.setBrush(QColor('#F4B860')); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(123 if compact else 134, 1 if compact else 3, 4, 4))
