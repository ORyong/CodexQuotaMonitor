"""Build runtime and source archives from an explicit file allowlist."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from quota_monitor import __version__ as VERSION
RELEASE_DIST = ROOT / "dist" / ("V" + VERSION)


def main():
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    sys.path.insert(0, str(ROOT))
    from quota_monitor.app import mark
    app = QApplication([])
    mark('#485F87', 256).save(str(ROOT / 'assets/app.png'))
    Image.open(ROOT / 'assets/app.png').save(ROOT / 'assets/app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    app.quit()
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--distpath', str(RELEASE_DIST),
        '--name', 'CodexQuotaMonitor', '--icon', str(ROOT / 'assets/app.ico'),
        '--add-data', str(ROOT / 'assets') + os.pathsep + 'assets',
        '--collect-data', 'tzdata',
        '--exclude-module', 'PyQt6', '--exclude-module', 'PyQt5', '--exclude-module', 'tkinter',
        '--exclude-module', 'numpy', '--exclude-module', 'matplotlib',
        '--exclude-module', 'pandas', '--exclude-module', 'pytest', str(ROOT / 'main.py')]
    # Build in a predictable DLL search environment. Scientific-tool runtimes
    # injected into PATH can contain an incompatible icuuc.dll with the same name
    # as Windows ICU used by Qt. Do not collect those unrelated dependencies.
    build_env = os.environ.copy()
    windows = Path(build_env.get('SystemRoot', r'C:\Windows'))
    python = Path(sys.executable).parent
    build_env['PATH'] = os.pathsep.join(map(str, [python, python / 'Scripts', windows / 'System32', windows]))
    subprocess.run(command, check=True, env=build_env)
    # README is deliberately omitted from this release.
    previous_readme = RELEASE_DIST / 'CodexQuotaMonitor/使用说明.md'
    previous_readme.unlink(missing_ok=True)
    if (ROOT / 'VALIDATION.md').exists():
        shutil.copy2(ROOT / 'VALIDATION.md', RELEASE_DIST / 'CodexQuotaMonitor/验证说明.md')
    package()


def package():
    dist = ROOT / 'dist'
    app_dir = RELEASE_DIST / 'CodexQuotaMonitor'
    with zipfile.ZipFile(dist / f'CodexQuotaMonitor-{VERSION}-Windows-x64.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app_dir.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(RELEASE_DIST))
    with zipfile.ZipFile(dist / f'CodexQuotaMonitor-{VERSION}-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        sources = [ROOT / n for n in ('main.py', 'requirements.txt', 'VALIDATION.md', '.gitignore')]
        for folder, pattern in [('quota_monitor','*.py'),('tests','*.py'),('tools','*.py'),('assets','*.svg'),('assets','*.ico')]:
            sources.extend((ROOT / folder).glob(pattern))
        sources.extend((ROOT / 'assets/fonts').glob('*'))
        for path in sorted(sources):
            archive.write(path, path.relative_to(ROOT))
    print('Runtime ZIP and source ZIP created in', dist)


if __name__ == '__main__':
    main()
