"""Two remaining-quota rings, sharing the client's validated window values."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
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


def draw_rings(painter, settings, state, compact=False):
    data = ring_data(state)
    text = QColor(settings.text)
    track = QColor(settings.icon); track.setAlpha(55)
    accent = QColor(settings.icon)
    if compact:
        centers, cy, radius, stroke = (46, 86), 17, 14, 2
    else:
        centers, cy, radius, stroke = (36, 108), 34, 26, 4
    for center, row in zip(centers, data):
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
        font = make_font(settings.font, 9 if compact else 15, 600)
        while QFontMetricsF(font).horizontalAdvance(row['value']) > radius*2-stroke*2 and font.pixelSize() > 7:
            font.setPixelSize(font.pixelSize()-1)
        painter.setFont(font); painter.setPen(text)
        painter.drawText(QRectF(center-radius, cy-(10 if compact else 15), radius*2, 13 if compact else 21), Qt.AlignmentFlag.AlignCenter, row['value'])
        label = row['short_label'] if compact else row['label']
        painter.setFont(make_font(settings.font, 7 if compact else 10))
        muted = QColor(text); muted.setAlpha(210); painter.setPen(muted)
        painter.drawText(QRectF(center-radius, cy+(3 if compact else 7), radius*2, 10 if compact else 16), Qt.AlignmentFlag.AlignCenter, label)
    if state.error:
        painter.setBrush(QColor('#F4B860')); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(99 if compact else 134, 1 if compact else 3, 4, 4))
