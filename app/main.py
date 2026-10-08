import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.extract.base import LabelExtractor
from app.extract.factory import build_extractor
from app.web.routes import router


def create_app(
    settings: Settings | None = None, extractor: LabelExtractor | None = None
) -> FastAPI:
    """Build the app. Fails fast at startup if the configured provider can't be built."""
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(title="Label Verifier", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.extractor = extractor or build_extractor(settings)

    app.mount(
        "/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static"
    )
    app.mount("/samples", StaticFiles(directory=settings.fixtures_dir), name="samples")
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
