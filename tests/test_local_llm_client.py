from src.local_llm_client import (
    DEFAULT_MODEL,
    LocalLLMClient,
    LocalLLMConfig,
)


class FakeResponse:

    status_code = 200

    def __init__(
        self,
        payload,
    ):
        self.payload = payload

    def json(
        self,
    ):
        return self.payload


class FakeSession:

    def __init__(
        self,
    ):
        self.last_post = None

    def post(
        self,
        url,
        *,
        json,
        timeout,
    ):

        self.last_post = {
            "url":
                url,

            "json":
                json,

            "timeout":
                timeout,
        }

        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role":
                                "assistant",

                            "content":
                                None,

                            "tool_calls": [
                                {
                                    "id":
                                        "call_1",

                                    "type":
                                        "function",

                                    "function": {
                                        "name":
                                            "search_campaigns",

                                        "arguments":
                                            '{"topic":"market"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )


def test_default_config_is_local():

    config = (
        LocalLLMConfig()
    )

    assert (
        config.base_url
        ==
        "http://127.0.0.1:8000/v1"
    )

    assert (
        config.model
        ==
        DEFAULT_MODEL
    )


def test_external_endpoint_is_rejected():

    config = LocalLLMConfig(
        base_url=(
            "https://example.com/v1"
        ),
    )

    try:
        LocalLLMClient(
            config
        )
    except ValueError as exc:
        assert (
            "loopback-only"
            in str(
                exc
            )
        )
    else:
        raise AssertionError(
            "External endpoint was accepted"
        )


def test_tool_call_is_preserved():

    fake = FakeSession()

    client = LocalLLMClient(
        LocalLLMConfig(),
        session=fake,
    )

    message = client.chat(
        [
            {
                "role":
                    "user",

                "content":
                    "Market kampanyalarini karsilastir.",
            }
        ],
        tools=[
            {
                "type":
                    "function",

                "function": {
                    "name":
                        "search_campaigns",

                    "description":
                        "Search verified campaigns",

                    "parameters": {
                        "type":
                            "object",

                        "properties": {
                            "topic": {
                                "type":
                                    "string",
                            }
                        },
                    },
                },
            }
        ],
        tool_choice="auto",
    )

    assert (
        message[
            "tool_calls"
        ][0][
            "function"
        ][
            "name"
        ]
        ==
        "search_campaigns"
    )

    assert (
        fake.last_post[
            "url"
        ]
        ==
        (
            "http://127.0.0.1:8000/v1"
            "/chat/completions"
        )
    )

    assert (
        "tools"
        in fake.last_post[
            "json"
        ]
    )
