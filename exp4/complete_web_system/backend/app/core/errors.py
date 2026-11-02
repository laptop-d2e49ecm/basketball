from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 500
    default_msg = "服务器内部错误"

    def __init__(self, msg: str | None = None):
        self.msg = msg or self.default_msg
        super().__init__(self.msg)


class InputError(AppError):
    status_code = 400
    default_msg = "请求参数错误"


class NotFoundError(AppError):
    status_code = 404
    default_msg = "资源不存在"


class ModelError(AppError):
    status_code = 500
    default_msg = "模型推理失败，请稍后重试"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "result": None, "msg": exc.msg},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = first.get("loc", [""])[-1]
        msg = f"请求参数错误：{field} {first.get('msg', '')}".strip()
        return JSONResponse(status_code=400, content={"code": 400, "result": None, "msg": msg})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        msg = exc.detail if isinstance(exc.detail, str) else "请求错误"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "result": None, "msg": msg},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "result": None, "msg": "服务器内部错误，请稍后重试"},
        )
