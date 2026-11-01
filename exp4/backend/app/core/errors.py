"""统一异常体系：输入错误 400 / 路径或资源不存在 404 / 服务器与模型错误 500。

所有错误响应统一为 {"code": <状态码>, "result": null, "msg": <用户友好提示>}。
"""
from __future__ import annotations


class AppError(Exception):
    status_code = 500
    default_msg = "服务器内部错误"

    def __init__(self, msg: str | None = None):
        self.msg = msg or self.default_msg
        super().__init__(self.msg)


class InputError(AppError):
    """请求参数/文件不合法（400）。"""
    status_code = 400
    default_msg = "请求参数错误"


class NotFoundError(AppError):
    """资源不存在，如任务 ID（404）。"""
    status_code = 404
    default_msg = "资源不存在"


class ModelError(AppError):
    """模型加载/推理失败（500）。"""
    status_code = 500
    default_msg = "模型推理失败，请稍后重试"


def register_exception_handlers(app) -> None:
    """挂载到 FastAPI：所有错误统一信封 {"code": 状态码, "result": null, "msg": ...}。

    用法：app = FastAPI(lifespan=...); register_exception_handlers(app)
    任务书口径：400 参数错 / 404 路径或资源错 / 500 服务器错。
    """
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    def envelope(code: int, msg: str):
        return JSONResponse({"code": code, "result": None, "msg": msg}, status_code=code)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return envelope(exc.status_code, exc.msg)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = first.get("loc", [""])[-1]
        return envelope(400, f"请求参数错误：{field} {first.get('msg', '')}".strip())

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "请求错误"
        return envelope(exc.status_code, detail)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return envelope(500, "服务器内部错误，请稍后重试")
