import csv
import io
import time
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.samples import sample, sample_bytes, sample_entries

NAMES = [entry["name"] for entry in sample_entries()]


def app(**settings: Any) -> TestClient:
    return TestClient(create_app(Settings(provider="fixture", **settings)))


def spreadsheet(names: list[str]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
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
    )
    for name in names:
        a = sample(name)["application"]
        writer.writerow(
            [
                f"{name}.png",
                a["beverage_type"],
                a["brand_name"],
                a["class_type"],
                a["alcohol_content"] or "",
                a["net_contents"],
                a["bottler_name_address"] or "",
                "yes" if a["imported"] else "no",
                a["country_of_origin"] or "",
            ]
        )
    return out.getvalue().encode()


def wait_until_finished(client: TestClient, url: str) -> str:
    for _ in range(100):
        text = client.get(url + "/table").text
        if 'data-finished="yes"' in text:
            return client.get(url).text
        time.sleep(0.02)
    raise AssertionError("batch didn't finish")


def upload(client: TestClient, names: list[str], sheet: bytes | None = None) -> Any:
    files = [("images", (f"{n}.png", sample_bytes(n), "image/png")) for n in names]
    files.append(("spreadsheet", ("apps.csv", sheet or spreadsheet(names), "text/csv")))
    return client.post("/batch", files=files, follow_redirects=False)


def test_batch_page_and_template() -> None:
    with app() as client:
        assert "Check many labels" in client.get("/batch").text
        template = client.get("/batch/template.csv")
        assert template.headers["content-type"].startswith("text/csv")
        assert template.text.startswith("image_filename,")


def test_uploaded_batch_runs_and_sorts_problems_first() -> None:
    with app() as client:
        response = upload(client, NAMES)
        assert response.status_code == 303
        url = response.headers["location"]
        page = wait_until_finished(client, url)

    assert "5 of 5" in page
    assert "<strong>3</strong> needs attention" not in page  # grammar: "need"
    assert "<strong>3</strong> need attention" in page
    issues = page.index("copper_ridge_vodka_wrong_abv.png")
    clear = page.index("old_tom_bourbon.png")
    assert issues < clear


def test_bad_rows_and_stray_images_are_listed_not_fatal() -> None:
    sheet = spreadsheet(["old_tom_bourbon"]) + b"ghost.png,wine,Ghost,Red,13%,750 mL,,,\n"
    with app() as client:
        response = upload(client, ["old_tom_bourbon", "stones_throw_gin"], sheet)
        page = wait_until_finished(client, response.headers["location"])
    assert "Not checked" in page
    assert "No uploaded image is named “ghost.png”." in page
    assert "No spreadsheet row names this image." in page
    assert "All clear" in page


def test_filter_and_item_detail() -> None:
    with app() as client:
        url = upload(client, NAMES).headers["location"]
        wait_until_finished(client, url)
        clear_only = client.get(url + "?show=all_clear").text
        assert "old_tom_bourbon.png" in clear_only
        assert "copper_ridge_vodka_wrong_abv.png" not in clear_only

        attention = client.get(url + "?show=attention").text
        assert "copper_ridge_vodka_wrong_abv.png" in attention
        assert "old_tom_bourbon.png" not in attention

        detail_link = url + "/items/0"
        detail = client.get(detail_link).text
        assert "Back to the batch" in detail
        assert "old_tom_bourbon.png" in detail


def test_export_csv() -> None:
    with app() as client:
        url = upload(client, NAMES).headers["location"]
        wait_until_finished(client, url)
        export = client.get(url + "/results.csv")
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert len(rows) == 5
    by_file = {r["image_filename"]: r for r in rows}
    vodka = by_file["copper_ridge_vodka_wrong_abv.png"]
    assert vodka["result"] == "Issues found"
    assert vodka["Alcohol content"] == "mismatch"
    assert "Label says 40%" in vodka["issues"]
    assert by_file["old_tom_bourbon.png"]["result"] == "All clear"


def test_example_batch() -> None:
    with app() as client:
        response = client.post("/batch/example", follow_redirects=False)
        page = wait_until_finished(client, response.headers["location"])
    assert "5 of 5" in page


def test_upload_problems_are_explained() -> None:
    with app() as client:
        no_sheet = client.post(
            "/batch", files=[("images", ("a.png", sample_bytes(NAMES[0]), "image/png"))]
        )
        assert no_sheet.status_code == 422
        assert "Choose the spreadsheet" in no_sheet.text

        bad_sheet = upload(client, NAMES[:1], b"just,some\ncolumns,here\n")
        assert bad_sheet.status_code == 422
        assert "missing these columns" in bad_sheet.text

    with app(batch_max_files=2) as client:
        too_many = upload(client, NAMES[:3])
        assert too_many.status_code == 422
        assert "the limit is 2 per batch" in too_many.text


def test_unknown_batch_is_a_friendly_404() -> None:
    with app() as client:
        response = client.get("/batch/nope")
    assert response.status_code == 404
    assert "expired" in response.text
    assert "<h1>" in response.text
