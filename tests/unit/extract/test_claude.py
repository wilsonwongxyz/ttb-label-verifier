import base64
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.extract.base import ExtractionError
from app.extract.claude import ClaudeExtractor
from app.extract.prompt import SYSTEM_PROMPT
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import BeverageType
from tests.samples import sample

IMAGE = PreparedImage(data=b"jpeg-bytes", width=900, height=1200, source_sha256="abc")
READING = LabelExtraction.model_validate(sample("old_tom_bourbon")["extraction"])


@dataclass
class Usage:
    input_tokens: int = 1600
    output_tokens: int = 400


@dataclass
class Response:
    parsed_output: LabelExtraction | None
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


class FakeMessages:
    def __init__(self, outcome: Response | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeClient:
    def __init__(self, outcome: Response | Exception) -> None:
        self.messages = FakeMessages(outcome)


def extractor(outcome: Response | Exception) -> tuple[ClaudeExtractor, FakeMessages]:
    client = FakeClient(outcome)
    return (
        ClaudeExtractor(client, model="claude-haiku-5-5", effort="low", max_tokens=2048),  # type: ignore[arg-type]
        client.messages,
    )


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx2.Response(status, request=request), body=None)


async def test_returns_the_parsed_reading() -> None:
    ex, _ = extractor(Response(parsed_output=READING))
    assert await ex.extract(IMAGE, BeverageType.DISTILLED_SPIRITS) == READING


async def test_sends_one_structured_image_request() -> None:
    ex, messages = extractor(Response(parsed_output=READING))
    await ex.extract(IMAGE, BeverageType.WINE)

    (call,) = messages.calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_format"] is LabelExtraction
    assert call["output_config"] == {"effort": "low"}
    assert call["system"] == SYSTEM_PROMPT
    image_block, text_block = call["messages"][0]["content"]
    assert image_block["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": base64.standard_b64encode(b"jpeg-bytes").decode(),
    }
    assert "wine" in text_block["text"]


async def test_never_shows_the_model_application_values() -> None:
    ex, messages = extractor(Response(parsed_output=READING))
    await ex.extract(IMAGE, BeverageType.DISTILLED_SPIRITS)
    sent = repr(messages.calls[0])
    for value in ("OLD TOM", "Bourbon", "45%", "750"):
        assert value not in sent


@pytest.mark.parametrize(
    "response",
    [
        Response(parsed_output=None, stop_reason="refusal"),
        Response(parsed_output=None, stop_reason="max_tokens"),
        Response(parsed_output=READING, stop_reason="max_tokens"),
    ],
)
async def test_unusable_answers_become_an_unreadable_reading(response: Response) -> None:
    ex, _ = extractor(response)
    assert await ex.extract(IMAGE, BeverageType.DISTILLED_SPIRITS) == (LabelExtraction.unreadable())


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")),
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.InternalServerError, 529),
    ],
)
async def test_transient_failures_are_retryable(error: Exception) -> None:
    ex, _ = extractor(error)
    with pytest.raises(ExtractionError) as caught:
        await ex.extract(IMAGE, BeverageType.DISTILLED_SPIRITS)
    assert caught.value.retryable
    assert caught.value.message == "We couldn't check this label just now. Please try again."


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (status_error(anthropic.AuthenticationError, 401), "isn't set up correctly"),
        (status_error(anthropic.PermissionDeniedError, 403), "isn't set up correctly"),
        (status_error(anthropic.BadRequestError, 400), "try a different photo"),
    ],
)
async def test_permanent_failures_are_not_retryable(error: Exception, message: str) -> None:
    ex, _ = extractor(error)
    with pytest.raises(ExtractionError, match=message) as caught:
        await ex.extract(IMAGE, BeverageType.DISTILLED_SPIRITS)
    assert not caught.value.retryable


@pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("  ")])
def test_requires_an_api_key(key: SecretStr | None) -> None:
    with pytest.raises(RuntimeError, match="LV_ANTHROPIC_API_KEY is not set"):
        ClaudeExtractor.from_settings(Settings(anthropic_api_key=key))


def test_client_uses_its_own_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")
    ex = ClaudeExtractor.from_settings(Settings(anthropic_api_key=SecretStr("sk-test")))
    assert str(ex._client.base_url).rstrip("/") == "https://api.anthropic.com"
