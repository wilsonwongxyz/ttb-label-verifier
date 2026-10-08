"""Reading the batch spreadsheet and writing the results export."""

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass

from app.rules.models import ApplicationData, BeverageType, Verdict
from app.web.forms import ApplicationForm

TEMPLATE_COLUMNS = [
    "image_filename",
    "beverage_type",
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_name_address",
    "imported",
    "country_of_origin",
]
REQUIRED_COLUMNS = {"image_filename", "beverage_type", "brand_name", "class_type", "net_contents"}

_BEVERAGE_ALIASES = {
    "distilled_spirits": BeverageType.DISTILLED_SPIRITS,
    "distilled spirits": BeverageType.DISTILLED_SPIRITS,
    "spirits": BeverageType.DISTILLED_SPIRITS,
    "spirit": BeverageType.DISTILLED_SPIRITS,
    "wine": BeverageType.WINE,
    "malt_beverage": BeverageType.MALT_BEVERAGE,
    "malt beverage": BeverageType.MALT_BEVERAGE,
    "beer": BeverageType.MALT_BEVERAGE,
}
_YES = {"yes", "y", "true", "1", "x"}


class SpreadsheetError(Exception):
    """The whole spreadsheet is unusable. ``message`` is safe to show to the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ApplicationRow:
    row_number: int  # as Excel shows it: the header is row 1
    image_filename: str
    application: ApplicationData | None
    problem: str | None = None


def _column_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("/", "_")


def parse_applications(raw: bytes) -> list[ApplicationRow]:
    try:
        text = raw.decode("utf-8-sig")  # Excel adds a byte-order mark
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise SpreadsheetError(
                "The spreadsheet couldn't be read. Please save it as CSV (UTF-8)."
            ) from None

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SpreadsheetError("The spreadsheet is empty.")
    columns = {_column_key(c): c for c in reader.fieldnames if c}
    missing = sorted(REQUIRED_COLUMNS - columns.keys())
    if missing:
        raise SpreadsheetError(
            "The spreadsheet is missing these columns: "
            + ", ".join(missing)
            + ". Download the template to see the expected layout."
        )

    rows = []
    for line, record in enumerate(reader, start=2):
        values = {key: (record.get(original) or "").strip() for key, original in columns.items()}
        if not any(values.values()):
            continue  # blank line
        rows.append(_parse_row(line, values))
    if not rows:
        raise SpreadsheetError("The spreadsheet has no applications in it.")
    return rows


def _parse_row(line: int, values: dict[str, str]) -> ApplicationRow:
    filename = values.get("image_filename", "")
    if not filename:
        return ApplicationRow(line, "", None, "No image filename given.")

    beverage = _BEVERAGE_ALIASES.get(values.get("beverage_type", "").lower())
    form = ApplicationForm.from_submission(
        {
            **values,
            "beverage_type": beverage.value if beverage else "",
            "imported": "on" if values.get("imported", "").lower() in _YES else "",
        }
    )
    application = form.validate()
    if application is None:
        problem = " ".join(form.errors.values())
        if beverage is None:
            problem = problem.replace(
                "Choose the type of drink.",
                "beverage_type must be distilled_spirits, wine or malt_beverage.",
            )
        return ApplicationRow(line, filename, None, problem)
    return ApplicationRow(line, filename, application)


def template_csv() -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(
        [
            "old_tom.jpg",
            "distilled_spirits",
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "45% Alc./Vol. (90 Proof)",
            "750 mL",
            "Bottled by Old Tom Distillery, Bardstown, Kentucky",
            "no",
            "",
        ]
    )
    return out.getvalue()


def safe_cell(value: str) -> str:
    """Stop spreadsheet apps from running cell text as a formula (CSV injection)."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


VERDICT_WORDS = {
    Verdict.MATCH: "match",
    Verdict.MATCH_NOTED: "match (noted)",
    Verdict.NEEDS_REVIEW: "needs review",
    Verdict.MISMATCH: "mismatch",
    Verdict.NOT_APPLICABLE: "n/a",
}


def write_rows(header: list[str], rows: Iterable[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return out.getvalue()
