import csv
import io

import pytest

from app.batch.csv_io import (
    SpreadsheetError,
    parse_applications,
    safe_cell,
    template_csv,
    write_rows,
)
from app.rules.models import BeverageType

HEADER = (
    "image_filename,beverage_type,brand_name,class_type,alcohol_content,net_contents,"
    "bottler_name_address,imported,country_of_origin\n"
)
GOOD = 'a.jpg,distilled_spirits,OLD TOM,Bourbon,45%,750 mL,"Bottled by X, KY",no,\n'


def test_parses_a_good_row() -> None:
    (row,) = parse_applications((HEADER + GOOD).encode())
    assert row.row_number == 2
    assert row.image_filename == "a.jpg"
    assert row.problem is None
    assert row.application is not None
    assert row.application.brand_name == "OLD TOM"
    assert row.application.bottler_name_address == "Bottled by X, KY"
    assert not row.application.imported


def test_template_round_trips() -> None:
    (row,) = parse_applications(template_csv().encode())
    assert row.application is not None
    assert row.application.brand_name == "OLD TOM DISTILLERY"


def test_excel_byte_order_mark_and_friendly_headers() -> None:
    raw = (
        "﻿Image Filename,Beverage Type,Brand Name,Class/Type,Alcohol Content,Net Contents\n"
        "a.jpg,Beer,Hop Co,IPA,,12 fl oz\n"
    ).encode()
    (row,) = parse_applications(raw)
    assert row.application is not None
    assert row.application.beverage_type == BeverageType.MALT_BEVERAGE


def test_windows_1252_is_accepted() -> None:
    raw = (HEADER + "a.jpg,wine,Château,Red Wine,13%,750 mL,,,\n").encode("cp1252")
    (row,) = parse_applications(raw)
    assert row.application is not None
    assert row.application.brand_name == "Château"


@pytest.mark.parametrize(
    ("value", "imported"), [("yes", True), ("Y", True), ("1", True), ("no", False), ("", False)]
)
def test_imported_flag(value: str, imported: bool) -> None:
    raw = HEADER + f"a.jpg,wine,B,Red,13%,750 mL,,{value},France\n"
    (row,) = parse_applications(raw.encode())
    assert row.application is not None
    assert row.application.imported is imported


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        (",wine,B,Red,13%,750 mL,,,\n", "No image filename given."),
        ("a.jpg,whisky,B,Red,13%,750 mL,,,\n", "beverage_type must be"),
        ("a.jpg,wine,,Red,13%,750 mL,,,\n", "Enter the brand name"),
        ("a.jpg,distilled_spirits,B,Gin,,750 mL,,,\n", "spirits must state it"),
        ("a.jpg,wine,B,Red,13%,750 mL,,yes,\n", "country of origin"),
    ],
)
def test_bad_rows_are_reported_not_fatal(line: str, problem: str) -> None:
    rows = parse_applications((HEADER + line + GOOD).encode())
    assert len(rows) == 2
    assert rows[0].application is None
    assert rows[0].problem is not None and problem in rows[0].problem
    assert rows[1].problem is None


def test_blank_lines_are_skipped() -> None:
    rows = parse_applications((HEADER + ",,,,,,,,\n" + GOOD).encode())
    assert len(rows) == 1


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "empty"),
        (
            b"image_filename,brand_name\na.jpg,X\n",
            "missing these columns: beverage_type, class_type, net_contents",
        ),
        (HEADER.encode(), "no applications"),
        (b"\xff\xfe\x00\x81\x8d", "couldn't be read"),
    ],
)
def test_unusable_spreadsheets(raw: bytes, message: str) -> None:
    with pytest.raises(SpreadsheetError, match=message):
        parse_applications(raw)


@pytest.mark.parametrize(
    ("value", "safe"),
    [
        ('=HYPERLINK("x")', '\'=HYPERLINK("x")'),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("OLD TOM", "OLD TOM"),
        ("", ""),
    ],
)
def test_safe_cell(value: str, safe: str) -> None:
    assert safe_cell(value) == safe


def test_write_rows_escapes_every_cell() -> None:
    text = write_rows(["a", "b"], [["=1+1", "fine"]])
    assert list(csv.reader(io.StringIO(text))) == [["a", "b"], ["'=1+1", "fine"]]
