from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import (QByteArray, QObject, QPoint, QRect, QRectF, QRunnable,
                            QSize, Qt, QThreadPool, QTimer, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFont, QFontDatabase, QIcon, QPainter,
                           QPen, QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QButtonGroup,
    QMenu, QPushButton, QScrollArea, QSpinBox, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import __version__
from .client import QuotaError, fetch_usage
from .settings import MODES, PRESETS, Settings, default_settings_path
from .state import QuotaState, reset_text, window_name
from .startup import StartupError, StartupManager
from .taskbar import TaskbarDock
from .widgets import Stepper, ModernComboBox, ColorPicker, component_style
from .timezones import TIMEZONES, valid_timezone, available_timezones

APP_NAME = 'Codex 额度'
UI_FONT = 'Noto Sans SC'


def asset(name: str) -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return root / 'assets' / name


def mark(color: str, size: int = 64) -> QPixmap:
    data = asset('codex.svg').read_text(encoding='utf-8').replace('#0D0D0D', color)
    renderer = QSvgRenderer(QByteArray(data.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def tray_icon(color: str, problem: bool = False, background: str = '#485F87') -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(0,0,size,size),size*.24,size*.24)
        glyph = mark(color,size)
        painter.drawPixmap(QRectF(size*.04,size*.04,size*.92,size*.92),glyph,QRectF(glyph.rect()))
        painter.end()
        if problem:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#F4B860'))
            radius = size * .14
            painter.drawEllipse(QPoint(round(size * .82), round(size * .82)), round(radius), round(radius))
            painter.end()
        icon.addPixmap(pixmap)
    return icon


def constrain(position: QPoint, size: QSize, screens: list[QRect]) -> QPoint:
    """Recover saved positions when a screen is removed or DPI changes."""
    if not screens:
        return position
    containing = next((r for r in screens if r.contains(position)), None)
    if containing is None:
        containing = min(screens, key=lambda r: (r.center() - position).manhattanLength())
    return QPoint(max(containing.left(), min(position.x(), containing.right() - size.width() + 1)),
                  max(containing.top(), min(position.y(), containing.bottom() - size.height() + 1)))


class WorkerSignals(QObject):
    success = Signal(object)
    failed = Signal(str)
    finished = Signal()


class FetchWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.success.emit(fetch_usage())
        except QuotaError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            # Do not render exception repr/HTTP bodies: they can contain account data.
            self.signals.failed.emit('额度查询失败，请稍后刷新')
        finally:
            self.signals.finished.emit()


class Capsule(QWidget):
    moved = Signal()
    detailRequested = Signal()
    menuRequested = Signal(QPoint)

    def __init__(self, settings: Settings):
        super().__init__()
        self.setWindowTitle('Codex 额度 · 悬浮窗')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.settings = settings
        self.state = QuotaState()
        self._drag_start = None
        self._origin = None
        self._dragged = False
        self.allow_close = False
        self.apply_settings()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName('Codex 剩余额度悬浮窗')

    def apply_settings(self):
        visible = self.isVisible()
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.settings.topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)
        self.setFixedSize(round(112 * self.settings.scale / 100), round(48 * self.settings.scale / 100))
        self.logo = mark(self.settings.icon, 128)
        if visible:
            self.show()
        self.update()

    def render_state(self, state: QuotaState):
        self.state = state
        self.setToolTip(state.tooltip())
        self.setAccessibleDescription(state.tooltip())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 112, self.height() / 48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.settings.background))
        painter.drawRoundedRect(QRectF(0, 0, 112, 48), 24, 24)
        painter.drawPixmap(QRectF(10, 10, 28, 28), self.logo, QRectF(self.logo.rect()))
        font = QFont(UI_FONT, 13)
        font.setWeight(QFont.Weight.DemiBold)
        font.setVariableAxis(QFont.Tag.fromString('wght'), 600)
        # Pixel size keeps the intended proportions independent of the monitor's DPI.
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor(self.settings.text))
        for value, top in zip(self.state.values, (4, 24)):
            painter.drawText(QRectF(45, top, 57, 20), Qt.AlignmentFlag.AlignCenter, value)
        if self.state.error:
            painter.setBrush(QColor('#F4B860'))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(100, 6, 5, 5))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.move(self._origin + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            if self._dragged:
                self.move(constrain(self.pos(), self.size(), [s.availableGeometry() for s in QApplication.screens()]))
                self.moved.emit()
            else:
                self.detailRequested.emit()
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()

    def contextMenuEvent(self, event):
        self.menuRequested.emit(event.globalPos())

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
            return
        # Alt+F4 must not leave a running app inaccessible in floating-only mode.
        event.ignore()
        self.menuRequested.emit(self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2)))


