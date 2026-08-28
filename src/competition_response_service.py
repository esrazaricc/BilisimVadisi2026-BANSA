"""Jury-facing BANSA response service.

The competition UI imports this lightweight facade instead of importing the
whole legacy orchestration stack at module load time. Structured finance and
campaign questions therefore remain available even if an optional heavy
RAG/PostgreSQL/live-adapter dependency is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.competition_fast_router import (
    answer_fast,
    should_replace_failure_text,
    smart_fallback,
)


@dataclass(frozen=True)
class BansaResponse:
    question: str
    route: str
    answer_mode: str
    text: str
    backend: str
    safe: bool
    qwen_used: bool
    finance_renderer_used: bool
    evidence_ids: tuple[str, ...]
    finance_result_count: int
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]
    rag_guard_warnings: tuple[str, ...] = ()


def _from_fast(question: str, fast, *, qwen_used: bool = False) -> BansaResponse:
    return BansaResponse(
        question=str(question or ""),
        route=str(getattr(fast, "route", "competition_fast") or "competition_fast"),
        answer_mode=str(getattr(fast, "answer_mode", "guide") or "guide"),
        text=str(getattr(fast, "text", "") or "").strip(),
        backend=str(getattr(fast, "backend", "competition_fast_router") or "competition_fast_router"),
        safe=True,
        qwen_used=bool(qwen_used),
        finance_renderer_used=(str(getattr(fast, "answer_mode", "")) == "finance"),
        evidence_ids=tuple(),
        finance_result_count=int(getattr(fast, "finance_result_count", 0) or 0),
        missing_fields=tuple(),
        reasons=tuple(getattr(fast, "reasons", ()) or ()),
    )


def _copy_legacy(question: str, response) -> BansaResponse:
    return BansaResponse(
        question=str(getattr(response, "question", question) or question),
        route=str(getattr(response, "route", "legacy") or "legacy"),
        answer_mode=str(getattr(response, "answer_mode", "rag") or "rag"),
        text=str(getattr(response, "text", "") or "").strip(),
        backend=str(getattr(response, "backend", "legacy") or "legacy"),
        safe=bool(getattr(response, "safe", True)),
        qwen_used=bool(getattr(response, "qwen_used", False)),
        finance_renderer_used=bool(getattr(response, "finance_renderer_used", False)),
        evidence_ids=tuple(getattr(response, "evidence_ids", ()) or ()),
        finance_result_count=int(getattr(response, "finance_result_count", 0) or 0),
        missing_fields=tuple(getattr(response, "missing_fields", ()) or ()),
        reasons=tuple(getattr(response, "reasons", ()) or ()),
        rag_guard_warnings=tuple(getattr(response, "rag_guard_warnings", ()) or ()),
    )


def ask_bansa(
    question,
    *,
    finance_adapters=None,
    service=None,
) -> BansaResponse:
    raw = str(question or "").strip()

    # Tier 0: natural deterministic conversation layer.  It uses the same
    # verified local data as the fast router, but answers the user's actual
    # question instead of rendering a fixed table for every structured turn.
    try:
        from src.competition_natural_chat import answer_natural

        natural = answer_natural(raw)
        if natural is not None and str(natural.text or "").strip():
            qwen_used = False
            try:
                from src.competition_surface_naturalizer import maybe_naturalize_fast_answer
                natural, qwen_used = maybe_naturalize_fast_answer(raw, natural)
            except Exception:
                # Surface naturalization is optional. Deterministic finance
                # output remains the authoritative fallback.
                qwen_used = False
            return _from_fast(raw, natural, qwen_used=qwen_used)
    except Exception:
        # Never let presentation logic take the system down.
        pass

    # Tier 1/2: deterministic local verified fast path.
    try:
        fast = answer_fast(raw)
        if fast is not None and str(fast.text or "").strip():
            return _from_fast(raw, fast)
    except Exception:
        # The legacy core below may still be able to answer.
        pass

    # Tier 3: existing local Qwen/RAG/verified core, imported only when needed.
    try:
        from src.chatbot_response_service import ask_bansa as legacy_ask_bansa

        legacy = legacy_ask_bansa(
            raw,
            finance_adapters=finance_adapters,
            service=service,
        )
        copied = _copy_legacy(raw, legacy)
        if copied.text and not should_replace_failure_text(copied.text):
            return copied
    except Exception:
        pass

    # Tier 4: never render a raw technical/UNVERIFIED failure to the jury.
    return _from_fast(raw, smart_fallback(raw))
