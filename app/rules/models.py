from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class BeverageType(StrEnum):
    DISTILLED_SPIRITS = "distilled_spirits"
    WINE = "wine"
    MALT_BEVERAGE = "malt_beverage"


class ApplicationData(BaseModel):
    """The values the applicant declared; what the label is checked against."""

    beverage_type: BeverageType
    brand_name: str
    class_type: str
    alcohol_content: str | None = None
    net_contents: str
    bottler_name_address: str | None = None
    imported: bool = False
    country_of_origin: str | None = None


class Verdict(StrEnum):
    MATCH = "match"
    MATCH_NOTED = "match_noted"
    NEEDS_REVIEW = "needs_review"
    MISMATCH = "mismatch"
    NOT_APPLICABLE = "n/a"


class OverallStatus(StrEnum):
    ALL_CLEAR = "all_clear"
    NEEDS_REVIEW = "needs_review"
    ISSUES_FOUND = "issues_found"
    CANT_READ = "cant_read"


class DiffSpan(BaseModel):
    """One run of a diff between the expected and the found text, for highlighting."""

    op: Literal["equal", "insert", "delete", "replace"]
    expected: str
    found: str


class FieldResult(BaseModel):
    field: str
    label: str
    verdict: Verdict
    expected: str | None
    found: str | None
    reason: str
    diff: list[DiffSpan] | None = None


class VerificationReport(BaseModel):
    status: OverallStatus
    fields: list[FieldResult]
