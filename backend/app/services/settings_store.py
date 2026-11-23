from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Setting
from .seed import DEFAULT_SETTINGS


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    s = db.get(Setting, key)
    if s is None:
        return DEFAULT_SETTINGS.get(key, default)
    return s.value


def set_setting(db: Session, key: str, value: Any) -> None:
    s = db.get(Setting, key)
    if s is None:
        db.add(Setting(key=key, value=value))
    else:
        s.value = value


def all_settings(db: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for s in db.query(Setting).all():
        out[s.key] = s.value
    return out