class TaskbarCapsule(Capsule):
    def apply_settings(self):
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(104, 34)
        self.logo = mark(self.settings.icon, 128)
        self.update()

    def __init__(self, settings):
        super().__init__(settings)
        self.setWindowTitle('Codex 额度 · 任务栏')
        self.setAccessibleName('Codex 任务栏剩余额度')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width()/104,self.height()/34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.settings.background))
        painter.drawRoundedRect(QRectF(0,0,104,34),16,16)
        painter.drawPixmap(QRectF(9,6,22,22),self.logo,QRectF(self.logo.rect()))
        font=QFont(UI_FONT)
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        font.setVariableAxis(QFont.Tag.fromString('wght'), 600)
        painter.setFont(font)
        painter.setPen(QColor(self.settings.text))
        for value,top in zip(self.state.values,(1,17)):
            painter.drawText(QRectF(39,top,56,16),Qt.AlignmentFlag.AlignCenter,value)
        if self.state.error:
            painter.setBrush(QColor('#F4B860'));painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(96,4,4,4))
        painter.end()

    def mouseMoveEvent(self,event):
        event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._drag_start=None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.detailRequested.emit()
            event.accept()


class DetailPopup(QFrame):
    refreshRequested = Signal()
    settingsRequested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('Codex 额度 · 详情')
        self.setObjectName('detailPopup')
        self.setMinimumWidth(296)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)
        heading = QHBoxLayout()
        self.logo = QLabel()
        self.logo.setFixedSize(28, 28)
        heading.addWidget(self.logo)
        title = QLabel('Codex 剩余额度')
        title.setObjectName('title')
        heading.addWidget(title)
        heading.addStretch()
        outer.addLayout(heading)
        self.rows = []
        for _ in range(2):
            row = QHBoxLayout()
            labels = QVBoxLayout()
            name = QLabel()
            name.setObjectName('period')
            reset = QLabel()
            reset.setObjectName('muted')
            labels.addWidget(name)
            labels.addWidget(reset)
            value = QLabel('--')
            value.setObjectName('quotaValue')
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addLayout(labels)
            row.addSpacing(24)
            row.addWidget(value)
            outer.addLayout(row)
            self.rows.append((name, reset, value))
        self.status = QLabel()
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        buttons = QHBoxLayout()
        self.refresh = QPushButton('立即刷新')
        self.refresh.clicked.connect(self.refreshRequested)
        settings = QPushButton('设置')
        settings.clicked.connect(self.settingsRequested)
        buttons.addWidget(self.refresh)
        buttons.addWidget(settings)
        outer.addLayout(buttons)

    def render_state(self, state: QuotaState, settings: Settings):
        self.logo.setPixmap(mark(settings.icon, 28))
        for i, (name, reset, value) in enumerate(self.rows):
            window = (state.snapshot.primary, state.snapshot.secondary)[i] if state.snapshot else None
            name.setText(window_name(window, ('短周期额度', '周额度')[i]))
            reset.setText(reset_text(window, state.timezone))
            value.setText(state.values[i])
        self.status.setText(state.status())
        self.refresh.setEnabled(not state.refreshing)
        self.setStyleSheet(f'''
            QFrame#detailPopup {{ background: {settings.background}; border-radius: 16px; }}
            QLabel {{ color: {settings.text}; background: transparent; }}
            QLabel#title {{ font-size: 15px; font-weight: 600; }}
            QLabel#period {{ font-size: 13px; font-weight: 600; }}
            QLabel#quotaValue {{ font-size: 28px; font-weight: 600; }}
            QLabel#muted {{ font-size: 11px; }}
            QPushButton {{ background: rgba(255,255,255,28); color: {settings.text};
                border: 1px solid rgba(255,255,255,36); border-radius: 7px; padding: 7px 12px; }}
            QPushButton:hover {{ background: rgba(255,255,255,48); }}
            QPushButton:disabled {{ color: #A9ACB3; }}
        ''')
        self.adjustSize()


