import pytest

from app.extract.fixture import FixtureExtractor
from app.imaging.prepare import ImageRejectedError
from app.rules.models import ApplicationData, OverallStatus, Verdict
from app.services.verify import check_label
from tests.samples import SAMPLES_DIR, sample, sample_bytes

LIMIT = 10 * 1024 * 1024
EXTRACTOR = FixtureExtractor.from_dir(SAMPLES_DIR)


async def check(name: str) -> dict[str, Verdict]:
    result = await check_label(
        sample_bytes(name),
        ApplicationData.model_validate(sample(name)["application"]),
        EXTRACTOR,
        max_image_bytes=LIMIT,
    )
    assert set(result.timings_ms) == {"prepare", "extract", "rules"}
    return {"status": result.report.status, **{f.field: f.verdict for f in result.report.fields}}  # type: ignore[dict-item]


@pytest.mark.parametrize(
    ("name", "status", "flagged"),
    [
        ("old_tom_bourbon", OverallStatus.ALL_CLEAR, {}),
        (
            "stones_throw_gin",
            OverallStatus.ALL_CLEAR,
            {"brand_name": Verdict.MATCH_NOTED, "alcohol_content": Verdict.MATCH_NOTED},
        ),
        (
            "harbor_light_rum_title_case",
            OverallStatus.ISSUES_FOUND,
            {"warning_prefix_caps": Verdict.MISMATCH, "warning_prefix_bold": Verdict.NEEDS_REVIEW},
        ),
        (
            "copper_ridge_vodka_wrong_abv",
            OverallStatus.ISSUES_FOUND,
            {"alcohol_content": Verdict.MISMATCH},
        ),
        (
            "domaine_viale_wine_reworded",
            OverallStatus.ISSUES_FOUND,
            {"warning_text": Verdict.MISMATCH, "net_contents": Verdict.MATCH_NOTED},
        ),
    ],
)
async def test_sample_labels_end_to_end(
    name: str, status: OverallStatus, flagged: dict[str, Verdict]
) -> None:
    verdicts = await check(name)
    assert verdicts.pop("status") == status
    for field, verdict in flagged.items():
        assert verdicts[field] == verdict, field


async def test_bad_upload_is_rejected_before_extraction() -> None:
    with pytest.raises(ImageRejectedError):
        await check_label(
            b"not an image",
            ApplicationData.model_validate(sample("old_tom_bourbon")["application"]),
            EXTRACTOR,
            max_image_bytes=LIMIT,
        )
