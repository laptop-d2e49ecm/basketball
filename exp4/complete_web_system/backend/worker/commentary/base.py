from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CommentaryService(ABC):
    """Contract for replaceable event-to-text commentary implementations."""

    @abstractmethod
    def generate(self, event: dict[str, Any]) -> str:
        """Return a Chinese caption for one structured video event."""
        raise NotImplementedError
