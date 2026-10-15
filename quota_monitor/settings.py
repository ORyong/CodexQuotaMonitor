"""UI preferences only. This file never stores credentials or API responses."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from .timezones import valid_timezone
from .fonts import FONT_OPTIONS

PRESETS = {
    "蓝灰 · 参考配色": ("#485F87", "#E9EDF7", "#E9EDF7"),
    "石墨": ("#252932", "#F1F3F7", "#C8D0DF"),
    "森林": ("#24594E", "#E9F5EF", "#CEF0DF"),
    "梅紫": ("#665078", "#FFF0FA", "#F4D9F1"),
    "浅色": ("#E6ECF5", "#28364C", "#405779"),
}
MODES = {"taskbar": "任务栏", "tray": "仅托盘", "float": "仅悬浮窗", "both": "悬浮+托盘"}


def default_settings_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "CodexQuotaMonitor" / "settings.json"


@dataclass
class Settings:
    mode: str = "taskbar"
    display_style: str = "capsule"
    font: str = "noto"
    scale: int = 100
    background: str = "#485F87"
    text: str = "#E9EDF7"
    icon: str = "#E9EDF7"
    topmost: bool = True
    autostart: bool = False
    timezone: str = "system"
    refresh_seconds: int = 60
    x: int | None = None
    y: int | None = None

    @classmethod
    def load(cls, path: Path):
        result = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return result
            if valid_timezone(data.get("timezone")):
                result.timezone = data["timezone"]
            if data.get("mode") in MODES:
                result.mode = data["mode"]
            if data.get("display_style") in ("capsule", "rings"):
                result.display_style = data["display_style"]
            if data.get("font") in FONT_OPTIONS:
                result.font = data["font"]
            for name, lower, upper in [("scale", 75, 200), ("refresh_seconds", 30, 3600)]:
                value = data.get(name)
                if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper:
                    setattr(result, name, value)
            for name in ("background", "text", "icon"):
                value = data.get(name)
                if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    setattr(result, name, value)
            for name in ("topmost", "autostart"):
                if isinstance(data.get(name), bool):
                    setattr(result, name, data[name])
            if all(isinstance(data.get(k), int) and not isinstance(data.get(k), bool) for k in ("x", "y")):
                result.x, result.y = data["x"], data["y"]
        except (OSError, ValueError):
            pass
        return result

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
