import os

import src.chatbot_grounded_naturalizer as naturalizer


def test_evren_marker_installed():

    source = open(
        "src/chatbot_grounded_naturalizer.py",
        "r",
        encoding="utf-8",
    ).read()

    assert (
        "BANSA_EVREN_FIRST_NATURALIZER_V1"
        in source
    )


def test_api_key_is_not_hardcoded():

    source = open(
        "src/chatbot_grounded_naturalizer.py",
        "r",
        encoding="utf-8",
    ).read()

    assert (
        "sk-evren-"
        not in source
    )

    assert (
        "EVREN_API_KEY"
        in source
    )


def test_pytest_external_provider_is_disabled():

    assert (
        "PYTEST_CURRENT_TEST"
        in os.environ
    )

    assert (
        naturalizer
        ._evren_enabled_v1()
        is False
    )


def test_evren_defaults_are_expected():

    (
        key,
        base,
        model,
        timeout,
    ) = (
        naturalizer
        ._evren_config_v1()
    )

    assert (
        base
        ==
        "https://evren-llmapi.ssyz.org.tr/v1"
    )

    assert (
        model
        ==
        "llm-fast"
    )

    assert timeout >= 2
