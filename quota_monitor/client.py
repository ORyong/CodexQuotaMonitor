"""The only module that reads credentials or contacts Codex services.

No login, refresh-token, reset-credit or other modifying endpoints are used.
"""

from __future__ import annotations

import json
import math
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
AUTH_MESSAGE = "请在 Codex 桌面端确认登录状态"


class QuotaError(Exception):
    """Contains only a fixed, safe message, never an HTTP response or token."""

    def __init__(self, message: str, kind: str = "network"):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Window:
    used_percent: float
    duration_seconds: int
    reset_at: int | None

    @property
    def remaining(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))

    @property
    def display(self) -> str:
        # Do not round 0.1% up to 1% or an almost-empty window up to full.
        return f"{math.floor(self.remaining + 1e-9)}%"


@dataclass(frozen=True)
class Snapshot:
    primary: Window | None
    secondary: Window | None
    fetched_at: datetime


def auth_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home) if codex_home else Path.home() / ".codex") / "auth.json"


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _window(data: Any) -> Window | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise QuotaError("额度接口格式发生变化：窗口格式异常", "schema")
    used, duration, reset = (data.get(k) for k in ("used_percent", "limit_window_seconds", "reset_at"))
    if not _number(used) or used < 0:
        raise QuotaError("额度接口格式发生变化：缺少有效使用比例", "schema")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        raise QuotaError("额度接口格式发生变化：缺少有效周期长度", "schema")
    if reset is not None:
        if not isinstance(reset, int) or isinstance(reset, bool) or not 0 <= reset <= 253402300799:
            raise QuotaError("额度接口格式发生变化：重置时间异常", "schema")
    return Window(float(used), duration, reset)


def parse_usage(data: Any, now: datetime | None = None) -> Snapshot:
    if not isinstance(data, dict) or not isinstance(data.get("rate_limit"), dict):
        raise QuotaError("额度接口格式发生变化：缺少 rate_limit", "schema")
    bucket = data["rate_limit"]
    if "primary_window" not in bucket and "secondary_window" not in bucket:
        raise QuotaError("额度接口格式发生变化：缺少额度窗口", "schema")
    primary = _window(bucket.get("primary_window"))
    secondary = _window(bucket.get("secondary_window"))
    return Snapshot(primary, secondary, now or datetime.now(timezone.utc))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the existing bearer credential to any redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_usage(path: Path | None = None, opener=None) -> Snapshot:
    try:
        with (path or auth_path()).open("r", encoding="utf-8-sig") as source:
            data = json.load(source)
        tokens = data.get("tokens") if isinstance(data, dict) else None
        access = tokens.get("access_token") if isinstance(tokens, dict) else None
        account = tokens.get("account_id") if isinstance(tokens, dict) else None
        if not isinstance(access, str) or not access.strip() or not isinstance(account, str) or not account.strip():
            raise QuotaError(AUTH_MESSAGE, "auth")
        if any(c in access + account for c in ("\r", "\n")):
            raise QuotaError(AUTH_MESSAGE, "auth")
    except QuotaError:
        raise
    except (OSError, ValueError, TypeError):
        raise QuotaError(AUTH_MESSAGE, "auth") from None

    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": "Bearer " + access,
            "ChatGPT-Account-Id": account,
            "User-Agent": "CodexQuotaMonitor/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    transport = opener or urllib.request.build_opener(NoRedirect())
    try:
        with transport.open(request, timeout=15) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise QuotaError("额度接口返回异常：响应过大", "schema")
            return parse_usage(json.loads(body))
    except QuotaError:
        raise
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        if code in (401, 403):
            raise QuotaError(AUTH_MESSAGE, "auth") from None
        if code == 429:
            raise QuotaError("查询过于频繁，请稍后刷新", "network") from None
        raise QuotaError(f"额度查询失败（HTTP {code}）", "network") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise QuotaError("网络连接失败，请稍后刷新", "network") from None
    except (ValueError, TypeError, UnicodeError):
        raise QuotaError("额度接口返回格式异常", "schema") from None
