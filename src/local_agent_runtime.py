# BANSA_LOCAL_AGENT_RUNTIME_V1

from __future__ import annotations

from dataclasses import dataclass

from src.local_agent_orchestrator import (
    AgentPlan,
    LocalAgentOrchestrator,
)

from src.local_agent_tools import (
    AgentToolResult,
    execute_agent_decision,
)


@dataclass(
    frozen=True
)
class LocalAgentRunResult:

    status: str

    plan: AgentPlan | None

    tool_result: AgentToolResult | None

    reasons: tuple[
        str,
        ...
    ]


def run_local_agent(
    question,
    *,
    history=None,
    orchestrator=None,
    tool_executor=None,
    db_path=None,
    as_of=None,
) -> LocalAgentRunResult:

    active_orchestrator = (
        orchestrator
        or LocalAgentOrchestrator()
    )

    executor = (
        tool_executor
        or execute_agent_decision
    )

    try:

        plan = (
            active_orchestrator.plan(
                question,
                history=history,
            )
        )

    except Exception as exc:

        return LocalAgentRunResult(
            status="fallback",
            plan=None,
            tool_result=None,
            reasons=(
                (
                    "planner_runtime_error:"
                    + type(
                        exc
                    ).__name__
                ),
            ),
        )

    if (
        plan.status
        ==
        "disabled"
    ):

        return LocalAgentRunResult(
            status="disabled",
            plan=plan,
            tool_result=None,
            reasons=(
                "local_agent_disabled",
            ),
        )

    if (
        plan.status
        != "planned"
        or
        plan.decision is None
        or
        not plan.tool_name
    ):

        return LocalAgentRunResult(
            status="fallback",
            plan=plan,
            tool_result=None,
            reasons=tuple(
                plan.reasons
                or (
                    "planner_did_not_produce_safe_plan",
                )
            ),
        )

    try:

        tool_result = (
            executor(
                plan.decision,
                question=question,
                db_path=db_path,
                as_of=as_of,
            )
        )

    except Exception as exc:

        return LocalAgentRunResult(
            status="fallback",
            plan=plan,
            tool_result=None,
            reasons=(
                (
                    "tool_runtime_error:"
                    + type(
                        exc
                    ).__name__
                ),
            ),
        )

    if (
        tool_result.status
        != "ok"
    ):

        return LocalAgentRunResult(
            status="fallback",
            plan=plan,
            tool_result=tool_result,
            reasons=tuple(
                tool_result.reasons
                or (
                    "tool_execution_failed",
                )
            ),
        )

    if (
        tool_result.tool_name
        != plan.tool_name
    ):

        return LocalAgentRunResult(
            status="fallback",
            plan=plan,
            tool_result=tool_result,
            reasons=(
                "tool_plan_mismatch",
            ),
        )

    return LocalAgentRunResult(
        status="ok",
        plan=plan,
        tool_result=tool_result,
        reasons=(
            "validated_plan_executed",
            "verified_tool_result",
        ),
    )
