"""Hospital-local time helpers.

All datetimes stored in the database are NAIVE and represent hospital local
time (config HOSPITAL_TIMEZONE, default Asia/Kolkata).  Keeping one convention
avoids timezone bugs in a demo project.
"""
from datetime import datetime

from flask import current_app

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def hospital_now() -> datetime:
    """Current hospital-local time as a naive datetime (no microseconds)."""
    name = current_app.config.get("HOSPITAL_TIMEZONE", "Asia/Kolkata")
    try:
        if ZoneInfo is None:
            raise RuntimeError
        return datetime.now(ZoneInfo(name)).replace(tzinfo=None, microsecond=0)
    except Exception:  # unknown zone / tzdata missing -> fall back to PC clock
        return datetime.now().replace(microsecond=0)


def hospital_today():
    return hospital_now().date()
