from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from .client import AUTH_MESSAGE, QuotaError, auth_path, fetch_usage, parse_usage
from .settings import Settings


def safe_snapshot(snapshot):
    def window(w):
        return None if w is None else {
            'used_percent': w.used_percent,
            'remaining_percent': w.remaining,
            'display': w.display,
            'duration_seconds': w.duration_seconds,
            'reset_at': w.reset_at,
        }
    return {'primary': window(snapshot.primary), 'secondary': window(snapshot.secondary),
            'fetched_at': snapshot.fetched_at.isoformat()}


def write_report(path: Path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def auth_digest():
    try:
        return hashlib.sha256(auth_path().read_bytes()).hexdigest()
    except OSError:
        return None


def check(path: Path):
    before = auth_digest()
    report = {'frozen': bool(getattr(sys, 'frozen', False)), 'operation': 'GET usage only'}
    try:
        report.update(ok=True, quota=safe_snapshot(fetch_usage()))
    except QuotaError as error:
        report.update(ok=False, error=str(error), error_kind=error.kind)
    report['credential_file_unchanged'] = before == auth_digest()
    write_report(path, report)
    return 0 if report['ok'] and report['credential_file_unchanged'] else 2


def verify_startup_backend():
    """Real Windows registry I/O in a unique QA key, never the startup key."""
    import uuid
    import winreg
    from .startup import RUN_KEY, VALUE_NAME, StartupManager
    scope = r'Software\CodexQuotaMonitor-QA-' + uuid.uuid4().hex
    def actual_startup_value():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                return winreg.QueryValueEx(key, VALUE_NAME)
        except FileNotFoundError:
            return None
    before = actual_startup_value()
    class ScopedRegistry:
        def __getattr__(self, name):
            return getattr(winreg, name)
        def OpenKey(self, root, key, *args):
            assert root == winreg.HKEY_CURRENT_USER and key == RUN_KEY
            return winreg.OpenKey(root, scope, *args)
        def CreateKeyEx(self, root, key, *args):
            assert root == winreg.HKEY_CURRENT_USER and key == RUN_KEY
            return winreg.CreateKeyEx(root, scope, *args)
    manager = StartupManager(ScopedRegistry())
    try:
        assert not manager.is_enabled()
        manager.set_enabled(True)
        assert manager.is_enabled()
        manager.set_enabled(False)
        assert not manager.is_enabled()
    finally:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, scope, 0, winreg.KEY_SET_VALUE) as key:
                try:winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:pass
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, scope)
        except FileNotFoundError:
            pass
    assert actual_startup_value() == before
    return True


