"""Acceptance of the final ZIP, using isolated UI settings and safe reports."""
from __future__ import annotations

import hashlib
import ctypes
import ctypes.wintypes as wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quota_monitor import __version__ as VERSION
VALIDATION = ROOT / 'validation' / ('v' + VERSION)


def run(exe, args, env=None, timeout=40):
    # subprocess.run kills its own child on timeout, including a bootloader error dialog.
    result = subprocess.run([str(exe), *map(str,args)], timeout=timeout,
        env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise AssertionError('Application exited with ' + str(result.returncode))



def settings_native_state(pid):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    rows = []
    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value.startswith('Codex') and '设置' in title.value:
                rows.append({'visible': bool(user32.IsWindowVisible(hwnd)),
                             'minimized': bool(user32.IsIconic(hwnd))})
        return True
    user32.EnumWindows(inspect, 0)
    return rows


def wait_for_visible_settings(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = settings_native_state(pid)
        if any(row['visible'] and not row['minimized'] for row in rows):
            return
        time.sleep(.05)
    raise AssertionError('Settings window is not natively visible: ' + repr(rows))


def verify_settings_startups(exe, results):
    for hidden in (True, False):
        label = 'hidden' if hidden else 'normal'
        settings_path = VALIDATION / ('settings-startup-' + label) / 'settings.json'
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({'mode':'float'}), encoding='utf-8')
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0 if hidden else 1
        process = subprocess.Popen([str(exe), '--settings-path', str(settings_path), '--settings'],
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            wait_for_visible_settings(process.pid)
            results['settings_' + label + '_startup_native_visible'] = True
            run(exe, ['--settings-path', settings_path, '--settings'], timeout=6)
            wait_for_visible_settings(process.pid)
            results['settings_' + label + '_reopen_native_visible'] = True
        finally:
            run(exe, ['--settings-path', settings_path, '--quit'], timeout=6)
            process.wait(timeout=20)


def main():
    archive = ROOT / 'dist' / f'CodexQuotaMonitor-{VERSION}-Windows-x64.zip'
    destination = VALIDATION/'最终 中文空格 解压验收'
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert not any(Path(name).name.casefold() in ('auth.json','settings.json') for name in zipped.namelist())
        zipped.extractall(destination)
    exe = destination/'CodexQuotaMonitor/CodexQuotaMonitor.exe'
    results = {'archive_integrity':True, 'no_auth_or_user_settings_in_archive':True,
               'chinese_space_path':True,'runs':[]}
    for label, factor in [('native',None),('100-percent','0.8'),('200-percent','1.6')]:
        output = VALIDATION/('release-'+label)
        environment = os.environ.copy()
        if factor:
            environment['QT_SCALE_FACTOR'] = factor
        run(exe,['--self-test',output],env=environment)
        report=json.loads((output/'gui-report.json').read_text(encoding='utf-8'))
        assert report['ok'] and report['frozen'] and report['credential_file_unchanged'], report.get('failure')
        results['runs'].append({'name':label,'checks_passed':len(report['checks']),
            'actual_device_pixel_ratio':report['screens'][0]['device_pixel_ratio'],
            'physical_screens':len(report['screens']),'all_passed':True})
    verify_settings_startups(exe, results)
    settings_path = VALIDATION/'single-instance/settings.json'
    first=subprocess.Popen([str(exe),'--settings-path',str(settings_path),'--settings'],creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(1)
        assert first.poll() is None
        wait_for_visible_settings(first.pid)
        run(exe,['--settings-path',settings_path,'--settings'],timeout=6)
        wait_for_visible_settings(first.pid)
        assert first.poll() is None
        results['single_instance_second_process_exits']=True
        run(exe,['--settings-path',settings_path,'--startup'],timeout=6)
        assert first.poll() is None
        results['startup_duplicate_process_exits']=True
    finally:
        if first.poll() is None:
            run(exe,['--settings-path',settings_path,'--quit'],timeout=6)
            first.wait(timeout=20)
        results['graceful_exit_restores_taskbar']=True
    processes=[]
    for process in psutil.process_iter(['pid','name']):
        if process.info['name']=='CodexQuotaMonitor.exe':
            try:
                if Path(process.exe()).resolve().is_relative_to(destination.resolve()):processes.append(process.pid)
            except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    results['no_test_processes_left']=not processes
    assert not processes
    results['runtime_zip_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
    results['ok']=True
    (VALIDATION/'release-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
