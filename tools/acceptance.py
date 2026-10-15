"""Acceptance of the final ZIP, using isolated UI settings and safe reports."""
from __future__ import annotations

import hashlib
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
    settings_path = VALIDATION/'single-instance/settings.json'
    first=subprocess.Popen([str(exe),'--settings-path',str(settings_path),'--settings'],creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(1)
        assert first.poll() is None
        run(exe,['--settings-path',settings_path,'--settings'],timeout=6)
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