class ModeSelector(QFrame):
    """Three visible segmented buttons; no dropdown or hidden mode control."""
    def __init__(self, selected):
        super().__init__()
        self.setObjectName('modeSelector')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.buttons = []
        for index, (key, label) in enumerate(MODES.items()):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(key == selected)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setObjectName('modeButton')
            button.setFixedHeight(30)
            self.group.addButton(button, index)
            self.buttons.append(button)
            layout.addWidget(button)

    def currentData(self):
        return list(MODES)[self.group.checkedId()]


class ThemePicker(QWidget):
    chosen = Signal(str)

    def __init__(self):
        super().__init__()
        self.group = QButtonGroup(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.buttons = {}
        for name, colors in PRESETS.items():
            button = QPushButton()
            button.setCheckable(True)
            button.setFixedSize(30, 30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setStyleSheet(f"QPushButton {{ background: {colors[0]}; border: 3px solid #FFFFFF; border-radius: 15px; }} QPushButton:checked {{ border: 3px solid #7192C2; }}")
            self.group.addButton(button)
            self.buttons[name] = button
            button.clicked.connect(lambda checked=False, n=name: self.chosen.emit(n))
            layout.addWidget(button)
        layout.addStretch()

    def select(self, name):
        self.group.setExclusive(False)
        for key, button in self.buttons.items():
            button.setChecked(name == key)
        self.group.setExclusive(True)


class SettingsDialog(QDialog):
    saved = Signal(object)

    def __init__(self, settings: Settings, quota_state: QuotaState | None = None):
        super().__init__()
        self.setWindowTitle('Codex 额度 · 设置')
        self.setObjectName('settingsDialog')
        self.setMinimumWidth(576)
        self.pending = replace(settings)
        self.quota_state = quota_state or QuotaState()
        self.setStyleSheet("""
            QDialog#settingsDialog { background: #F5F6F8; }
            QWidget { font-family: 'Noto Sans SC'; font-size: 12px; color: #3E4753; }
            QLabel { background: transparent; }
            QLabel#muted { color: #707985; font-size: 11px; }
            QLabel#cardTitle { color: #323B47; font-size: 12px; font-weight: 600; }
            QFrame#settingsCard { background: white; border: 1px solid #E4E7EC; border-radius: 12px; }
            QFrame#modeSelector { background: #E9EDF2; border-radius: 10px; }
            QPushButton#modeButton { background: transparent; border: 0; border-radius: 7px; color: #687484; }
            QPushButton#modeButton:checked { background: white; color: #435C7C; font-weight: 600; }
            QPushButton#modeButton:hover { color: #2F4E7B; }
            QPushButton#saveButton { background: #4C6382; color: white; border: 0; border-radius: 7px; padding: 7px 23px; font-weight: 600; }
            QPushButton#saveButton:hover { background: #3D5371; }
            QPushButton#cancelButton { background: transparent; border: 1px solid #D7DFEC; border-radius: 7px; padding: 7px 18px; color: #67727F; }
            QPushButton#cancelButton:hover { background: #E8EDF5; }
            QPushButton#colorButton { background: #FAFBFC; border: 1px solid #E3E7ED; border-radius: 6px; padding: 5px 7px; }
            QPushButton#colorButton:hover { background: #EDF2FA; border-color: #B8C8DE; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(mark('#67788F', 30))
        icon.setFixedSize(36, 36)
        header.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel('Codex 额度')
        title.setStyleSheet('font-size: 17px; font-weight: 600; color: #343E4B;')
        subtitle = QLabel('显示与外观')
        subtitle.setObjectName('muted')
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        version = QLabel('v' + __version__)
        version.setObjectName('muted')
        header.addWidget(version)
        root.addLayout(header)
        self.mode = ModeSelector(settings.mode)
        root.addWidget(self.mode)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        left = QFrame()
        left.setObjectName('settingsCard')
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(10)
        label = QLabel('显示与启动')
        label.setObjectName('cardTitle')
        left_layout.addWidget(label)
        self.scale = Stepper()
        self.scale.setRange(75, 200)
        self.scale.setSuffix(' %')
        self.scale.setSingleStep(5)
        self.scale.setValue(settings.scale)
        self.scale.setFixedWidth(110)
        self.scale.valueChanged.connect(self.update_size_label)
        row = QHBoxLayout()
        row.addWidget(QLabel('悬浮窗大小'))
        row.addStretch()
        row.addWidget(self.scale)
        left_layout.addLayout(row)
        self.topmost = QCheckBox('始终置顶')
        self.topmost.setChecked(settings.topmost)
        left_layout.addWidget(self.topmost)
        self.autostart = QCheckBox('开机启动')
        self.autostart.setToolTip('登录 Windows 后自动运行，沿用上次的显示模式')
        self.autostart.setChecked(settings.autostart)
        left_layout.addWidget(self.autostart)
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet('background: #EDF0F6; border: 0;')
        left_layout.addWidget(separator)
        label = QLabel('刷新')
        label.setObjectName('cardTitle')
        left_layout.addWidget(label)
        self.interval = Stepper()
        self.interval.setRange(30, 3600)
        self.interval.setSuffix(' 秒')
        self.interval.setValue(settings.refresh_seconds)
        self.interval.setFixedWidth(110)
        row = QHBoxLayout()
        row.addWidget(QLabel('自动更新'))
        row.addStretch()
        row.addWidget(self.interval)
        left_layout.addLayout(row)
        self.timezone = ModernComboBox()
        self.timezone.setMinimumWidth(142)
        self.timezone.setMaximumWidth(178)
        self.timezone.setMaxVisibleItems(12)
        for label, key in TIMEZONES:
            self.timezone.addItem(label, key)
        common = {key for _, key in TIMEZONES}
        for key in sorted(available_timezones() - common):
            self.timezone.addItem(key, key)
        index = self.timezone.findData(settings.timezone)
        self.timezone.setCurrentIndex(max(0,index))
        self.timezone.setToolTip('仅改变本软件的重置时间和更新时间显示')
        row = QHBoxLayout()
        row.addWidget(QLabel('时区'))
        row.addStretch()
        row.addWidget(self.timezone)
        left_layout.addLayout(row)
        left_layout.addStretch()
        right = QFrame()
        right.setObjectName('settingsCard')
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(10)
        palette_header = QHBoxLayout()
        label = QLabel('配色')
        label.setObjectName('cardTitle')
        palette_header.addWidget(label)
        palette_header.addStretch()
        self.theme_name = QLabel()
        self.theme_name.setObjectName('muted')
        palette_header.addWidget(self.theme_name)
        right_layout.addLayout(palette_header)
        self.presets = ThemePicker()
        self.presets.chosen.connect(self.select_preset)
        right_layout.addWidget(self.presets)
        self.colors = {}
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        for key, label in [('background', '背景'), ('text', '文字'), ('icon', '图标')]:
            button = QPushButton(label)
            button.setObjectName('colorButton')
            button.setIconSize(QSize(12, 12))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, k=key: self.choose_color(k))
            self.colors[key] = button
            color_row.addWidget(button)
        right_layout.addLayout(color_row)
        preview_box = QFrame()
        preview_box.setObjectName('previewBox')
        preview_box.setStyleSheet('QFrame#previewBox { background: #F3F5F8; border: 0; border-radius: 9px; }')
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        preview_layout.setSpacing(5)
        self.preview = Capsule(self.pending)
        self.preview.setWindowFlags(Qt.WindowType.Widget)
        self.preview.setFixedSize(112, 48)
        self.preview.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self.preview)
        preview_row.addStretch()
        preview_layout.addLayout(preview_row)
        self.preview_note = QLabel('')
        self.preview_note.setObjectName('muted')
        self.preview_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_note)
        right_layout.addWidget(preview_box)
        self.size_label = QLabel()
        self.size_label.setObjectName('muted')
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.size_label)
        cards.addWidget(left, 1)
        cards.addWidget(right, 1)
        root.addLayout(cards)
        self.error_label = QLabel()
        self.error_label.setStyleSheet('color: #B54A21; font-size: 11px;')
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)
        footer = QHBoxLayout()
        footnote = QLabel('配色与显示设置保存在本机')
        footnote.setObjectName('muted')
        footer.addWidget(footnote)
        footer.addStretch()
        self.cancel_button = QPushButton('取消')
        self.cancel_button.setObjectName('cancelButton')
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton('保存')
        self.save_button.setObjectName('saveButton')
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        root.addLayout(footer)
        self.update_colors()
        self.update_size_label()
        self.set_quota_state(self.quota_state)
        self.layout().activate()
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(constrain(area.center() - QPoint(self.width() // 2, self.height() // 2),
                            self.size(), [area.adjusted(8, 32, -8, -8)]))

    def set_quota_state(self, state):
        self.quota_state = state
        self.preview.render_state(state)
        self.preview_note.setText('当前额度预览' if state.snapshot else '等待额度数据')
        if state.error:
            self.preview_note.setText('额度暂不可用' if not state.snapshot else '上次额度 · 已过期')

    def update_size_label(self, *args):
        if hasattr(self, 'size_label'):
            scale = self.scale.value() / 100
            self.size_label.setText(f'实际尺寸 {round(112 * scale)} × {round(48 * scale)}')

    def update_colors(self):
        current = (self.pending.background, self.pending.text, self.pending.icon)
        selected = next((name for name, values in PRESETS.items() if tuple(c.lower() for c in values) == tuple(c.lower() for c in current)), None)
        self.presets.select(selected)
        self.theme_name.setText(selected.split(' · ')[0] if selected else '自定义')
        for key, button in self.colors.items():
            color = getattr(self.pending, key)
            swatch = QPixmap(16, 16)
            swatch.fill(Qt.GlobalColor.transparent)
            painter = QPainter(swatch)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(color))
            painter.setPen(QPen(QColor('#C6D0DE'), 1))
            painter.drawRoundedRect(QRectF(.5, .5, 15, 15), 4, 4)
            painter.end()
            button.setIcon(QIcon(swatch))
            button.setToolTip(color.upper() + ' · 点击更换')
        self.preview.logo = mark(self.pending.icon, 128)
        self.preview.update()

    def select_preset(self, name):
        if name in PRESETS:
            self.pending.background, self.pending.text, self.pending.icon = PRESETS[name]
            self.update_colors()

    def choose_color(self, key):
        dialog = ColorPicker(getattr(self.pending, key), self, {'background':'背景颜色','text':'文字颜色','icon':'图标颜色'}[key])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            setattr(self.pending, key, dialog.color.name())
            self.update_colors()

    def save(self):
        self.pending.mode = self.mode.currentData()
        self.pending.scale = self.scale.value()
        self.pending.topmost = self.topmost.isChecked()
        self.pending.autostart = self.autostart.isChecked()
        self.pending.refresh_seconds = self.interval.value()
        self.pending.timezone = self.timezone.currentData()
        self.saved.emit(self.pending)


class Controller(QObject):
    updated = Signal()

    def __init__(self, app: QApplication, settings_path: Path):
        super().__init__()
        self.app = app
        self.settings_path = settings_path
        self.settings = Settings.load(settings_path)
        self.startup = StartupManager()
        self.settings.autostart = self.startup.is_enabled()
        self.state = QuotaState(timezone=self.settings.timezone)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.worker = None
        self.quitting = False
        self.settings_dialog = None
        self.float = Capsule(self.settings)
        self.popup = DetailPopup()
        self.taskbar = TaskbarCapsule(self.settings)
        self.dock = TaskbarDock(self.taskbar, self)
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(tray_icon(self.settings.icon, background=self.settings.background))
        self.menu = QMenu()
        self.mode_menu = self.menu.addMenu('显示模式')
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_actions = {}
        for key, text in MODES.items():
            action = QAction(text, self.mode_group)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, k=key: self.set_mode(k))
            self.mode_menu.addAction(action)
            self.mode_actions[key] = action
        self.menu.addSeparator()
        self.refresh_action = self.menu.addAction('立即刷新', self.refresh)
        self.menu.addAction('设置…', self.open_settings)
        self.startup_action = self.menu.addAction('开机启动')
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(self.settings.autostart)
        self.startup_action.triggered.connect(self.toggle_startup)
        self.menu.addSeparator()
        self.menu.addAction('退出', self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.float.menuRequested.connect(self.menu.popup)
        self.float.detailRequested.connect(self.show_details)
        self.taskbar.detailRequested.connect(self.show_details)
        self.taskbar.menuRequested.connect(self.menu.popup)
        self.float.moved.connect(self.remember_position)
        self.popup.refreshRequested.connect(self.refresh)
        self.popup.settingsRequested.connect(self.open_settings)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.settings.refresh_seconds * 1000)
        self.recover_position()
        self.apply_mode()
        self.render()
        for screen in self.app.screens():
            screen.availableGeometryChanged.connect(self.recover_position)
        self.app.screenAdded.connect(self.screen_added)
        self.app.screenRemoved.connect(lambda _: QTimer.singleShot(100, self.recover_position))
        self.taskbar_watch = QTimer(self)
        self.taskbar_watch.timeout.connect(self.maintain_taskbar)
        self.taskbar_watch.start(2000)
        self.app.aboutToQuit.connect(self.shutdown)

    def maintain_taskbar(self):
        if self.quitting or self.settings.mode != 'taskbar':
            return
        if not self.dock.attached:
            self.float.setVisible(not self.dock.attach())
        elif not self.dock.refresh():
            self.float.show()

    def screen_added(self, screen):
        screen.availableGeometryChanged.connect(self.recover_position)
        self.recover_position()

    def recover_position(self, *args):
        screens = [s.availableGeometry() for s in self.app.screens()]
        if self.settings.x is None or self.settings.y is None:
            rect = self.app.primaryScreen().availableGeometry()
            position = QPoint(rect.right() - self.float.width() - 24, rect.top() + 28)
        else:
            position = QPoint(self.settings.x, self.settings.y)
        self.float.move(constrain(position, self.float.size(), screens))

    def remember_position(self):
        self.settings.x, self.settings.y = self.float.x(), self.float.y()
        self.save_settings()

    def save_settings(self) -> bool:
        try:
            self.settings.save(self.settings_path)
            return True
        except OSError:
            return False

    def apply_mode(self):
        tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray.setVisible(self.settings.mode != 'float' and tray_available)
        if self.settings.mode == 'taskbar':
            embedded = self.dock.attach()
            self.float.setVisible(not embedded)
        else:
            self.dock.detach()
            self.float.setVisible(self.settings.mode in ('float','both') or not tray_available)
        for key, action in self.mode_actions.items():
            action.setChecked(key == self.settings.mode)

    def set_mode(self, mode):
        self.settings.mode = mode
        self.popup.hide()
        self.apply_mode()
        if not self.save_settings():
            self.open_settings()
            self.settings_dialog.error_label.setText('无法保存设置，请检查目录写入权限。当前显示模式仍已生效。')
            self.settings_dialog.error_label.show()

    def apply_settings(self, settings):
        old = self.settings
        self.settings = replace(settings)
        if not self.save_settings():
            self.settings = old
            self.startup_action.setChecked(old.autostart)
            self.open_settings()
            self.settings_dialog.error_label.setText('无法保存设置，请检查目录写入权限。')
            self.settings_dialog.error_label.show()
            return
        if self.settings.autostart != old.autostart:
            try:
                self.startup.set_enabled(self.settings.autostart)
            except StartupError as error:
                self.settings = old
                self.save_settings()
                self.open_settings()
                self.settings_dialog.error_label.setText(str(error))
                self.settings_dialog.error_label.show()
                self.startup_action.setChecked(old.autostart)
                return
        self.startup_action.setChecked(self.settings.autostart)
        self.state.timezone = self.settings.timezone
        self.float.settings = self.settings
        self.float.apply_settings()
        self.taskbar.settings = self.settings
        self.taskbar.logo = mark(self.settings.icon, 128)
        self.taskbar.update()
        self.recover_position()
        self.apply_mode()
        self.timer.start(self.settings.refresh_seconds * 1000)
        self.render()
        if self.settings_dialog:
            self.settings_dialog.accept()

    def toggle_startup(self, enabled):
        self.apply_settings(replace(self.settings, autostart=enabled))

    def refresh(self):
        if self.quitting or self.state.refreshing:
            return
        self.state.refreshing = True
        self.render()
        self.worker = FetchWorker()
        self.worker.signals.success.connect(self.received)
        self.worker.signals.failed.connect(self.failed)
        self.worker.signals.finished.connect(self.worker_finished)
        self.pool.start(self.worker)

    def worker_finished(self):
        self.worker = None

    def received(self, snapshot):
        self.state.success(snapshot)
        self.render()
        self.updated.emit()

    def failed(self, message):
        self.state.failure(message)
        self.render()
        self.updated.emit()

    def render(self):
        self.float.render_state(self.state)
        self.taskbar.render_state(self.state)
        self.popup.render_state(self.state, self.settings)
        self.tray.setIcon(tray_icon(self.settings.icon, bool(self.state.error), self.settings.background))
        self.tray.setToolTip(self.state.tooltip())
        self.refresh_action.setEnabled(not self.state.refreshing)
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.set_quota_state(self.state)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.show_details()

    def show_details(self):
        self.render()
        if self.dock.attached:
            anchor = self.taskbar.windowHandle().mapToGlobal(QPoint(self.taskbar.width() // 2, 0))
            screen = self.app.screenAt(anchor) or self.app.primaryScreen()
            position = QPoint(anchor.x() - self.popup.width() // 2, anchor.y() - self.popup.height() - 8)
        elif self.tray.isVisible():
            rect = self.tray.geometry()
            anchor = rect.center() if not rect.isNull() else QCursor.pos()
            screen = self.app.screenAt(anchor) or self.app.primaryScreen()
            # Select the correct side for taskbars on any edge; clamp to its work area.
            position = QPoint(anchor.x() - self.popup.width() // 2, (rect.top() if not rect.isNull() else anchor.y()) - self.popup.height() - 8)
            if position.y() < screen.availableGeometry().top():
                position.setY((rect.bottom() if not rect.isNull() else anchor.y()) + 8)
        else:
            anchor = self.float.geometry().center()
            screen = self.app.screenAt(anchor) or self.app.primaryScreen()
            position = QPoint(self.float.x(), self.float.y() + self.float.height() + 8)
        self.popup.move(constrain(position, self.popup.size(), [screen.availableGeometry()]))
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()

    def open_settings(self):
        self.popup.hide()
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.settings.autostart = self.startup.is_enabled()
        self.startup_action.setChecked(self.settings.autostart)
        self.settings_dialog = SettingsDialog(self.settings, self.state)
        self.settings_dialog.setWindowIcon(tray_icon(self.settings.icon, background=self.settings.background))
        self.settings_dialog.saved.connect(self.apply_settings)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def shutdown(self):
        if self.quitting:
            return
        self.quitting = True
        self.timer.stop()
        self.taskbar_watch.stop()
        self.dock.detach()
        self.tray.hide()
        self.float.hide()
        self.popup.hide()
        if self.settings_dialog:
            self.settings_dialog.hide()
        # No subprocesses are started. Finish the bounded read before Qt destroys signals.
        self.pool.waitForDone(17000)

    def quit(self):
        self.dock.detach()
        self.taskbar.allow_close = True
        self.taskbar.close()
        self.float.allow_close = True
        self.float.close()
        self.app.quit()


def instance_server(path: Path, app: QApplication, activate: bool = True, taskbar: bool = False, stop: bool = False):
    name = 'CodexQuotaMonitor-' + hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()[:20]
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(300):
        socket.write(b'quit' if stop else (b'taskbar' if taskbar else (b'show' if activate else b'ping')))
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer(app)
    if not server.listen(name):
        raise RuntimeError('无法创建本地单实例通道')
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Codex 额度：只读现有登录状态，不介入登录。')
    parser.add_argument('--settings-path', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--settings', action='store_true', help='打开设置')
    parser.add_argument('--startup', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--taskbar', action='store_true', help='在任务栏直接显示额度')
    parser.add_argument('--quit', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--check', type=Path, help='只读查询并写入不含凭据的诊断 JSON')
    parser.add_argument('--self-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.check:
        from .verification import check
        return check(args.check)
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    app.setApplicationName('CodexQuotaMonitor')
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    font_id = QFontDatabase.addApplicationFont(str(asset('fonts/NotoSansSC-VF.ttf')))
    interface_font = QFont(UI_FONT if font_id >= 0 else 'Microsoft YaHei UI', 9)
    interface_font.setVariableAxis(QFont.Tag.fromString('wght'), 430)
    app.setFont(interface_font)
    app.setProperty('bundledFontId', font_id)
    app.setStyleSheet(component_style(asset('')))
    app.setWindowIcon(tray_icon('#485F87'))
    path = args.settings_path or default_settings_path()
    if args.self_test:
        path = args.self_test / 'settings.json'
    server = instance_server(path, app, activate=not args.startup, taskbar=args.taskbar, stop=args.quit)
    if server is None:
        return 0
    if args.quit:
        server.close()
        return 0
    controller = Controller(app, path)
    if args.taskbar:
        controller.set_mode('taskbar')
    def new_connection():
        connection = server.nextPendingConnection()
        if not connection:
            return
        def consume():
            command = bytes(connection.readAll())
            if command == b'quit':
                controller.quit()
            if command == b'taskbar':
                controller.set_mode('taskbar')
            if command == b'show':
                controller.open_settings()
            connection.disconnectFromServer()
            connection.deleteLater()
        connection.readyRead.connect(consume)
        if connection.bytesAvailable():
            consume()
    server.newConnection.connect(new_connection)
    if args.self_test:
        from .verification import start_self_test
        start_self_test(controller, args.self_test)
    else:
        QTimer.singleShot(0, controller.refresh)
        if args.settings:
            QTimer.singleShot(200, controller.open_settings)
    exit_code = app.exec()
    server.close()
    return exit_code
