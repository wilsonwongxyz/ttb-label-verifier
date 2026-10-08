from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extract.base import ExtractionError
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.main import create_app
from app.rules.models import BeverageType
from tests.samples import sample, sample_bytes


def client(**settings: Any) -> TestClient:
    return TestClient(create_app(Settings(provider="fixture", **settings)))


def form_for(name: str) -> dict[str, str]:
    application = sample(name)["application"]
    data = {k: v for k, v in application.items() if isinstance(v, str)}
    if application["imported"]:
        data["imported"] = "on"
    return data


class FailingExtractor:
    def __init__(self, error: ExtractionError) -> None:
        self.error = error

    async def extract(self, image: PreparedImage, beverage_type: BeverageType) -> LabelExtraction:
        raise self.error


def test_check_page_shows_the_form_and_examples() -> None:
    response = client().get("/")
    assert response.status_code == 200
    assert 'action="/check"' in response.text
    assert "Try an example" in response.text
    assert "Demo mode" in response.text


def test_example_prefills_the_form() -> None:
    response = client().get("/?sample=old_tom_bourbon")
    assert 'value="OLD TOM DISTILLERY"' in response.text
    assert 'name="sample" value="old_tom_bourbon"' in response.text
    assert 'src="/samples/old_tom_bourbon.png"' in response.text


def test_unknown_example_is_ignored() -> None:
    assert client().get("/?sample=nope").status_code == 200


def test_sample_images_are_served() -> None:
    response = client().get("/samples/old_tom_bourbon.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_checking_an_example_is_all_clear() -> None:
    data = form_for("old_tom_bourbon") | {"sample": "old_tom_bourbon"}
    response = client().post("/check", data=data)
    assert response.status_code == 200
    assert "All clear" in response.text
    assert 'src="data:image/jpeg;base64,' in response.text


def test_uploaded_title_case_label_shows_issues_first() -> None:
    response = client().post(
        "/check",
        data=form_for("harbor_light_rum_title_case"),
        files={"image": ("rum.png", sample_bytes("harbor_light_rum_title_case"), "image/png")},
    )
    assert response.status_code == 200
    assert "Issues found" in response.text
    text = response.text
    # Mismatches are listed before matches.
    assert text.index("must be all capital letters") < text.index("Matches the application.")


def test_reworded_warning_shows_a_word_diff() -> None:
    data = form_for("domaine_viale_wine_reworded") | {"sample": "domaine_viale_wine_reworded"}
    response = client().post("/check", data=data)
    assert "<del" in response.text and ">not drink </del>" in response.text
    assert ">avoid drinking </ins>" in response.text


def test_missing_fields_are_explained() -> None:
    data = form_for("old_tom_bourbon") | {"sample": "old_tom_bourbon", "brand_name": " "}
    response = client().post("/check", data=data)
    assert response.status_code == 422
    assert "Enter the brand name from the application." in response.text
    # What the agent typed is kept.
    assert 'value="Kentucky Straight Bourbon Whiskey"' in response.text


def test_spirits_need_alcohol_content() -> None:
    data = form_for("old_tom_bourbon") | {"sample": "old_tom_bourbon", "alcohol_content": ""}
    response = client().post("/check", data=data)
    assert response.status_code == 422
    assert "spirits must state it" in response.text


def test_imported_products_need_a_country() -> None:
    data = form_for("old_tom_bourbon") | {"sample": "old_tom_bourbon", "imported": "on"}
    response = client().post("/check", data=data)
    assert response.status_code == 422
    assert "country of origin for imported products" in response.text


def test_photo_is_required() -> None:
    response = client().post("/check", data=form_for("old_tom_bourbon"))
    assert response.status_code == 422
    assert "Choose a photo of the label." in response.text


def test_non_image_upload_is_explained() -> None:
    response = client().post(
        "/check",
        data=form_for("old_tom_bourbon"),
        files={"image": ("notes.pdf", b"%PDF-1.7", "application/pdf")},
    )
    assert response.status_code == 422
    assert "isn&#39;t a photo we can open" in response.text


def test_oversized_upload_is_rejected() -> None:
    response = client(max_image_bytes=1024).post(
        "/check",
        data=form_for("old_tom_bourbon"),
        files={"image": ("big.png", sample_bytes("old_tom_bourbon"), "image/png")},
    )
    assert response.status_code == 422
    assert "larger than" in response.text


def test_unknown_image_in_demo_mode_is_explained() -> None:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (900, 1200), "white").save(out, format="PNG")
    response = client().post(
        "/check",
        data=form_for("old_tom_bourbon"),
        files={"image": ("mine.png", out.getvalue(), "image/png")},
    )
    assert response.status_code == 422
    assert "Demo mode can only read the sample labels" in response.text


@pytest.mark.parametrize(("retryable", "status"), [(True, 503), (False, 422)])
def test_extraction_failures_are_explained(retryable: bool, status: int) -> None:
    app = create_app(
        Settings(provider="fixture"),
        extractor=FailingExtractor(ExtractionError("Try again later.", retryable=retryable)),
    )
    data = form_for("old_tom_bourbon") | {"sample": "old_tom_bourbon"}
    response = TestClient(app).post("/check", data=data)
    assert response.status_code == status
    assert "Try again later." in response.text
    assert 'value="OLD TOM DISTILLERY"' in response.text


def test_app_refuses_to_start_without_a_key() -> None:
    with pytest.raises(RuntimeError, match="LV_ANTHROPIC_API_KEY is not set"):
        create_app(Settings(provider="anthropic", anthropic_api_key=None))
