"""Lightweight progress reporting helpers for conversion workflows.

Callbacks receive ``(percent: int, message: str)``. All callback failures are
isolated from conversion; integrations may adapt this to Telegram status edits.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ProgressCallback = Callable[[int, str], object] | None


@dataclass
class ProgressReporter:
    callback: ProgressCallback = None
    last_percent: int = -1

    def report(self, percent: float, message: str = "") -> None:
        """Clamp and emit progress, ignoring callback exceptions."""
        value = max(0, min(100, int(percent)))
        if value < self.last_percent: value = self.last_percent
        self.last_percent = value
        if self.callback:
            try: self.callback(value, message)
            except Exception: pass


def report_progress(callback: ProgressCallback, percent: float, message: str = "") -> None:
    """Convenience one-shot progress notification."""
    ProgressReporter(callback).report(percent, message)
