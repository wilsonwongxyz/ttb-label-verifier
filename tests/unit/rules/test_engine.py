from app.extract.schema import LabelExtraction
from app.rules import verify
from app.rules.models import ApplicationData, OverallStatus, Verdict
from app.rules.warning import REQUIRED_WARNING
from tests.unit.rules.conftest import application, extraction, read, warning


def test_clean_sample_label_is_all_clear(
    sample_app: ApplicationData, sample_extraction: LabelExtraction
) -> None:
    report = verify(sample_app, sample_extraction)
    assert report.status == OverallStatus.ALL_CLEAR
    assert [f.field for f in report.fields] == [
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "bottler_name_address",
        "country_of_origin",
        "warning_text",
        "warning_prefix_caps",
        "warning_prefix_bold",
    ]


def test_noted_matches_are_still_all_clear() -> None:
    report = verify(
        application(brand_name="Stone's Throw"),
        extraction(brand_name=read("STONE'S THROW"), net_contents=read("75 cL")),
    )
    assert report.status == OverallStatus.ALL_CLEAR
    assert {f.field: f.verdict for f in report.fields}["brand_name"] == Verdict.MATCH_NOTED


def test_any_mismatch_means_issues_found() -> None:
    report = verify(application(), extraction(alcohol_content=read("40% Alc./Vol. (80 Proof)")))
    assert report.status == OverallStatus.ISSUES_FOUND


def test_title_case_warning_means_issues_found() -> None:
    text = REQUIRED_WARNING.replace("GOVERNMENT WARNING", "Government Warning")
    report = verify(application(), extraction(government_warning=warning(text)))
    assert report.status == OverallStatus.ISSUES_FOUND


def test_review_without_mismatch_means_needs_review() -> None:
    report = verify(application(), extraction(government_warning=warning(bold="unsure")))
    assert report.status == OverallStatus.NEEDS_REVIEW


def test_mismatch_outranks_review() -> None:
    report = verify(
        application(),
        extraction(
            government_warning=warning(bold="unsure"),
            net_contents=read("700 mL"),
        ),
    )
    assert report.status == OverallStatus.ISSUES_FOUND


def test_unusable_image_cant_be_read() -> None:
    report = verify(application(), extraction(image_quality="unusable"))
    assert report.status == OverallStatus.CANT_READ


def test_not_a_label_cant_be_read() -> None:
    report = verify(application(), extraction(is_alcohol_label=False))
    assert report.status == OverallStatus.CANT_READ


def test_nothing_on_the_label_is_never_all_clear() -> None:
    absent = read(None)
    report = verify(
        application(),
        extraction(
            brand_name=absent,
            class_type=absent,
            alcohol_content=absent,
            net_contents=absent,
            bottler_name_address=absent,
            government_warning=warning(None),
        ),
    )
    assert report.status == OverallStatus.ISSUES_FOUND
    assert not any(f.verdict == Verdict.MATCH for f in report.fields)


def test_unreadable_stand_in_needs_review_everywhere() -> None:
    report = verify(application(), LabelExtraction.unreadable())
    assert report.status == OverallStatus.NEEDS_REVIEW
    assert {f.verdict for f in report.fields} <= {Verdict.NEEDS_REVIEW, Verdict.NOT_APPLICABLE}


def test_override_changes_the_verdict_and_status_but_keeps_the_original() -> None:
    from app.rules.engine import with_overrides
    from app.rules.models import Override

    extraction_ = extraction(alcohol_content=read("40% Alc./Vol. (80 Proof)"))
    report = verify(application(), extraction_)
    assert report.status == OverallStatus.ISSUES_FOUND

    changed = with_overrides(
        report,
        extraction_,
        {"alcohol_content": Override(verdict=Verdict.MATCH, reason="Amended application")},
    )
    field = {f.field: f for f in changed.fields}["alcohol_content"]
    assert changed.status == OverallStatus.ALL_CLEAR
    assert field.verdict == Verdict.MATCH
    assert field.overridden_from == Verdict.MISMATCH
    assert field.reason == "Changed by the agent: Amended application"
    # The original report is untouched.
    assert report.status == OverallStatus.ISSUES_FOUND


def test_override_cannot_rescue_an_unreadable_image() -> None:
    from app.rules.engine import with_overrides
    from app.rules.models import Override

    extraction_ = extraction(image_quality="unusable")
    report = verify(application(), extraction_)
    changed = with_overrides(
        report, extraction_, {"brand_name": Override(verdict=Verdict.MATCH, reason="x")}
    )
    assert changed.status == OverallStatus.CANT_READ
