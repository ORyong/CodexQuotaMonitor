"""Mode composition checks without opening any UI or modifying the taskbar."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from quota_monitor.app import Controller
from quota_monitor.settings import Settings,MODES

class ModesTests(unittest.TestCase):
    def controller(self,mode,attached=True):
        obj=Mock();obj.settings=Settings(mode=mode)
        obj.dock.attach.return_value=attached
        obj.mode_actions={k:Mock() for k in MODES}
        return obj
    def test_every_display_mode_keeps_tray_visible(self):
        for mode in MODES:
            with self.subTest(mode=mode),patch('quota_monitor.app.QSystemTrayIcon.isSystemTrayAvailable',return_value=True):
                obj=self.controller(mode);Controller.apply_mode(obj)
                obj.tray.setVisible.assert_called_once_with(True)
                obj.float.setVisible.assert_called_once_with(mode!='taskbar')
                if mode=='float':obj.dock.detach.assert_called_once()
                else:obj.dock.attach.assert_called_once()
    def test_taskbar_failure_still_shows_float_and_tray(self):
        with patch('quota_monitor.app.QSystemTrayIcon.isSystemTrayAvailable',return_value=True):
            obj=self.controller('taskbar',False);Controller.apply_mode(obj)
            obj.tray.setVisible.assert_called_once_with(True)
            obj.float.setVisible.assert_called_once_with(True)
    def test_both_mode_maintains_taskbar(self):
        obj=self.controller('both');obj.quitting=False;obj.dock.attached=True;obj.dock.refresh.return_value=True
        Controller.maintain_taskbar(obj);obj.dock.refresh.assert_called_once()
    def test_both_mode_reconnect_preserves_float(self):
        obj=self.controller('both');obj.quitting=False;obj.dock.attached=False
        Controller.maintain_taskbar(obj)
        obj.dock.attach.assert_called_once()
        obj.float.setVisible.assert_called_once_with(True)
    def test_taskbar_reserves_the_current_style_width(self):
        from quota_monitor.taskbar import TaskbarDock
        obj=Mock();obj.attached=True;obj.native.user.IsWindow.return_value=True
        obj.widget.winId.return_value=123;obj.widget.logical_width=128
        self.assertTrue(TaskbarDock.refresh(obj))
        obj.native.reserve.assert_called_once_with(123,128)
    def test_legacy_tray_setting_migrates_and_unknown_types_are_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'settings.json'
            p.write_text(json.dumps({'mode':'tray'}));self.assertEqual(Settings.load(p).mode,'taskbar')
            p.write_text(json.dumps({'mode':[],'font':[]}));self.assertEqual(Settings.load(p),Settings())
        self.assertEqual(set(MODES),{'taskbar','float','both'})

if __name__=='__main__':unittest.main()
