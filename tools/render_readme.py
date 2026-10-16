"""Render README illustrations offscreen using synthetic data and real widgets.

No Controller, credential reads, network requests, tray registration, taskbar
attachment, settings writes or startup changes are involved.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from datetime import datetime, timezone

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_SCALE_FACTOR'] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from quota_monitor.app import Capsule, TaskbarCapsule, SettingsDialog, asset
from quota_monitor.client import parse_usage
from quota_monitor.fonts import FONT_OPTIONS, family, make_font, register_fonts
from quota_monitor.settings import PRESETS, Settings
from quota_monitor.state import QuotaState
from quota_monitor.widgets import component_style

OUTPUT = ROOT / 'docs' / 'images'


def canvas(width, height):
    image = QImage(width * 2, height * 2, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(2)
    image.fill(QColor('#F2F5FA'))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return image, painter


def text(painter, x, y, value, size=16, color='#52627B', weight=400):
    painter.setPen(QColor(color))
    painter.setFont(make_font('noto', size, weight))
    painter.drawText(QPoint(x, y), value)


def card(painter, x, y, width, height):
    painter.setBrush(QColor('#FFFFFF'))
    painter.setPen(QPen(QColor('#E1E7F0'), 1))
    painter.drawRoundedRect(QRectF(x, y, width, height), 20, 20)


def widget(painter, view, x, y, scale=1):
    view.ensurePolished()
    if view.layout():
        view.layout().activate()
    painter.save()
    painter.translate(x, y)
    painter.scale(scale, scale)
    # Rendering hidden widgets also paints their children; no native show().
    view.render(painter, QPoint())
    painter.restore()


def quota_widget(state, style='rings', taskbar=False, font='source_han_sans', colors=None):
    settings = Settings(display_style=style, font=font)
    if colors:
        settings.background, settings.text, settings.icon = colors
    view = (TaskbarCapsule if taskbar else Capsule)(settings)
    view.render_state(state)
    return view


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    loaded = register_fonts(asset('fonts'))
    assert all(value >= 0 for value in loaded.values()), 'A bundled font failed to load'
    app.setFont(make_font('noto', 12, 430))
    app.setStyleSheet(component_style(asset(''), family('noto')))
    state = QuotaState(timezone='Asia/Shanghai')
    state.success(parse_usage({'rate_limit': {
        'primary_window': {'used_percent': 25, 'limit_window_seconds': 18000},
        'secondary_window': {'used_percent': 50, 'limit_window_seconds': 604800},
    }}, now=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert state.values == ('75%', '50%')
    OUTPUT.mkdir(parents=True, exist_ok=True)

    image, painter = canvas(1120, 488)
    text(painter, 40, 58, 'Codex 额度', 36, '#263A58', 650)
    text(painter, 40, 94, '5 小时与一周剩余额度，抬眼可见。', 19)
    text(painter, 40, 128, '任务栏直接显示  /  自由悬浮  /  托盘始终常驻', 14, '#6D7E95')
    examples = [
        ('胶囊', '上下两行：5 小时 / 一周', 'capsule', False, 2),
        ('双圆环', '两个圆环，分别查看剩余比例', 'rings', False, 1.9),
        ('任务栏组件', '紧凑显示，点击查看详情', 'rings', True, 2),
    ]
    for index, (title, note, style, taskbar, scale) in enumerate(examples):
        x = 40 + index * 352
        card(painter, x, 164, 336, 252)
        text(painter, x + 24, 202, title, 20, '#304662', 600)
        view = quota_widget(state, style, taskbar)
        widget(painter, view, x + (336 - view.width()*scale)/2,
               232 + (126-view.height()*scale)/2, scale)
        text(painter, x + 24, 389, note, 14)
        view.close()
    text(painter, 40, 456, '界面组件展示 · 75% / 50% 为示例额度，非真实账户数据 · 组件已放大', 13, '#76859B')
    painter.end()
    assert image.save(str(OUTPUT / 'overview.png'))

    dialog = SettingsDialog(Settings(display_style='rings', font='source_han_sans'), state)
    dialog.preview_note.setText('示例额度 · 非真实账户数据')
    dialog.ensurePolished()
    dialog.layout().activate()
    dialog.adjustSize()
    width, height = dialog.width() + 80, dialog.height() + 124
    image, painter = canvas(width, height)
    text(painter, 40, 38, '显示、字体、配色与时区，一页完成', 18, '#304662', 600)
    widget(painter, dialog, 40, 60)
    text(painter, 40, height-22, '当前源码界面 · 示例额度 · 后台绘制，无真实账户信息', 12, '#76859B')
    painter.end()
    assert image.save(str(OUTPUT / 'settings.png'))
    dialog.reject()

    image, painter = canvas(1120, 738)
    text(painter, 40, 52, '选择喜欢的字体和配色', 28, '#263A58', 650)
    text(painter, 40, 85, '内置 7 款字体，仅在应用内加载；下方圆环使用各自字体。', 16)
    for index, (key, (name, _)) in enumerate(FONT_OPTIONS.items()):
        x, y = 40 + (index % 2)*528, 112 + (index // 2)*112
        card(painter, x, y, 512, 98)
        text(painter, x+22, y+54, name, 19, '#304662', 500)
        view = quota_widget(state, font=key)
        widget(painter, view, x+325, y+15)
        view.close()
    card(painter, 568, 448, 512, 98)
    text(painter, 590, 486, '字号自适应', 19, '#304662', 500)
    text(painter, 590, 518, '按字形边界排版，适配百分号与倾斜字体。', 14)
    text(painter, 40, 586, '5 组预设 · 背景 / 文字 / 图标可分别修改', 17, '#304662', 500)
    for index, (name, colors) in enumerate(PRESETS.items()):
        x = 40 + index * 212
        view = quota_widget(state, taskbar=True, colors=colors)
        widget(painter, view, x, 610, 1.4)
        text(painter, x+4, 686, name.split(' · ')[0], 14)
        view.close()
    text(painter, 40, 720, '字体与颜色示例 · 所有 75% / 50% 均为示例额度', 12, '#76859B')
    painter.end()
    assert image.save(str(OUTPUT / 'appearance.png'))
    print('Created 3 README images offscreen using synthetic quota values only.')
    app.quit()


if __name__ == '__main__':
    main()
