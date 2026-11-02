from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    code: int = 0
    result: T
    msg: str = "ok"


class ErrorEnvelope(BaseModel):
    code: int
    result: None = None
    msg: str
