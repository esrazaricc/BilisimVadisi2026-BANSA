from dataclasses import dataclass

from src.local_agent_contract import (
    validate_agent_decision,
)

from src.local_agent_orchestrator import (
    AgentPlan,
)

from src.local_agent_runtime import (
    run_local_agent,
)

from src.local_agent_tools import (
    AgentToolResult,
)


def _decision():

    return validate_agent_decision(
        {
            "intent":
                "campaign_compare",

            "banks": [
                "Kuveyt Turk",
                "Turkiye Finans",
            ],

            "topic":
                "market",

            "product":
                None,

            "amount":
                5000,

            "maturity_months":
                None,

            "customer_scope":
                "all",

            "time_scope":
                "current",
        }
    )


class FakeOrchestrator:

    def __init__(
        self,
        plan,
    ):
        self.plan_value = plan
        self.called = False

    def plan(
        self,
        question,
        *,
        history=None,
    ):
        self.called = True
        return self.plan_value


def test_disabled_runtime_never_executes_tool():

    plan = AgentPlan(
        status="disabled",
        decision=None,
        tool_name=None,
        reasons=(
            "local_agent_disabled",
        ),
    )

    orchestrator = FakeOrchestrator(
        plan
    )

    called = {
        "tool":
            False
    }

    def fake_executor(
        *args,
        **kwargs,
    ):
        called[
            "tool"
        ] = True

        raise AssertionError(
            "tool should not run"
        )

    result = run_local_agent(
        "test",
        orchestrator=orchestrator,
        tool_executor=fake_executor,
    )

    assert result.status == "disabled"
    assert called["tool"] is False


def test_fallback_plan_never_executes_tool():

    plan = AgentPlan(
        status="fallback",
        decision=None,
        tool_name=None,
        reasons=(
            "planner_error",
        ),
    )

    called = {
        "tool":
            False
    }

    def fake_executor(
        *args,
        **kwargs,
    ):
        called[
            "tool"
        ] = True

        raise AssertionError(
            "tool should not run"
        )

    result = run_local_agent(
        "test",
        orchestrator=FakeOrchestrator(
            plan
        ),
        tool_executor=fake_executor,
    )

    assert result.status == "fallback"
    assert called["tool"] is False


def test_valid_plan_executes_verified_tool():

    decision = _decision()

    plan = AgentPlan(
        status="planned",
        decision=decision,
        tool_name="compare_campaigns",
        reasons=(
            "validated_local_agent_plan",
        ),
    )

    calls = {}

    def fake_executor(
        received_decision,
        *,
        question,
        db_path,
        as_of,
    ):

        calls[
            "decision"
        ] = received_decision

        calls[
            "question"
        ] = question

        return AgentToolResult(
            status="ok",
            tool_name="compare_campaigns",
            data={
                "candidate_count":
                    2,
            },
            reasons=(
                "verified_campaign_comparison",
            ),
        )

    result = run_local_agent(
        (
            "Kuveyt Turk ile Turkiye Finans "
            "market kampanyalarini karsilastir."
        ),
        orchestrator=FakeOrchestrator(
            plan
        ),
        tool_executor=fake_executor,
    )

    assert result.status == "ok"

    assert (
        result.tool_result.tool_name
        ==
        "compare_campaigns"
    )

    assert (
        calls[
            "decision"
        ]
        ==
        decision
    )

    assert (
        "market"
        in calls[
            "question"
        ]
    )


def test_tool_failure_falls_back():

    decision = _decision()

    plan = AgentPlan(
        status="planned",
        decision=decision,
        tool_name="compare_campaigns",
        reasons=(
            "validated_local_agent_plan",
        ),
    )

    def fake_executor(
        *args,
        **kwargs,
    ):

        return AgentToolResult(
            status="fallback",
            tool_name="compare_campaigns",
            data=None,
            reasons=(
                "tool_execution_error",
            ),
        )

    result = run_local_agent(
        "test",
        orchestrator=FakeOrchestrator(
            plan
        ),
        tool_executor=fake_executor,
    )

    assert result.status == "fallback"

    assert (
        result.reasons
        ==
        (
            "tool_execution_error",
        )
    )


def test_tool_plan_mismatch_fails_closed():

    decision = _decision()

    plan = AgentPlan(
        status="planned",
        decision=decision,
        tool_name="compare_campaigns",
        reasons=(
            "validated_local_agent_plan",
        ),
    )

    def fake_executor(
        *args,
        **kwargs,
    ):

        return AgentToolResult(
            status="ok",
            tool_name="get_finance_fact",
            data={
                "unsafe":
                    True,
            },
            reasons=(
                "wrong_tool",
            ),
        )

    result = run_local_agent(
        "test",
        orchestrator=FakeOrchestrator(
            plan
        ),
        tool_executor=fake_executor,
    )

    assert result.status == "fallback"

    assert (
        result.reasons
        ==
        (
            "tool_plan_mismatch",
        )
    )


def test_planner_exception_fails_closed():

    class BrokenOrchestrator:

        def plan(
            self,
            *args,
            **kwargs,
        ):
            raise RuntimeError(
                "boom"
            )

    result = run_local_agent(
        "test",
        orchestrator=(
            BrokenOrchestrator()
        ),
    )

    assert result.status == "fallback"

    assert (
        result.reasons
        ==
        (
            "planner_runtime_error:RuntimeError",
        )
    )
