from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .client import Snapshot, Window
from .timezones import localize, offset_label


def window_name(window: Window | None, fallback: str) -> str:
    if window is None:
        return fallback
    seconds = window.duration_seconds
    if seconds % 604800 == 0:
        return "周额度" if seconds == 604800 else f"{seconds // 604800} 周额度"
    if seconds % 86400 == 0:
        return f"{seconds // 86400} 天额度"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} 小时额度"
    return f"{seconds / 60:g} 分钟额度"


def reset_text(window: Window | None, zone: str = 'system') -> str:
    if window is None or window.reset_at is None:
        return "重置时间暂不可用"
    local = localize(datetime.fromtimestamp(window.reset_at, timezone.utc), zone)
    return "重置：" + local.strftime("%m-%d %H:%M ") + offset_label(local)


@dataclass
class QuotaState:
    snapshot: Snapshot | None = None
    error: str | None = None
    refreshing: bool = False
    timezone: str = "system"

    def success(self, snapshot: Snapshot):
        self.snapshot, self.error, self.refreshing = snapshot, None, False

    def failure(self, message: str):
        self.error, self.refreshing = message, False

    @property
    def values(self) -> tuple[str, str]:
        if not self.snapshot:
            return "--", "--"
        return tuple(w.display if w else "--" for w in (self.snapshot.primary, self.snapshot.secondary))

    def status(self) -> str:
        if self.error:
            return ("数据已过期 · " if self.snapshot else "") + self.error
        if self.refreshing:
            return "正在刷新…"
        if self.snapshot:
            local = localize(self.snapshot.fetched_at, self.timezone)
            return "更新于 " + local.strftime("%H:%M:%S ") + offset_label(local)
        return "等待查询"

    def tooltip(self) -> str:
        lines = ["Codex 剩余额度"]
        for i, label in enumerate(("短周期额度", "周额度")):
            window = (self.snapshot.primary, self.snapshot.secondary)[i] if self.snapshot else None
            lines.append(f"{window_name(window, label)}：{self.values[i]}  {reset_text(window, self.timezone)}")
        lines.append(self.status())
        return "\n".join(lines)
