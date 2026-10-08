from app.config import Settings
from app.extract.base import LabelExtractor


def build_extractor(settings: Settings) -> LabelExtractor:
    """The one place that decides which model provider the app talks to."""
    if settings.provider == "fixture":
        from app.extract.fixture import FixtureExtractor

        return FixtureExtractor.from_dir(settings.fixtures_dir)

    from app.extract.claude import ClaudeExtractor

    return ClaudeExtractor.from_settings(settings)
