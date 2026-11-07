"""Volatile process state; deliberately not persisted."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RuntimeState:
    started_at: float = field(default_factory=time.time)
    seen_users: set[int] = field(default_factory=set)
    sessions: dict[int, dict] = field(default_factory=dict)
    active_jobs: set[str] = field(default_factory=set)
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    semaphore: asyncio.Semaphore | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


state = RuntimeState()
