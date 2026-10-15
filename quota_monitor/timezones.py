"""Application-local timezone preferences; never change the Windows timezone."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

TIMEZONES = [
    ('跟随系统', 'system'),
    ('北京 · UTC+8', 'Asia/Shanghai'),
    ('洛杉矶 · 夏令时', 'America/Los_Angeles'),
    ('纽约 · 夏令时', 'America/New_York'),
    ('伦敦 · 夏令时', 'Europe/London'),
    ('东京 · UTC+9', 'Asia/Tokyo'),
    ('柏林 · 夏令时', 'Europe/Berlin'),
    ('UTC · 协调时', 'UTC'),
]


def valid_timezone(name):
    if name == 'system':return True
    if not isinstance(name,str):return False
    try:ZoneInfo(name);return True
    except (ValueError,ZoneInfoNotFoundError):return False


def localize(time: datetime, zone='system'):
    return time.astimezone() if zone=='system' else time.astimezone(ZoneInfo(zone))


def offset_label(time):
    offset=time.utcoffset()
    if offset is None:return 'UTC'
    minutes=int(offset.total_seconds()/60)
    if minutes==0:return 'UTC'
    sign='+' if minutes>=0 else '-'
    hours,mins=divmod(abs(minutes),60)
    return f'UTC{sign}{hours:02d}:{mins:02d}'
