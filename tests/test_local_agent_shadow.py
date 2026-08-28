from types import SimpleNamespace

import src.chatbot_response_service as service


def _legacy_response():

    return service.BansaResponse(
        question="test",
        route="campaign_compare",
        answer_mode="campaign",
        text="LEGACY VERIFIED ANSWER",
        backend="deterministic_test",
        safe=True,
        qwen_used=False,
        finance_renderer_used=False,
        evidence_ids=tuple(),
        finance_result_count=0,
        missing_fields=tuple(),
        reasons=tuple(),
    )


def test_shadow_disabled_does_not_run_agent(
    monkeypatch,
):

    expected = _legacy_response()

    monkeypatch.setattr(
        service,
        "_ask_bansa_before_local_agent_shadow_v1",
        lambda *args, **kwargs:
            expected,
    )

    monkeypatch.setenv(
        "BANSA_LOCAL_AGENT_SHADOW_ENABLED",
        "0",
    )

    called = {
        "agent":
            False,
    }

    def forbidden_agent(
        question,
    ):
        called["agent"] = True
        raise AssertionError(
            "shadow agent must not run"
        )

    monkeypatch.setattr(
        service,
        "_run_local_agent_shadow_v1",
        forbidden_agent,
    )

    actual = service.ask_bansa(
        "test"
    )

    assert actual is expected
    assert called["agent"] is False

    trace = (
        service
        .get_local_agent_shadow_trace()
    )

    assert trace["enabled"] is False
    assert trace["status"] == "disabled"


def test_shadow_never_replaces_existing_answer(
    monkeypatch,
):

    expected = _legacy_response()

    monkeypatch.setattr(
        service,
        "_ask_bansa_before_local_agent_shadow_v1",
        lambda *args, **kwargs:
            expected,
    )

    monkeypatch.setenv(
        "BANSA_LOCAL_AGENT_SHADOW_ENABLED",
        "1",
    )

    decision = SimpleNamespace(
        intent="campaign_compare",
        banks=(
            "Kuveyt T\u00fcrk",
            "T\u00fcrkiye Finans",
        ),
        topic="market",
        product=None,
        amount=5000,
        maturity_months=None,
        customer_scope=None,
        time_scope="current",
    )

    plan = SimpleNamespace(
        status="planned",
        decision=decision,
        tool_name="compare_campaigns",
    )

    tool_result = SimpleNamespace(
        status="ok",
        reasons=(
            "verified_canonical_market_runtime",
        ),
        data={
            "universe":
                "canonical_market",
        },
    )

    run = SimpleNamespace(
        status="ok",
        plan=plan,
        tool_result=tool_result,
        reasons=(
            "validated_plan_executed",
            "verified_tool_result",
        ),
    )

    monkeypatch.setattr(
        service,
        "_run_local_agent_shadow_v1",
        lambda question:
            run,
    )

    actual = service.ask_bansa(
        "test"
    )

    # The shadow agent MUST NOT change user output.
    assert actual is expected

    assert (
        actual.text
        ==
        "LEGACY VERIFIED ANSWER"
    )

    trace = (
        service
        .get_local_agent_shadow_trace()
    )

    assert trace["enabled"] is True
    assert trace["status"] == "ok"

    assert (
        trace["intent"]
        ==
        "campaign_compare"
    )

    assert (
        trace["banks"]
        ==
        (
            "Kuveyt T\u00fcrk",
            "T\u00fcrkiye Finans",
        )
    )

    assert trace["topic"] == "market"

    assert (
        trace["tool_name"]
        ==
        "compare_campaigns"
    )

    assert (
        trace["tool_universe"]
        ==
        "canonical_market"
    )

    assert (
        trace["legacy_backend"]
        ==
        "deterministic_test"
    )


def test_shadow_failure_still_returns_existing_answer(
    monkeypatch,
):

    expected = _legacy_response()

    monkeypatch.setattr(
        service,
        "_ask_bansa_before_local_agent_shadow_v1",
        lambda *args, **kwargs:
            expected,
    )

    monkeypatch.setenv(
        "BANSA_LOCAL_AGENT_SHADOW_ENABLED",
        "1",
    )

    def broken_agent(
        question,
    ):
        raise RuntimeError(
            "boom"
        )

    monkeypatch.setattr(
        service,
        "_run_local_agent_shadow_v1",
        broken_agent,
    )

    actual = service.ask_bansa(
        "test"
    )

    assert actual is expected

    trace = (
        service
        .get_local_agent_shadow_trace()
    )

    assert (
        trace["status"]
        ==
        "shadow_error"
    )

    assert (
        trace["error"]
        ==
        "RuntimeError"
    )

    assert (
        actual.text
        ==
        "LEGACY VERIFIED ANSWER"
    )
