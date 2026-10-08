import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import UploadFile

from app.batch.csv_io import (
    VERDICT_WORDS,
    ApplicationRow,
    SpreadsheetError,
    parse_applications,
    template_csv,
    write_rows,
)
from app.batch.jobs import (
    BatchItem,
    ItemState,
    Job,
    JobStore,
    build_items,
    run_job,
    take_retry_work,
)
from app.config import Settings
from app.rules.models import OverallStatus, Override, Verdict
from app.web.routes import (
    STATUS_DISPLAY,
    ExtractorDep,
    SettingsDep,
    render_page,
    result_context,
)
from app.web.samples import load_samples

router = APIRouter(prefix="/batch")

# Problems first, then labels that need eyes, then clean ones; unfinished work last.
_ROW_ORDER = [
    "not-checked",
    OverallStatus.ISSUES_FOUND,
    OverallStatus.CANT_READ,
    OverallStatus.NEEDS_REVIEW,
    OverallStatus.ALL_CLEAR,
    "waiting",
]
_ROW_DISPLAY: dict[str, tuple[str, str, str]] = {
    "not-checked": ("issues-found", "!", "Not checked"),
    "waiting": ("waiting", "…", "Checking…"),
    **{status: display[:3] for status, display in STATUS_DISPLAY.items()},
}
FILTERS = [
    ("", "All"),
    ("attention", "Needs attention"),
    (OverallStatus.ALL_CLEAR.value, "All clear"),
]


def get_jobs(request: Request) -> JobStore:
    jobs: JobStore = request.app.state.jobs
    return jobs


def _row_kind(item: BatchItem) -> str:
    if item.state == ItemState.WAITING:
        return "waiting"
    if item.status is None:
        return "not-checked"
    return item.status


def _issues(item: BatchItem) -> str:
    if item.problem:
        return item.problem
    report = item.report
    if report is None:
        return ""
    flagged = [
        f"{field.label}: {field.reason}"
        for field in report.fields
        if field.verdict in (Verdict.MISMATCH, Verdict.NEEDS_REVIEW)
    ]
    return " • ".join(flagged)


def _table_context(job: Job, show: str) -> dict[str, Any]:
    items = sorted(job.items, key=lambda i: (_ROW_ORDER.index(_row_kind(i)), i.index))
    counts = {kind: 0 for kind in _ROW_ORDER}
    for item in job.items:
        counts[_row_kind(item)] += 1
    if show == "attention":
        items = [i for i in items if _row_kind(i) not in ("waiting", OverallStatus.ALL_CLEAR)]
    elif show:
        items = [i for i in items if _row_kind(i) == show]
    return {
        "job": job,
        "items": items,
        "show": show,
        "filters": FILTERS,
        "counts": counts,
        "attention": sum(
            counts[k] for k in _ROW_ORDER if k not in ("waiting", OverallStatus.ALL_CLEAR)
        ),
        "row_kind": _row_kind,
        "row_display": _ROW_DISPLAY,
        "issues": _issues,
    }


def _start(
    request: Request,
    settings: Settings,
    extractor: Any,
    rows: list[ApplicationRow],
    images: dict[str, bytes],
) -> Job:
    items, work = build_items(rows, images)
    job = get_jobs(request).add(items)
    job.task = asyncio.create_task(
        run_job(
            job,
            work,
            extractor,
            concurrency=settings.batch_concurrency,
            max_image_bytes=settings.max_image_bytes,
        )
    )
    return job


def _upload_page(request: Request, settings: Settings, error: str | None = None) -> HTMLResponse:
    return render_page(
        request,
        "batch.html",
        settings,
        status_code=422 if error else 200,
        error=error,
        max_files=settings.batch_max_files,
        max_mb=settings.batch_max_bytes // (1024 * 1024),
    )


@router.get("", response_class=HTMLResponse)
async def batch_page(request: Request, settings: SettingsDep) -> HTMLResponse:
    return _upload_page(request, settings)


@router.get("/template.csv")
async def batch_template() -> Response:
    return Response(
        template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="label-batch-template.csv"'},
    )


@router.post("", response_model=None)
async def start_batch(
    request: Request, settings: SettingsDep, extractor: ExtractorDep
) -> HTMLResponse | RedirectResponse:
    # Let our own limit (with its friendly message) apply well before the framework's.
    data = await request.form(max_files=max(1000, settings.batch_max_files * 2))
    sheet = data.get("spreadsheet")
    uploads = [u for u in data.getlist("images") if isinstance(u, UploadFile) and u.filename]

    if not isinstance(sheet, UploadFile) or not sheet.filename:
        return _upload_page(request, settings, "Choose the spreadsheet of application details.")
    if not uploads:
        return _upload_page(request, settings, "Choose the label photos to check.")
    if len(uploads) > settings.batch_max_files:
        return _upload_page(
            request,
            settings,
            f"That's {len(uploads)} photos; the limit is {settings.batch_max_files} per batch. "
            "Please split it into smaller batches.",
        )
    if sum(u.size or 0 for u in uploads) > settings.batch_max_bytes:
        return _upload_page(
            request,
            settings,
            f"The photos add up to more than {settings.batch_max_bytes // (1024 * 1024)} MB. "
            "Please split them into smaller batches.",
        )

    try:
        rows = parse_applications(await sheet.read())
    except SpreadsheetError as exc:
        return _upload_page(request, settings, exc.message)

    images: dict[str, bytes] = {}
    for upload in uploads:
        name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        images[name] = await upload.read(settings.max_image_bytes + 1)

    job = _start(request, settings, extractor, rows, images)
    return RedirectResponse(f"/batch/{job.id}", status_code=303)


