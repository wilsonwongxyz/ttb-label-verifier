"""What the vision model returns: a verbatim transcription of the label, never a verdict.

The extractor is never shown the application values (see TECHNICAL_DESIGN.md §2), so
everything here describes only what is printed on the label. Every field is required so
the model must account for each one explicitly; the descriptions are part of the prompt.
"""

from typing import Literal, Self

from pydantic import BaseModel, Field

Legibility = Literal["clear", "partial", "unreadable", "absent"]
ImageQuality = Literal["good", "fair", "poor", "unusable"]
QualityIssue = Literal["glare", "blur", "angle", "low_resolution", "cropped", "obstructed"]
BoldAssessment = Literal["yes", "no", "unsure"]

_LEGIBILITY = (
    "clear: fully readable. partial: some characters uncertain. "
    "unreadable: present but cannot be read. absent: not on the label."
)


class ReadValue(BaseModel):
    """One field as printed on the label."""

    text: str | None = Field(
        description="Exactly as printed, including case, punctuation and spelling mistakes. "
        "Do not correct or complete it. null if absent or unreadable."
    )
    legibility: Legibility = Field(description=_LEGIBILITY)


class WarningRead(BaseModel):
    """The government health warning statement as printed on the label."""

    full_text: str | None = Field(
        description="The whole warning statement exactly as printed, from its first word to "
        "its last, with line breaks replaced by single spaces. Copy wording, case and "
        "punctuation exactly even if they differ from the standard statement; never fix or "
        "complete it. null if there is no warning."
    )
    prefix_as_printed: str | None = Field(
        description='The lead-in words exactly as printed, e.g. "GOVERNMENT WARNING:" or '
        '"Government Warning:". null if the statement has no such lead-in.'
    )
    prefix_looks_bold: BoldAssessment = Field(
        description="Whether the lead-in words are printed in a visibly heavier (bold) weight "
        "than the rest of the statement."
    )
    legibility: Legibility = Field(description=_LEGIBILITY)


class LabelExtraction(BaseModel):
    is_alcohol_label: bool = Field(
        description="Whether the image shows an alcohol beverage label at all."
    )
    image_quality: ImageQuality = Field(
        description="How well the label can be read overall. unusable: too poor to read."
    )
    quality_issues: list[QualityIssue] = Field(
        description="Problems that make parts of the label hard to read."
    )
    brand_name: ReadValue = Field(description='The brand name, e.g. "OLD TOM DISTILLERY".')
    class_type: ReadValue = Field(
        description='The class/type designation, e.g. "Kentucky Straight Bourbon Whiskey". '
        "Not the brand name."
    )
    alcohol_content: ReadValue = Field(
        description='The full alcohol statement, e.g. "45% Alc./Vol. (90 Proof)".'
    )
    net_contents: ReadValue = Field(description='The volume statement, e.g. "750 mL".')
    bottler_name_address: ReadValue = Field(
        description="The bottler, producer or importer statement with name and address, "
        'e.g. "Bottled by Old Tom Distillery, Bardstown, Kentucky".'
    )
    country_of_origin: ReadValue = Field(
        description='The country of origin statement, e.g. "Product of Scotland".'
    )
    government_warning: WarningRead

    @classmethod
    def unreadable(cls) -> Self:
        """Stand-in when the model gives no usable reading: every field needs a person."""
        field = ReadValue(text=None, legibility="unreadable")
        return cls(
            is_alcohol_label=True,
            image_quality="poor",
            quality_issues=[],
            brand_name=field,
            class_type=field,
            alcohol_content=field,
            net_contents=field,
            bottler_name_address=field,
            country_of_origin=field,
            government_warning=WarningRead(
                full_text=None,
                prefix_as_printed=None,
                prefix_looks_bold="unsure",
                legibility="unreadable",
            ),
        )
