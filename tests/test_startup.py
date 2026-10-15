from unittest.mock import MagicMock, patch
import subprocess
import sys
import unittest
from quota_monitor.startup import RUN_KEY, VALUE_NAME, StartupError, StartupManager, startup_command


class StartupTests(unittest.TestCase):
    def registry(self):
        return MagicMock()

    def test_frozen_command_quotes_path_and_uses_silent_startup(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',r'D:\程序 空格\CodexQuotaMonitor.exe'):
            self.assertEqual(startup_command(), '"D:\\程序 空格\\CodexQuotaMonitor.exe" --startup')

    def test_enable_only_current_user_own_value(self):
        reg=self.registry();manager=StartupManager(reg)
        manager.set_enabled(True)
        reg.CreateKeyEx.assert_called_once_with(reg.HKEY_CURRENT_USER,RUN_KEY,0,reg.KEY_SET_VALUE)
        reg.SetValueEx.assert_called_once()
        args=reg.SetValueEx.call_args.args
        self.assertEqual(args[1:4],(VALUE_NAME,0,reg.REG_SZ))
        self.assertEqual(args[4],startup_command())
        reg.DeleteValue.assert_not_called()

    def test_disable_removes_only_own_startup_value(self):
        reg=self.registry();StartupManager(reg).set_enabled(False)
        self.assertEqual(reg.DeleteValue.call_args.args[1],VALUE_NAME)
        reg.SetValueEx.assert_not_called()

    def test_missing_value_is_disabled_and_disable_is_idempotent(self):
        reg=self.registry();reg.OpenKey.side_effect=FileNotFoundError()
        manager=StartupManager(reg)
        self.assertFalse(manager.is_enabled())
        manager.set_enabled(False)

    def test_existing_command_must_match_current_location(self):
        reg=self.registry();reg.QueryValueEx.return_value=(startup_command(),reg.REG_SZ)
        manager=StartupManager(reg);self.assertTrue(manager.is_enabled())
        reg.QueryValueEx.return_value=('other program',reg.REG_SZ)
        self.assertFalse(manager.is_enabled())

    def test_denial_is_reported_without_pretending_enabled(self):
        reg=self.registry();reg.CreateKeyEx.side_effect=PermissionError()
        with self.assertRaises(StartupError):StartupManager(reg).set_enabled(True)


if __name__=='__main__':unittest.main()
