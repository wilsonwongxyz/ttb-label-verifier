import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.batch.jobs import JobStore
from app.config import Settings, get_settings
from app.extract.base import LabelExtractor
from app.extract.factory import build_extractor
from app.web import batch_routes, routes
from app.web.guards import COOKIE, access_guard, access_token, size_guard

_ERROR_TITLES = {404: "Page not found", 405: "Not allowed"}


def create_app(
    settings: Settings | None = None, extractor: LabelExtractor | None = None
) -> FastAPI:
    """Build the app. Fails fast at startup if the configured provider can't be built."""
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    jobs = JobStore(ttl_seconds=settings.batch_ttl_s)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        jobs.cancel_all()

    app = FastAPI(
        title="Label Verifier", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.extractor = extractor or build_extractor(settings)
    app.state.jobs = jobs

    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
    app.mount("/samples", StaticFiles(directory=settings.fixtures_dir), name="samples")
    app.include_router(routes.router)
    app.include_router(batch_routes.router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/static") or request.url.path.startswith("/samples"):
            return Response(status_code=exc.status_code)
        page: HTMLResponse = routes.render_page(
            request,
            "error.html",
            settings,
            status_code=exc.status_code,
            title=_ERROR_TITLES.get(exc.status_code, "Something went wrong"),
            message=exc.detail
            if exc.status_code != 404 or exc.detail != "Not Found"
            else "There's nothing at this address.",
        )
        return page

    # Generous slack over the batch limit for form fields and multipart framing.
    app.middleware("http")(size_guard(settings.batch_max_bytes + 5 * 1024 * 1024))
    code = settings.access_code.get_secret_value().strip() if settings.access_code else ""
    if code:
        app.middleware("http")(access_guard(code))

    @app.get("/access", response_class=HTMLResponse)
    async def access_page(request: Request, next: str = "/") -> HTMLResponse:
        return routes.render_page(request, "access.html", settings, next=_local(next))

    @app.post("/access", response_model=None)
    async def access_submit(request: Request) -> Response:
        data = await request.form()
        target = _local(str(data.get("next", "/")))
        if not code or hmac.compare_digest(str(data.get("code", "")).strip(), code):
            response = RedirectResponse(target, status_code=303)
            if code:
                response.set_cookie(
                    COOKIE,
                    access_token(code),
                    httponly=True,
                    samesite="lax",
                    secure=request.url.scheme == "https",
                    max_age=7 * 24 * 3600,
                )
            return response
        return routes.render_page(
            request,
            "access.html",
            settings,
            status_code=401,
            next=target,
            error="That code isn't right.",
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _local(path: str) -> str:
    """Only redirect within this site (no open redirects via ``next``)."""
    return path if path.startswith("/") and not path.startswith("//") else "/"
