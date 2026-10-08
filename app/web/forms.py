"""The application form: what the agent types in, validated into ApplicationData."""

from dataclasses import dataclass, field

from app.rules.models import ApplicationData, BeverageType

BEVERAGE_CHOICES = [
    (BeverageType.DISTILLED_SPIRITS, "Distilled spirits"),
    (BeverageType.WINE, "Wine"),
    (BeverageType.MALT_BEVERAGE, "Beer / malt beverage"),
]

TEXT_FIELDS = [
    ("brand_name", "Brand name", True),
    ("class_type", "Class / type", True),
    ("alcohol_content", "Alcohol content", False),
    ("net_contents", "Net contents", True),
    ("bottler_name_address", "Bottler name and address", False),
    ("country_of_origin", "Country of origin", False),
]


@dataclass
class ApplicationForm:
    values: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_application(cls, application: ApplicationData) -> "ApplicationForm":
        values = {name: getattr(application, name) or "" for name, _, _ in TEXT_FIELDS}
        values["beverage_type"] = application.beverage_type.value
        values["imported"] = "on" if application.imported else ""
        return cls(values=values)

    @classmethod
    def from_submission(cls, data: dict[str, str]) -> "ApplicationForm":
        values = {name: data.get(name, "").strip() for name, _, _ in TEXT_FIELDS}
        values["beverage_type"] = data.get("beverage_type", "")
        values["imported"] = "on" if data.get("imported") else ""
        return cls(values=values)

    def validate(self) -> ApplicationData | None:
        """The application if the form is complete, otherwise None with ``errors`` filled in."""
        self.errors = {}
        try:
            beverage_type = BeverageType(self.values.get("beverage_type", ""))
        except ValueError:
            self.errors["beverage_type"] = "Choose the type of drink."
            beverage_type = BeverageType.DISTILLED_SPIRITS

        for name, label, required in TEXT_FIELDS:
            if required and not self.values.get(name):
                self.errors[name] = f"Enter the {label.lower()} from the application."
        if beverage_type == BeverageType.DISTILLED_SPIRITS and not self.values.get(
            "alcohol_content"
        ):
            self.errors["alcohol_content"] = "Enter the alcohol content; spirits must state it."
        imported = self.values.get("imported") == "on"
        if imported and not self.values.get("country_of_origin"):
            self.errors["country_of_origin"] = "Enter the country of origin for imported products."

        if self.errors:
            return None
        return ApplicationData(
            beverage_type=beverage_type,
            brand_name=self.values["brand_name"],
            class_type=self.values["class_type"],
            alcohol_content=self.values.get("alcohol_content") or None,
            net_contents=self.values["net_contents"],
            bottler_name_address=self.values.get("bottler_name_address") or None,
            imported=imported,
            country_of_origin=self.values.get("country_of_origin") or None,
        )
