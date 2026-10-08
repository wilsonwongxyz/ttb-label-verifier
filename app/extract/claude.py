import base64
import logging
import time
from typing import Literal

import anthropic
from anthropic import AsyncAnthropic

from app.config import Settings
from app.extract.base import ExtractionError
from app.extract.prompt import SYSTEM_PROMPT, user_instruction
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import BeverageType

log = logging.getLogger(__name__)

_TRY_AGAIN = "We couldn't check this label just now. Please try again."


class ClaudeExtractor:
    """Reads a label with one structured-output call to Claude."""

    def __init__(
        self,
        client: AsyncAnthropic,
        *,
        model: str,
        effort: Literal["low", "medium", "high"],
        max_tokens: int,
    ) -> None:
        self._client = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens
        # Running totals, for cost reporting in evaluations.
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> "ClaudeExtractor":
        key = settings.anthropic_api_key
        if key is None or not key.get_secret_value().strip():
            raise RuntimeError(
                "LV_ANTHROPIC_API_KEY is not set. Set it, or run with LV_PROVIDER=fixture "
                "for the offline demo."
            )
        client = AsyncAnthropic(
            api_key=key.get_secret_value().strip(),
            # Explicit, so an ANTHROPIC_BASE_URL meant for other tools is never picked up.
            base_url=settings.anthropic_base_url,
            timeout=settings.extract_timeout_s,
            max_retries=settings.extract_max_retries,
        )
        return cls(
            client,
            model=settings.model,
            effort=settings.effort,
            max_tokens=settings.max_output_tokens,
        )

    async def extract(self, image: PreparedImage, beverage_type: BeverageType) -> LabelExtraction:
        started = time.perf_counter()
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                output_config={"effort": self._effort},
                output_format=LabelExtraction,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64.standard_b64encode(image.data).decode(),
                                },
                            },
                            {"type": "text", "text": user_instruction(beverage_type)},
                        ],
                    }
                ],
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            log.error("extraction auth failure: %s", type(exc).__name__)
            raise ExtractionError(
                "The label checker isn't set up correctly. Please contact the administrator.",
                retryable=False,
            ) from exc
        except anthropic.BadRequestError as exc:
            log.error("extraction rejected by API: status=%s", exc.status_code)
            raise ExtractionError(
                "We couldn't process this image. Please try a different photo.", retryable=False
            ) from exc
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            # Timeouts, connection failures, 429 and 5xx, after the SDK's own retry.
            log.warning("extraction unavailable: %s", type(exc).__name__)
            raise ExtractionError(_TRY_AGAIN, retryable=True) from exc

        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        log.info(
            "extraction model=%s ms=%d in=%d out=%d stop=%s",
            self._model,
            (time.perf_counter() - started) * 1000,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            # A refusal or a truncated answer is no reading at all: hand every field to a
            # person rather than guess (TECHNICAL_DESIGN.md §5.4).
            log.warning("extraction unusable: stop_reason=%s", response.stop_reason)
            return LabelExtraction.unreadable()
        return response.parsed_output
