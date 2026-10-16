"""Audit only publication candidates; never print credential values."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quota_monitor import __version__ as VERSION


def publication_files():
    files = [ROOT / name for name in ('main.py', 'requirements.txt', 'README.md', 'VALIDATION.md', '.gitignore')]
    for folder, pattern in [('quota_monitor', '*.py'), ('tests', '*.py'), ('tools', '*.py'),
                            ('assets', '*.svg'), ('assets', '*.ico'), ('assets', '*.png')]:
        files.extend((ROOT / folder).glob(pattern))
    files.extend(path for path in (ROOT / 'assets/fonts').glob('*') if path.is_file())
    files.extend((ROOT / 'docs/images').glob('*.png'))
    return sorted(set(files))


def private_markers():
    # Read locally for an exact-value absence check. Values never leave this process.
    from quota_monitor.client import auth_path
    markers = []
    try:
        data = json.loads(auth_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    def collect(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if key in ('access_token', 'refresh_token', 'id_token', 'account_id', 'email', 'OPENAI_API_KEY') and isinstance(value, str) and len(value) >= 8:
                    markers.append(value.encode())
                elif isinstance(value, (dict, list)):
                    collect(value)
        elif isinstance(item, list):
            for value in item: collect(value)
    collect(data)
    home = str(Path.home())
    for text in (home, home.replace('\\', '/'), str(ROOT), ROOT.as_posix()):
        markers.extend((text.encode('utf-8'), text.encode('utf-16-le')))
    return markers


def main():
    markers = private_markers()
    failures = []
    count = 0
    forbidden = {'auth.json', 'settings.json', 'hosts.yml', '.env', 'gui-report.json'}
    patterns = [re.compile(rb'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}'),
                re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}')]
    def inspect(name, content):
        nonlocal count
        count += 1
        if Path(name).name.casefold() in forbidden or any(part in ('validation', 'build', '.local-tools', '.git') for part in Path(name).parts):
            failures.append({'file':name, 'reason':'private file in publication'})
        if any(marker in content for marker in markers) or any(pattern.search(content) for pattern in patterns):
            failures.append({'file':name, 'reason':'private value or credential pattern detected'})
    for path in publication_files():
        inspect(path.relative_to(ROOT).as_posix(), path.read_bytes())
    for label in ('Windows-x64', 'source'):
        path = ROOT / 'dist' / f'CodexQuotaMonitor-{VERSION}-{label}.zip'
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            for name in archive.namelist():
                if not name.endswith('/'):
                    inspect(path.name + '/' + name, archive.read(name))
    report = {'ok':not failures, 'files_checked':count, 'failures':failures,
              'actual_credential_values_printed':False}
    output = ROOT / 'validation' / ('v'+VERSION) / 'privacy-audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
