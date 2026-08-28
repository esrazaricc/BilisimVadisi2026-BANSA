# BANSA_LOCAL_LLM_CLIENT_V1

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse

import requests


DEFAULT_BASE_URL = (
    "http://127.0.0.1:8000/v1"
)

DEFAULT_MODEL = (
    "Qwen/Qwen3-30B-A3B-Instruct-2507"
)


def _is_loopback_url(
    value: str,
) -> bool:

    parsed = urlparse(
        str(value or "").strip()
    )

    host = str(
        parsed.hostname
        or ""
    ).strip().casefold()

    return (
        parsed.scheme
        in {
            "http",
            "https",
        }
        and
        host
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    )


@dataclass(
    frozen=True
)
class LocalLLMConfig:

    base_url: str = (
        DEFAULT_BASE_URL
    )

    model: str = (
        DEFAULT_MODEL
    )

    timeout_seconds: float = 45.0

    @classmethod
    def from_env(
        cls,
    ) -> "LocalLLMConfig":

        base_url = str(
            os.getenv(
                "BANSA_LOCAL_LLM_BASE_URL",
                DEFAULT_BASE_URL,
            )
            or DEFAULT_BASE_URL
        ).strip().rstrip("/")

        model = str(
            os.getenv(
                "BANSA_LOCAL_LLM_MODEL",
                DEFAULT_MODEL,
            )
            or DEFAULT_MODEL
        ).strip()

        timeout_raw = str(
            os.getenv(
                "BANSA_LOCAL_LLM_TIMEOUT_SECONDS",
                "45",
            )
            or "45"
        ).strip()

        try:
            timeout = float(
                timeout_raw
            )
        except ValueError:
            timeout = 45.0

        return cls(
            base_url=base_url,
            model=model,
            timeout_seconds=max(
                1.0,
                timeout,
            ),
        )


class LocalLLMClient:

    def __init__(
        self,
        config: LocalLLMConfig | None = None,
        *,
        session=None,
    ):

        self.config = (
            config
            or LocalLLMConfig.from_env()
        )

        if not _is_loopback_url(
            self.config.base_url
        ):
            raise ValueError(
                "BANSA local LLM endpoint must "
                "be loopback-only"
            )

        self._session = (
            session
            or requests
        )

    @property
    def model(
        self,
    ) -> str:

        return self.config.model

    def chat(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict:

        payload = {
            "model":
                self.config.model,

            "messages":
                list(
                    messages
                ),

            "temperature":
                float(
                    temperature
                ),

            "max_tokens":
                int(
                    max_tokens
                ),
        }

        if tools is not None:
            payload[
                "tools"
            ] = list(
                tools
            )

        if tool_choice is not None:
            payload[
                "tool_choice"
            ] = tool_choice

        response = (
            self._session.post(
                (
                    self.config.base_url
                    + "/chat/completions"
                ),
                json=payload,
                timeout=(
                    self.config
                    .timeout_seconds
                ),
            )
        )

        if (
            int(
                response.status_code
            )
            != 200
        ):
            raise RuntimeError(
                "Local LLM HTTP "
                + str(
                    response.status_code
                )
            )

        data = response.json()

        choices = (
            data.get(
                "choices"
            )
            or []
        )

        if not choices:
            raise RuntimeError(
                "Local LLM returned no choices"
            )

        message = (
            choices[0].get(
                "message"
            )
            or {}
        )

        if not isinstance(
            message,
            dict,
        ):
            raise RuntimeError(
                "Local LLM returned invalid message"
            )

        finish_reason = str(
            choices[0].get(
                "finish_reason"
            )
            or ""
        ).strip()

        if finish_reason:

            message = dict(
                message
            )

            message[
                "_finish_reason"
            ] = finish_reason

        return message

    def models(
        self,
    ) -> dict:

        response = (
            self._session.get(
                (
                    self.config.base_url
                    + "/models"
                ),
                timeout=(
                    self.config
                    .timeout_seconds
                ),
            )
        )

        if (
            int(
                response.status_code
            )
            != 200
        ):
            raise RuntimeError(
                "Local LLM models HTTP "
                + str(
                    response.status_code
                )
            )

        return response.json()
