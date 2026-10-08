"""Entry point of the rule engine: application + extraction in, verification report out."""

from app.extract.schema import LabelExtraction
from app.rules.fields import (
    check_alcohol,
    check_bottler,
    check_country_of_origin,
    check_net_contents,
    compare_text,
)
from app.rules.models import (
    ApplicationData,
    FieldResult,
    OverallStatus,
    Verdict,
    VerificationReport,
)
from app.rules.warning import check_warning_bold, check_warning_prefix, check_warning_text


def overall_status(extraction: LabelExtraction, fields: list[FieldResult]) -> OverallStatus:
    if not extraction.is_alcohol_label or extraction.image_quality == "unusable":
        return OverallStatus.CANT_READ
    verdicts = {f.verdict for f in fields}
    if Verdict.MISMATCH in verdicts:
        return OverallStatus.ISSUES_FOUND
    if Verdict.NEEDS_REVIEW in verdicts:
        return OverallStatus.NEEDS_REVIEW
    return OverallStatus.ALL_CLEAR


def verify(app: ApplicationData, extraction: LabelExtraction) -> VerificationReport:
    warning = extraction.government_warning
    fields = [
        compare_text("brand_name", "Brand name", app.brand_name, extraction.brand_name),
        compare_text("class_type", "Class / type", app.class_type, extraction.class_type),
        check_alcohol(app, extraction.alcohol_content),
        check_net_contents(app, extraction.net_contents),
        check_bottler(app, extraction.bottler_name_address),
        check_country_of_origin(app, extraction.country_of_origin),
        check_warning_text(warning),
        check_warning_prefix(warning),
        check_warning_bold(warning),
    ]
    return VerificationReport(status=overall_status(extraction, fields), fields=fields)
