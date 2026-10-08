import base64
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from app.config import Settings
from app.extract.base import ExtractionError, LabelExtractor
from app.imaging.prepare import ImageRejectedError
from app.rules.models import OverallStatus, Verdict
from app.services.verify import LabelCheck, check_label
from app.web.forms import BEVERAGE_CHOICES, TEXT_FIELDS, ApplicationForm
from app.web.samples import Sample, load_samples

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

STATUS_DISPLAY = {
    OverallStatus.ALL_CLEAR: (
        "all-clear",
        "\u2714",
        "All clear",
        "Everything on the label matches the application.",
    ),
    OverallStatus.NEEDS_REVIEW: (
        "needs-review",
        "\u26a0",
        "Needs review",
        "Nothing is clearly wrong, but some items need your eyes. They are marked below.",
    ),
    OverallStatus.ISSUES_FOUND: (
        "issues-found",
        "\u2716",
        "Issues found",
        "Some items on the label don't match. They are listed first below.",
    ),
    OverallStatus.CANT_READ: (
        "cant-read",
        "?",
        "Can't read this image",
        "The photo is too unclear to check. Ask the applicant for a clearer image.",
    ),
}
VERDICT_DISPLAY = {
    Verdict.MISMATCH: ("mismatch", "\u2716", "Doesn't match"),
    Verdict.NEEDS_REVIEW: ("needs-review", "\u26a0", "Please check"),
    Verdict.MATCH_NOTED: ("match", "\u2714", "Matches (see note)"),
    Verdict.MATCH: ("match", "\u2714", "Matches"),
    Verdict.NOT_APPLICABLE: ("not-applicable", "\u2013", "Not needed"),
}
_VERDICT_ORDER = list(VERDICT_DISPLAY)

router = APIRouter()


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_extractor(request: Request) -> LabelExtractor:
    extractor: LabelExtractor = request.app.state.extractor
    return extractor


SettingsDep = Annotated[Settings, Depends(get_settings)]
ExtractorDep = Annotated[LabelExtractor, Depends(get_extractor)]


def render_page(
    request: Request, name: str, settings: Settings, status_code: int = 200, **context: Any
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {
            "demo_mode": settings.provider == "fixture",
            "samples": load_samples(settings.fixtures_dir).values(),
            **context,
        },
        status_code=status_code,
    )


def _render_form(
    request: Request,
    settings: Settings,
    form: ApplicationForm,
    *,
    sample: Sample | None = None,
    image_error: str | None = None,
    page_error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return render_page(
        request,
        "check.html",
        settings,
        status_code=status_code,
        form=form,
        text_fields=TEXT_FIELDS,
        beverage_choices=BEVERAGE_CHOICES,
        sample=sample,
        image_error=image_error,
        page_error=page_error,
    )


@router.get("/", response_class=HTMLResponse)
async def check_page(request: Request, settings: SettingsDep, sample: str = "") -> HTMLResponse:
    chosen = load_samples(settings.fixtures_dir).get(sample)
    form = ApplicationForm.from_application(chosen.application) if chosen else ApplicationForm()
    return _render_form(request, settings, form, sample=chosen)


@router.post("/check", response_class=HTMLResponse)
async def check(request: Request, settings: SettingsDep, extractor: ExtractorDep) -> HTMLResponse:
    data = await request.form()
    form = ApplicationForm.from_submission({k: v for k, v in data.items() if isinstance(v, str)})
    sample = load_samples(settings.fixtures_dir).get(str(data.get("sample", "")))
    upload = data.get("image")

    raw: bytes | None = None
    if isinstance(upload, UploadFile) and upload.filename:
        # Read one byte past the limit so oversized files are rejected without reading it all.
        raw = await upload.read(settings.max_image_bytes + 1)
        sample = None
    elif sample is not None:
        raw = (settings.fixtures_dir / sample.file).read_bytes()

    application = form.validate()
    image_error = None if raw else "Choose a photo of the label."
    if application is None or raw is None:
        return _render_form(
            request, settings, form, sample=sample, image_error=image_error, status_code=422
        )

    try:
        result = await check_label(
            raw, application, extractor, max_image_bytes=settings.max_image_bytes
        )
    except ImageRejectedError as exc:
        return _render_form(request, settings, form, image_error=exc.message, status_code=422)
    except ExtractionError as exc:
        return _render_form(
            request,
            settings,
            form,
            sample=sample,
            page_error=exc.message,
            status_code=503 if exc.retryable else 422,
        )
    return _render_result(request, settings, result)


def result_context(result: LabelCheck) -> dict[str, Any]:
    """Template context for result.html."""
    rows = sorted(result.report.fields, key=lambda f: _VERDICT_ORDER.index(f.verdict))
    return {
        "status": STATUS_DISPLAY[result.report.status],
        "rows": rows,
        "verdicts": VERDICT_DISPLAY,
        "quality_issues": result.extraction.quality_issues,
        "image_uri": "data:image/jpeg;base64," + base64.b64encode(result.image.data).decode(),
        "seconds": sum(result.timings_ms.values()) / 1000,
    }


def _render_result(request: Request, settings: Settings, result: LabelCheck) -> HTMLResponse:
    return render_page(request, "result.html", settings, **result_context(result))
