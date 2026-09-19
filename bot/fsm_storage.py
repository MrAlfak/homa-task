"""JSON-file FSM storage so create-task state survives process restarts."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

logger = logging.getLogger(__name__)


def _key_str(key: StorageKey) -> str:
    thread = getattr(key, "thread_id", None) or ""
    biz = getattr(key, "business_connection_id", None) or ""
    destiny = getattr(key, "destiny", "")
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{thread}:{biz}:{destiny}"


def _state_value(state: StateType) -> str | None:
    if state is None:
        return None
    if isinstance(state, State):
        return state.state
    return str(state)


class JsonFileStorage(BaseStorage):
    """Drop-in replacement for MemoryStorage that persists to a JSON file."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._records = raw
                return
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Could not load FSM file %s", self._path, exc_info=True)
        self._records = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._records, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        except Exception:
            logger.warning("Could not persist FSM file %s", self._path, exc_info=True)

    def _rec(self, key: StorageKey) -> dict[str, Any]:
        token = _key_str(key)
        rec = self._records.get(token)
        if rec is None:
            rec = {"state": None, "data": {}}
            self._records[token] = rec
        return rec

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        async with self._lock:
            rec = self._rec(key)
            rec["state"] = _state_value(state)
            self._save()

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._lock:
            rec = self._records.get(_key_str(key))
            if not rec:
                return None
            value = rec.get("state")
            return str(value) if value is not None else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with self._lock:
            rec = self._rec(key)
            rec["data"] = dict(data)
            self._save()

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            rec = self._rec(key)
            current = dict(rec.get("data") or {})
            current.update(data)
            rec["data"] = current
            self._save()
            return current

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._lock:
            rec = self._records.get(_key_str(key))
            if not rec:
                return {}
            payload = rec.get("data") or {}
            return dict(payload)

    async def close(self) -> None:
        async with self._lock:
            self._save()