@router.post("/example")
async def start_example_batch(
    request: Request, settings: SettingsDep, extractor: ExtractorDep
) -> RedirectResponse:
    samples = load_samples(settings.fixtures_dir).values()
    rows = [
        ApplicationRow(row_number=n, image_filename=s.file, application=s.application)
        for n, s in enumerate(samples, start=2)
    ]
    images = {s.file: (settings.fixtures_dir / s.file).read_bytes() for s in samples}
    job = _start(request, settings, extractor, rows, images)
    return RedirectResponse(f"/batch/{job.id}", status_code=303)


def _job_or_404(request: Request, job_id: str) -> Job:
    job = get_jobs(request).get(job_id)
    if job is None:
        raise HTTPException(
            404, "This batch has expired or doesn't exist. Batches are kept for one hour."
        )
    return job


@router.get("/{job_id}", response_class=HTMLResponse)
async def batch_job(
    request: Request, settings: SettingsDep, job_id: str, show: str = ""
) -> HTMLResponse:
    job = _job_or_404(request, job_id)
    return render_page(request, "batch_job.html", settings, **_table_context(job, show))


@router.get("/{job_id}/table", response_class=HTMLResponse)
async def batch_table(
    request: Request, settings: SettingsDep, job_id: str, show: str = ""
) -> HTMLResponse:
    job = _job_or_404(request, job_id)
    return render_page(request, "_batch_table.html", settings, **_table_context(job, show))


@router.post("/{job_id}/retry")
async def retry_batch(
    request: Request, settings: SettingsDep, extractor: ExtractorDep, job_id: str
) -> RedirectResponse:
    job = _job_or_404(request, job_id)
    if job.finished and job.retry_work:
        job.task = asyncio.create_task(
            run_job(
                job,
                take_retry_work(job),
                extractor,
                concurrency=settings.batch_concurrency,
                max_image_bytes=settings.max_image_bytes,
            )
        )
    return RedirectResponse(f"/batch/{job.id}", status_code=303)


def _item_or_404(job: Job, index: int) -> BatchItem:
    if not 0 <= index < len(job.items) or job.items[index].check is None:
        raise HTTPException(404, "That label hasn't been checked.")
    return job.items[index]


@router.get("/{job_id}/items/{index}", response_class=HTMLResponse)
async def batch_item(
    request: Request, settings: SettingsDep, job_id: str, index: int
) -> HTMLResponse:
    job = _job_or_404(request, job_id)
    item = _item_or_404(job, index)
    assert item.check is not None
    return render_page(
        request,
        "result.html",
        settings,
        back_url=f"/batch/{job.id}",
        item_name=item.filename,
        override_url=f"/batch/{job.id}/items/{index}/override",
        **result_context(item.check, item.report),
    )


@router.post("/{job_id}/items/{index}/override")
async def override_item(request: Request, job_id: str, index: int) -> RedirectResponse:
    """Record (or, with ``undo``, remove) an agent's override of one field's verdict."""
    job = _job_or_404(request, job_id)
    item = _item_or_404(job, index)
    data = await request.form()
    field = str(data.get("field", ""))
    assert item.check is not None
    if field not in {f.field for f in item.check.report.fields}:
        raise HTTPException(400, "Unknown item.")
    if data.get("undo"):
        item.overrides.pop(field, None)
    else:
        verdict = {"match": Verdict.MATCH, "mismatch": Verdict.MISMATCH}.get(
            str(data.get("verdict", ""))
        )
        reason = str(data.get("reason", "")).strip()
        if verdict is None or not reason:
            raise HTTPException(
                400, "Choose whether it matches and give a short reason for the change."
            )
        item.overrides[field] = Override(verdict=verdict, reason=reason[:300])
    return RedirectResponse(f"/batch/{job.id}/items/{index}#field-{field}", status_code=303)


@router.get("/{job_id}/results.csv")
async def batch_export(request: Request, job_id: str) -> Response:
    job = _job_or_404(request, job_id)
    checked = next((i.report for i in job.items if i.report), None)
    field_labels = [f.label for f in checked.fields] if checked else []
    header = [
        "row",
        "image_filename",
        "brand_name",
        "result",
        "issues",
        *field_labels,
        "agent_changes",
    ]

    def row(item: BatchItem) -> list[str]:
        kind = _row_kind(item)
        report = item.report
        verdicts = (
            [VERDICT_WORDS[f.verdict] for f in report.fields]
            if report
            else [""] * len(field_labels)
        )
        changes = "; ".join(
            f"{f.label}: tool said {VERDICT_WORDS[f.overridden_from]}, agent said "
            f"{VERDICT_WORDS[f.verdict]} ({item.overrides[f.field].reason})"
            for f in (report.fields if report else [])
            if f.overridden_from is not None
        )
        return [
            str(item.row_number or ""),
            item.filename,
            item.brand_name,
            _ROW_DISPLAY[kind][2],
            _issues(item),
            *verdicts,
            changes,
        ]

    items = sorted(job.items, key=lambda i: i.index)
    return Response(
        write_rows(header, (row(i) for i in items)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="label-results-{job.id}.csv"'},
    )
