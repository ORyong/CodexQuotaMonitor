"""Optional per-user Windows startup, controlled explicitly by the UI.

Only the CodexQuotaMonitor value is touched. No scheduled tasks, services,
login actions, administrator privileges, or machine-wide settings are used.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'CodexQuotaMonitor'


class StartupError(Exception):
    pass


def startup_command() -> str:
    if getattr(sys, 'frozen', False):
        args = [sys.executable, '--startup']
    else:
        python = Path(sys.executable)
        windowless = python.with_name('pythonw.exe')
        args = [str(windowless if windowless.exists() else python),
                str(Path(__file__).resolve().parents[1] / 'main.py'), '--startup']
    return subprocess.list2cmdline(args)


class StartupManager:
    def __init__(self, registry=winreg):
        self.registry = registry

    def is_enabled(self) -> bool:
        reg = self.registry
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
                command, _ = reg.QueryValueEx(key, VALUE_NAME)
            return isinstance(command, str) and command.casefold() == startup_command().casefold()
        except OSError:
            return False

    def set_enabled(self, enabled: bool):
        reg = self.registry
        try:
            if enabled:
                with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                    reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, startup_command())
            else:
                try:
                    with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                        reg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        except OSError:
            raise StartupError('无法设置开机启动，请检查当前用户权限。') from None
