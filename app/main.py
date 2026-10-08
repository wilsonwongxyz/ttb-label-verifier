from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Label Verifier", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
