"""Request guards for a public deployment: an optional access code and an upload size cap."""

import hashlib
import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

COOKIE = "lv_access"
OPEN_PATHS = ("/healthz", "/static/", "/access")

Handler = Callable[[Request], Awaitable[Response]]


def access_token(code: str) -> str:
    """Cookie value proving the visitor knew the code, without storing the code itself."""
    return hmac.new(code.encode(), b"label-verifier-access", hashlib.sha256).hexdigest()


def access_guard(code: str) -> Callable[[Request, Handler], Awaitable[Response]]:
    expected = access_token(code)

    async def guard(request: Request, call_next: Handler) -> Response:
        path = request.url.path
        if path.startswith(OPEN_PATHS) or hmac.compare_digest(
            request.cookies.get(COOKIE, ""), expected
        ):
            return await call_next(request)
        return RedirectResponse(f"/access?next={request.url.path}", status_code=303)

    return guard


def size_guard(max_bytes: int) -> Callable[[Request, Handler], Awaitable[Response]]:
    async def guard(request: Request, call_next: Handler) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            return PlainTextResponse(
                "This upload is too large. Please split it into smaller batches.", status_code=413
            )
        return await call_next(request)

    return guard