def start_self_test(controller, output: Path):
    """Exercise the real GUI and frozen runtime; no credential content is recorded.

    The first stage queries the real service through the same worker as production.
    Failure-state and boundary tests use explicitly synthetic data afterward.
    """
    from PySide6.QtCore import QPoint, QRect, QSize, QTimer, Qt
    from PySide6.QtTest import QTest
    from .app import constrain, tray_icon
    from .settings import MODES

    output.mkdir(parents=True, exist_ok=True)
    report = {'frozen': bool(getattr(sys, 'frozen', False)), 'checks': {}, 'screens': []}
    before = auth_digest()
    finished = False
    deadline = QTimer(controller)
    deadline.setSingleShot(True)
    screenshots = []

    def record(name, value):
        report['checks'][name] = bool(value)
        if not value:
            raise AssertionError(name)

    def finish(error=None):
        nonlocal finished
        if finished:
            return
        finished = True
        deadline.stop()
        if error:
            report['failure'] = str(error)
        report['credential_file_unchanged'] = before == auth_digest()
        report['ok'] = not error and all(report['checks'].values()) and report['credential_file_unchanged']
        write_report(output / 'gui-report.json', report)
        controller.quit()

    def run_gui_checks():
        try:
            snapshot = controller.state.snapshot
            record('live_background_query', snapshot is not None and controller.state.error is None)
            report['live_quota'] = safe_snapshot(snapshot)
            report['screens'] = [{'name': s.name(), 'dpi': s.logicalDotsPerInch(),
                'device_pixel_ratio': s.devicePixelRatio(),
                'available_geometry': s.availableGeometry().getRect()} for s in controller.app.screens()]
            record('bundled_font_loaded', controller.app.property('bundledFontId') >= 0)
            controller.set_mode('taskbar')
            controller.app.processEvents()
            record('taskbar_attached', controller.dock.attached)
            info = controller.dock.diagnostic()
            report['taskbar'] = info
            record('taskbar_is_native_child', info['parent'] == info['host'])
            record('taskbar_inside_shell', info['inside_taskbar'] and info['native_visible'])
            record('taskbar_does_not_cover_buttons', info['no_overlap'])
            controller.taskbar.grab().save(str(output / 'taskbar-live.png'))
            record('taskbar_values_match_live', controller.taskbar.state.values == controller.state.values)
            QTest.mouseClick(controller.taskbar, Qt.MouseButton.LeftButton, pos=QPoint(50,17))
            controller.app.processEvents()
            record('taskbar_click_shows_details', controller.popup.isVisible())
            def settings_native_visible():
                dialog = controller.settings_dialog
                return bool(dialog and dialog.isVisible() and not dialog.isMinimized()
                            and controller.dock.native.user.IsWindowVisible(int(dialog.winId())))
            QTest.mouseClick(controller.popup.settings_button, Qt.MouseButton.LeftButton)
            controller.app.processEvents()
            record('settings_from_taskbar_details_native_visible', settings_native_visible())
            controller.settings_dialog.showMinimized()
            controller.app.processEvents()
            controller.settings_action.trigger()
            controller.app.processEvents()
            record('settings_reopen_restores_minimized', settings_native_visible())
            controller.settings_dialog.reject()
            controller.menu.popup(controller.app.primaryScreen().availableGeometry().center())
            controller.app.processEvents()
            QTest.mouseClick(controller.menu, Qt.MouseButton.LeftButton,
                             pos=controller.menu.actionGeometry(controller.settings_action).center())
            controller.app.processEvents()
            record('settings_from_context_menu_native_visible', settings_native_visible())
            controller.settings_dialog.reject()
            controller.popup.hide()
            restore_width=controller.dock.native.baseline[2]
            for mode in ('tray', 'float', 'both'):
                controller.set_mode(mode)
                controller.app.processEvents()
                if mode=='tray':
                    record('taskbar_gap_restored_on_mode_switch', controller.dock.native.rect(controller.dock.native.rebar)[2]==restore_width)
                record('mode_' + mode, controller.tray.isVisible() == (mode != 'float')
                       and controller.float.isVisible() == (mode != 'tray'))
                controller.show_details()
                QTest.mouseClick(controller.popup.settings_button, Qt.MouseButton.LeftButton)
                controller.app.processEvents()
                record('settings_from_details_' + mode, settings_native_visible())
                controller.settings_dialog.reject()
            controller.float.grab().save(str(output / 'capsule-live.png'))
            screenshots.append('capsule-live.png')
            controller.show_details()
            controller.app.processEvents()
            record('popup_values_match_live_response', all(row[2].text() == expected
                for row, expected in zip(controller.popup.rows, controller.state.values)))
            record('popup_inside_screen', any(s.availableGeometry().contains(controller.popup.geometry())
                for s in controller.app.screens()))
            report['tray_geometry'] = controller.tray.geometry().getRect()
            controller.popup.grab().save(str(output / 'detail-live.png'))
            screenshots.append('detail-live.png')
            controller.popup.hide()
            controller.set_mode('float')
            old_position = controller.float.pos()
            QTest.mousePress(controller.float, Qt.MouseButton.LeftButton, pos=QPoint(15, 24))
            QTest.mouseMove(controller.float, QPoint(45, 44), delay=50)
            QTest.mouseRelease(controller.float, Qt.MouseButton.LeftButton, pos=QPoint(45, 44))
            controller.app.processEvents()
            record('mouse_drag_changes_position', controller.float.pos() != old_position)
            record('mouse_drag_saved', Settings.load(controller.settings_path).x == controller.float.x())
            for screen in controller.app.screens():
                controller.float.move(constrain(screen.availableGeometry().center(), controller.float.size(), [screen.availableGeometry()]))
                controller.app.processEvents()
                record('screen_placement_' + screen.name(), screen.availableGeometry().contains(controller.float.geometry()))
            virtual = [QRect(-1920, 0, 1920, 1080), QRect(0, 0, 2560, 1440)]
            record('removed_monitor_position_recovery', virtual[1].contains(QRect(constrain(QPoint(9000, -400), QSize(112, 48), virtual), QSize(112, 48))))
            record('negative_monitor_coordinates', virtual[0].contains(QRect(constrain(QPoint(-1800, 900), QSize(224, 96), virtual), QSize(224, 96))))
            controller.open_settings()
            controller.app.processEvents()
            dialog = controller.settings_dialog
            QTest.mouseClick(dialog.presets.buttons['森林'], Qt.MouseButton.LeftButton)
            scale_before=dialog.scale.value()
            QTest.mouseClick(dialog.scale.plus, Qt.MouseButton.LeftButton)
            record('modern_stepper_increases_value', dialog.scale.value()==scale_before+5)
            QTest.mouseClick(dialog.scale.minus, Qt.MouseButton.LeftButton)
            record('modern_stepper_decreases_value', dialog.scale.value()==scale_before)
            from PySide6.QtWidgets import QAbstractSpinBox
            record('no_native_spin_arrows', all(control.editor.buttonSymbols()==QAbstractSpinBox.ButtonSymbols.NoButtons for control in (dialog.scale,dialog.interval)))
            dialog.timezone.showPopup()
            controller.app.processEvents()
            dialog.timezone.view().grab().save(str(output/'timezone-dropdown.png'))
            dialog.timezone.hidePopup()
            from .widgets import ColorPicker
            picker=ColorPicker('#485F87',dialog,'背景颜色')
            picker.show()
            picker.hex.setText('invalid')
            record('color_picker_rejects_invalid_hex', not picker.apply.isEnabled())
            picker.hex.setText('#24594E')
            record('color_picker_accepts_hex', picker.apply.isEnabled() and picker.color.name()=='#24594e')
            controller.app.processEvents()
            picker.grab().save(str(output/'color-picker.png'))
            picker.reject()
            dialog.scale.setValue(150)
            dialog.timezone.setCurrentIndex(dialog.timezone.findData('Asia/Shanghai'))
            QTest.mouseClick(dialog.mode.buttons[list(MODES).index('both')], Qt.MouseButton.LeftButton)
            dialog.save()
            controller.app.processEvents()
            loaded = Settings.load(controller.settings_path)
            record('colors_and_mode_persisted', loaded.background == '#24594E' and loaded.mode == 'both')
            record('timezone_saved_and_applied', loaded.timezone == 'Asia/Shanghai' and controller.state.timezone == 'Asia/Shanghai' and 'UTC+08:00' in controller.state.tooltip())
            record('scale_applied', controller.float.size() == QSize(168, 72))
            controller.apply_settings(replace(controller.settings, scale=100, background='#485F87', text='#E9EDF7', icon='#E9EDF7'))
            for scale in (75, 100, 150, 200):
                controller.apply_settings(replace(controller.settings, scale=scale))
                controller.app.processEvents()
                record('scale_' + str(scale), controller.float.width() == round(112 * scale / 100))
                controller.float.grab().save(str(output / f'capsule-scale-{scale}.png'))
            controller.apply_settings(replace(controller.settings, scale=100))
            from .fonts import FONT_OPTIONS, FONT_IDS, family
            from .rings import ring_data
            from PySide6.QtGui import QFontInfo
            controller.open_settings()
            dialog = controller.settings_dialog
            dialog.display_style.setCurrentIndex(dialog.display_style.findData('rings'))
            dialog.save()
            controller.app.processEvents()
            record('rings_style_persisted', Settings.load(controller.settings_path).display_style == 'rings')
            record('rings_float_size', controller.float.size() == QSize(144,68))
            record('rings_values_match_live', tuple(row['value'] for row in ring_data(controller.state)) == controller.state.values)
            controller.float.grab().save(str(output/'rings-live.png'))
            controller.set_mode('taskbar')
            controller.app.processEvents()
            record('rings_taskbar_inside_shell', controller.dock.diagnostic()['inside_taskbar'] and controller.dock.diagnostic()['no_overlap'])
            controller.taskbar.grab().save(str(output/'rings-taskbar.png'))
            controller.set_mode('both')
            for font_key in FONT_OPTIONS:
                record('font_loaded_' + font_key, FONT_IDS.get(font_key,-1) >= 0)
                controller.open_settings()
                dialog = controller.settings_dialog
                dialog.font_choice.setCurrentIndex(dialog.font_choice.findData(font_key))
                record('font_live_preview_' + font_key, dialog.preview.settings.font == font_key)
                dialog.save()
                controller.app.processEvents()
                record('font_saved_' + font_key, Settings.load(controller.settings_path).font == font_key
                       and QFontInfo(controller.app.font()).family() == family(font_key))
                controller.float.grab().save(str(output/('rings-font-'+font_key+'.png')))
            controller.open_settings()
            controller.app.processEvents()
            record('rings_settings_fit_screen', any(s.availableGeometry().contains(controller.settings_dialog.frameGeometry()) for s in controller.app.screens()))
            controller.settings_dialog.grab().save(str(output/'settings-rings.png'))
            controller.settings_dialog.reject()
            controller.apply_settings(replace(controller.settings, font='noto', display_style='capsule'))
            values = controller.state.values
            controller.state.failure('网络连接失败，请稍后刷新')
            controller.render()
            record('stale_keeps_values', controller.state.values == values and '数据已过期' in controller.state.status())
            record('tray_stale_mark', '数据已过期' in controller.tray.toolTip())
            controller.state.failure(AUTH_MESSAGE)
            controller.render()
            record('auth_error_displayed', AUTH_MESSAGE in controller.popup.status.text())
            zero = parse_usage({'rate_limit': {'primary_window': {'used_percent': 100, 'limit_window_seconds': 18000}, 'secondary_window': None}})
            controller.state.success(zero)
            controller.render()
            record('zero_and_missing_distinct', controller.state.values == ('0%', '--'))
            controller.state.success(snapshot)
            controller.render()
            controller.open_settings()
            controller.app.processEvents()
            from PySide6.QtWidgets import QScrollArea
            record('settings_no_scrolling', not controller.settings_dialog.findChildren(QScrollArea))
            record('settings_preview_matches_live', controller.settings_dialog.preview.state.values == controller.state.values)
            record('autostart_ui_matches_system', controller.settings_dialog.autostart.isChecked() == controller.startup.is_enabled())
            record('autostart_registry_roundtrip_isolated_key', verify_startup_backend())
            from .startup import startup_command
            command = startup_command()
            record('autostart_command', '--startup' in command and (not getattr(sys, 'frozen', False) or sys.executable in command))
            record('settings_fit_screen', any(s.availableGeometry().contains(controller.settings_dialog.frameGeometry()) for s in controller.app.screens()))
            controller.settings_dialog.grab().save(str(output / 'settings.png'))
            screenshots.append('settings.png')
            record('multi_resolution_tray_icon', len(tray_icon(controller.settings.icon).availableSizes()) == 6)
            report['screenshots'] = screenshots
            finish()
        except Exception as error:
            finish(type(error).__name__ + ': ' + str(error))

    def updated():
        controller.updated.disconnect(updated)
        QTimer.singleShot(100, run_gui_checks)

    controller.updated.connect(updated)
    deadline.timeout.connect(lambda: finish('Timed out waiting for live quota'))
    deadline.start(30000)
    QTimer.singleShot(0, controller.refresh)
