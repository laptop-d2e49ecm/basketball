from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CommentaryService(ABC):
    """Contract for replaceable event-to-text commentary implementations."""

    @abstractmethod
    def generate(self, event: dict[str, Any]) -> str:
        """Return a Chinese caption for one structured video event."""
        raise NotImplementedError

    def generate_batch(self, events: list[dict[str, Any]]) -> list[str]:
        """Return one caption per event; 默认逐条生成，子类可覆写为批量调用以省配额。"""
        return [self.generate(event) for event in events]
