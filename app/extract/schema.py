"""What the vision model returns: a verbatim transcription of the label, never a verdict.

The extractor is never shown the application values (see TECHNICAL_DESIGN.md §2), so
everything here describes only what is printed on the label.
"""

from typing import Literal

from pydantic import BaseModel, Field

Legibility = Literal["clear", "partial", "unreadable", "absent"]
ImageQuality = Literal["good", "fair", "poor", "unusable"]
QualityIssue = Literal["glare", "blur", "angle", "low_resolution", "cropped", "obstructed"]
BoldAssessment = Literal["yes", "no", "unsure"]


class ReadValue(BaseModel):
    """One field as printed on the label."""

    text: str | None = Field(
        default=None, description="Verbatim as printed; null if not present or not visible."
    )
    legibility: Legibility = "absent"


class WarningRead(BaseModel):
    """The government health warning as printed on the label."""

    full_text: str | None = Field(
        default=None,
        description="Verbatim, original case and punctuation, line breaks replaced by spaces.",
    )
    prefix_as_printed: str | None = Field(
        default=None, description='The lead-in exactly as printed, e.g. "GOVERNMENT WARNING:".'
    )
    prefix_looks_bold: BoldAssessment = "unsure"
    legibility: Legibility = "absent"


class LabelExtraction(BaseModel):
    is_alcohol_label: bool = True
    image_quality: ImageQuality = "good"
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    brand_name: ReadValue = Field(default_factory=ReadValue)
    class_type: ReadValue = Field(default_factory=ReadValue)
    alcohol_content: ReadValue = Field(default_factory=ReadValue)
    net_contents: ReadValue = Field(default_factory=ReadValue)
    bottler_name_address: ReadValue = Field(default_factory=ReadValue)
    country_of_origin: ReadValue = Field(default_factory=ReadValue)
    government_warning: WarningRead = Field(default_factory=WarningRead)
