# CHATBOT_RAG_ORCHESTRATOR_V1

from __future__ import annotations

from dataclasses import dataclass
import gc
import json
from pathlib import Path

import torch


from src.chatbot_router import (
    route_question,
)

from src.rag_bm25_index import (
    BM25Index,
)

from src.rag_dense_store import (
    load_chunks_jsonl,
    load_dense_index,
)


from src.rag_evidence_pack import (
    EvidencePack,
)

from src.rag_retrieval_verifier import (
    VERIFIER_ABSTAIN,
    VERIFIER_PASS,
    VERIFIER_RETRIEVE_MORE,
    RetrievalVerification,
    verify_retrieval,
)


from src.rag_rrf import (
    hybrid_search,
)


ROUTE_CAMPAIGN_RAG = "campaign_rag"
ROUTE_PRODUCT_RAG = "product_rag"
ROUTE_FINANCE_COMPARE = "finance_compare"
ROUTE_HYBRID = "hybrid"
ROUTE_UNKNOWN = "unknown"


RAG_STATUS_NOT_APPLICABLE = (
    "not_applicable"
)


@dataclass(frozen=True)
class ChatbotRagResult:

    question: str

    route: str

    expected_source_kind: str | None

    status: str

    attempts: int

    route_decision: object

    verification: (
        RetrievalVerification
        | None
    )

    evidence_pack: (
        EvidencePack
        | None
    )

    reasons: tuple[
        str,
        ...
    ]

    retrieval_trace: tuple[
        dict,
        ...
    ]


@dataclass
class RagRuntime:

    chunks: list
    dense_index: object
    bm25_index: BM25Index

    corpus_hash: str

    @classmethod
    def load(
        cls,
        *,
        rag_dir: str | Path = (
            "data/rag"
        ),
    ) -> "RagRuntime":

        from src.rag_embedding_qwen import DEFAULT_MODEL_NAME

        rag_dir = Path(
            rag_dir
        )

        chunks_path = (
            rag_dir
            / "rag_chunks.jsonl"
        )

        manifest_path = (
            rag_dir
            / "rag_manifest.json"
        )

        vectors_path = (
            rag_dir
            / "rag_dense_vectors.npy"
        )

        dense_manifest_path = (
            rag_dir
            / "rag_dense_manifest.json"
        )

        required = (
            chunks_path,
            manifest_path,
            vectors_path,
            dense_manifest_path,
        )

        missing = [
            str(path)
            for path in required
            if not path.exists()
        ]

        if missing:

            raise RuntimeError(
                "RAG runtime files missing: "
                + ", ".join(
                    missing
                )
            )

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        corpus_hash = str(
            manifest[
                "corpus_hash"
            ]
        )

        chunks = load_chunks_jsonl(
            chunks_path
        )

        dense_index, _ = (
            load_dense_index(
                chunks,
                vectors_path=(
                    vectors_path
                ),
                manifest_path=(
                    dense_manifest_path
                ),
                expected_corpus_hash=(
                    corpus_hash
                ),
                expected_model_name=(
                    DEFAULT_MODEL_NAME
                ),
            )
        )

        bm25_index = (
            BM25Index.build(
                chunks
            )
        )

        if len(
            dense_index.records
        ) != len(
            bm25_index.records
        ):

            raise RuntimeError(
                "Dense/BM25 runtime "
                "record count mismatch."
            )

        dense_ids = [
            record.chunk_id
            for record in (
                dense_index.records
            )
        ]

        bm25_ids = [
            record.chunk_id
            for record in (
                bm25_index.records
            )
        ]

        if dense_ids != bm25_ids:

            raise RuntimeError(
                "Dense/BM25 runtime "
                "chunk identity mismatch."
            )

        return cls(
            chunks=chunks,
            dense_index=dense_index,
            bm25_index=bm25_index,
            corpus_hash=corpus_hash,
        )



_DEFAULT_RAG_RUNTIME = None
_DEFAULT_RAG_RUNTIME_SIGNATURE = None


def _rag_runtime_signature(
    rag_dir: str | Path = "data/rag",
):
    """
    Lightweight cache invalidation signature.

    Runtime is reused while the on-disk RAG artifacts
    are unchanged. If any file is rebuilt/replaced,
    the next RAG request reloads the runtime.
    """

    root = Path(
        rag_dir
    )

    if not root.exists():

        return (
            (
                "__missing__",
                str(root),
            ),
        )

    result = []

    for path in sorted(
        (
            item
            for item in root.rglob("*")
            if item.is_file()
        ),
        key=lambda item:
            item.relative_to(
                root
            ).as_posix(),
    ):

        stat = path.stat()

        result.append(
            (
                path.relative_to(
                    root
                ).as_posix(),
                int(
                    stat.st_size
                ),
                int(
                    stat.st_mtime_ns
                ),
            )
        )

    return tuple(
        result
    )


def clear_cached_rag_runtime():
    """
    Explicit cache reset hook for tests/rebuild tools.
    """

    global _DEFAULT_RAG_RUNTIME
    global _DEFAULT_RAG_RUNTIME_SIGNATURE

    _DEFAULT_RAG_RUNTIME = None
    _DEFAULT_RAG_RUNTIME_SIGNATURE = None


def _get_cached_default_rag_runtime(
    *,
    rag_dir: str | Path = "data/rag",
) -> RagRuntime:

    global _DEFAULT_RAG_RUNTIME
    global _DEFAULT_RAG_RUNTIME_SIGNATURE

    signature = (
        _rag_runtime_signature(
            rag_dir
        )
    )

    if (
        _DEFAULT_RAG_RUNTIME
        is None
        or
        _DEFAULT_RAG_RUNTIME_SIGNATURE
        != signature
    ):

        runtime = RagRuntime.load(
            rag_dir=rag_dir
        )

        # Compute signature again after successful load.
        # This avoids caching a runtime against files that
        # happened to change while it was being loaded.
        final_signature = (
            _rag_runtime_signature(
                rag_dir
            )
        )

        _DEFAULT_RAG_RUNTIME = runtime
        _DEFAULT_RAG_RUNTIME_SIGNATURE = (
            final_signature
        )

    return _DEFAULT_RAG_RUNTIME

def expected_source_kind_for_route(
    route: str,
) -> str | None:

    if route == ROUTE_CAMPAIGN_RAG:
        return "campaign"

    if route == ROUTE_PRODUCT_RAG:
        return "standard_product"

    # Current hybrid router represents
    # campaign + structured finance.
    # RAG owns only the campaign side.
    if route == ROUTE_HYBRID:
        return "campaign"

    return None


def route_requires_rag(
    route: str,
) -> bool:

    return route in {
        ROUTE_CAMPAIGN_RAG,
        ROUTE_PRODUCT_RAG,
        ROUTE_HYBRID,
    }


def _source_predicate(
    expected_source_kind: str,
):

    return lambda record: (
        record.source_kind
        == expected_source_kind
    )


import threading as _rag_threading


_RAG_GPU_MODEL_LOCK = (
    _rag_threading.RLock()
)


def _activate_cached_rag_model(
    model,
):

    if model is None:

        raise RuntimeError(
            "RAG model is unavailable."
        )

    if not torch.cuda.is_available():

        raise RuntimeError(
            "CUDA is required for "
            "BANSA RAG model inference."
        )

    mover = getattr(
        model,
        "to",
        None,
    )

    if not callable(
        mover
    ):

        raise RuntimeError(
            "RAG model does not support "
            "device transfer."
        )

    device_text = str(
        getattr(
            model,
            "device",
            "",
        )
    ).lower()

    if not device_text.startswith(
        "cuda"
    ):

        mover(
            "cuda"
        )

    torch.cuda.synchronize()

    return model


def _offload_cached_rag_model(
    model,
):

    if model is None:

        return

    mover = getattr(
        model,
        "to",
        None,
    )

    if not callable(
        mover
    ):

        raise RuntimeError(
            "RAG model does not support "
            "CPU offload."
        )

    if torch.cuda.is_available():

        torch.cuda.synchronize()

    mover(
        "cpu"
    )

    gc.collect()

    if torch.cuda.is_available():

        torch.cuda.empty_cache()


def clear_cached_rag_models():

    from src.rag_embedding_qwen import (
        load_qwen_embedding_model,
    )

    from src.rag_reranker_qwen import (
        load_qwen_reranker_model,
    )

    with _RAG_GPU_MODEL_LOCK:

        load_qwen_embedding_model.cache_clear()

        load_qwen_reranker_model.cache_clear()

        gc.collect()

        if torch.cuda.is_available():

            torch.cuda.empty_cache()



def prewarm_rag_runtime_and_models():
    """
    Prepare BANSA RAG before the first user request.

    The runtime/index is cached in-process.

    Embedding and reranker weights are loaded once,
    then moved back to CPU RAM. Normal RAG requests
    later move only one heavy model to CUDA at a time.

    No retrieval question is executed here.
    No answer is generated here.
    """

    import time

    started = (
        time.perf_counter()
    )

    # --------------------------------------------------------
    # 1. RAG runtime / indexes
    # --------------------------------------------------------

    runtime_started = (
        time.perf_counter()
    )

    runtime = (
        _get_cached_default_rag_runtime()
    )

    runtime_seconds = (
        time.perf_counter()
        - runtime_started
    )

    # --------------------------------------------------------
    # 2. Embedding model
    # --------------------------------------------------------

    embedding_started = (
        time.perf_counter()
    )

    from src.rag_embedding_qwen import (
        create_qwen_embedding_backend,
        load_qwen_embedding_model,
    )

    embedding_backend = None
    embedding_model = None

    with _RAG_GPU_MODEL_LOCK:

        try:

            embedding_backend = (
                create_qwen_embedding_backend(
                    batch_size=1,
                )
            )

            embedding_model = (
                embedding_backend.model
            )

            _activate_cached_rag_model(
                embedding_model
            )

        finally:

            if embedding_model is not None:

                _offload_cached_rag_model(
                    embedding_model
                )

            if embedding_backend is not None:

                del embedding_backend

    embedding_seconds = (
        time.perf_counter()
        - embedding_started
    )

    # --------------------------------------------------------
    # 3. Reranker model
    # --------------------------------------------------------

    reranker_started = (
        time.perf_counter()
    )

    from src.rag_reranker_qwen import (
        create_qwen_reranker_backend,
        load_qwen_reranker_model,
    )

    reranker_backend = None
    reranker_model = None

    with _RAG_GPU_MODEL_LOCK:

        try:

            reranker_backend = (
                create_qwen_reranker_backend(
                    batch_size=1,
                    max_length=2048,
                )
            )

            reranker_model = (
                reranker_backend.model
            )

            _activate_cached_rag_model(
                reranker_model
            )

        finally:

            if reranker_model is not None:

                _offload_cached_rag_model(
                    reranker_model
                )

            if reranker_backend is not None:

                del reranker_backend

    reranker_seconds = (
        time.perf_counter()
        - reranker_started
    )

    # --------------------------------------------------------
    # 4. Final memory cleanup
    # --------------------------------------------------------

    gc.collect()

    if torch.cuda.is_available():

        torch.cuda.empty_cache()

    total_seconds = (
        time.perf_counter()
        - started
    )

    return {
        "status":
            "ready",

        "chunk_count":
            len(
                runtime.chunks
            ),

        "runtime_seconds":
            runtime_seconds,

        "embedding_seconds":
            embedding_seconds,

        "reranker_seconds":
            reranker_seconds,

        "total_seconds":
            total_seconds,

        "embedding_cache":
            load_qwen_embedding_model.cache_info(),

        "reranker_cache":
            load_qwen_reranker_model.cache_info(),
    }

def _release_embedding_model(
    model=None,
):

    _offload_cached_rag_model(
        model
    )


def _release_reranker_model(
    model=None,
):

    _offload_cached_rag_model(
        model
    )


def _retrieve_rrf(
    runtime: RagRuntime,
    question: str,
    *,
    expected_source_kind: str,
    source_top_k: int,
    rrf_top_k: int,
):

    from src.rag_embedding_qwen import (
        create_qwen_embedding_backend,
    )

    backend = (
        create_qwen_embedding_backend(
            batch_size=1,
        )
    )

    model = None

    with _RAG_GPU_MODEL_LOCK:

        try:

            # The loader is lru_cached.
            #
            # Cold request:
            #   disk -> CUDA
            #
            # Warm request:
            #   CPU RAM -> CUDA
            #
            # No weight reload is required
            # after the first request.
            model = backend.model

            _activate_cached_rag_model(
                model
            )

            hits = hybrid_search(
                question,
                dense_index=(
                    runtime.dense_index
                ),
                bm25_index=(
                    runtime.bm25_index
                ),
                embed_queries=(
                    backend.encode_queries
                ),
                source_top_k=(
                    source_top_k
                ),
                final_top_k=(
                    rrf_top_k
                ),
                rrf_k=60,
                predicate=(
                    _source_predicate(
                        expected_source_kind
                    )
                ),
            )

            return hits

        finally:

            if model is not None:

                _release_embedding_model(
                    model
                )

            del backend


def _rerank(
    question: str,
    rrf_hits,
    *,
    rerank_top_k: int,
):

    from src.rag_reranker_qwen import (
        create_qwen_reranker_backend,
    )

    reranker = (
        create_qwen_reranker_backend(
            batch_size=1,
            max_length=2048,
        )
    )

    model = None

    with _RAG_GPU_MODEL_LOCK:

        try:

            # The first call loads weights.
            # Later calls reuse the same cached
            # CPU-resident model and move it to
            # CUDA only for inference.
            model = reranker.model

            _activate_cached_rag_model(
                model
            )

            return (
                reranker.rerank_rrf_hits(
                    question,
                    rrf_hits,
                    top_k=(
                        rerank_top_k
                    ),
                )
            )

        finally:

            if model is not None:

                _release_reranker_model(
                    model
                )

            del reranker


def _one_attempt(
    runtime: RagRuntime,
    question: str,
    *,
    expected_source_kind: str,
    attempt: int,
    max_attempts: int,
    source_top_k: int,
    rrf_top_k: int,
    rerank_top_k: int,
):

    rrf_hits = _retrieve_rrf(
        runtime,
        question,
        expected_source_kind=(
            expected_source_kind
        ),
        source_top_k=source_top_k,
        rrf_top_k=rrf_top_k,
    )

    reranked = _rerank(
        question,
        rrf_hits,
        rerank_top_k=(
            rerank_top_k
        ),
    )

    verification = verify_retrieval(
        question,
        reranked,
        expected_source_kind=(
            expected_source_kind
        ),
        attempt=attempt,
        max_attempts=max_attempts,
        max_evidence_items=6,
        max_per_document=2,
    )

    trace = {
        "attempt":
            int(attempt),

        "source_top_k":
            int(source_top_k),

        "rrf_candidate_count":
            len(rrf_hits),

        "reranked_count":
            len(reranked),

        "verification_status":
            verification.status,

        "lexical_coverage":
            verification.lexical_coverage,

        "cross_lane_item_count":
            (
                verification
                .cross_lane_item_count
            ),

        "eligible_item_count":
            verification.eligible_item_count,

        "reasons":
            verification.reasons,
    }

    return (
        verification,
        trace,
    )


def run_chatbot_rag(
    question: str,
    *,
    runtime: RagRuntime | None = None,
    route_decision=None,
) -> ChatbotRagResult:

    question = str(
        question or ""
    ).strip()

    if route_decision is None:

        route_decision = (
            route_question(
                question
            )
        )

    route = str(
        route_decision.route
    )

    expected_source_kind = (
        expected_source_kind_for_route(
            route
        )
    )

    if not route_requires_rag(
        route
    ):

        reasons = (
            (
                "finance_route_uses_"
                "deterministic_engine"
            )
            if route
            == ROUTE_FINANCE_COMPARE
            else (
                "rag_not_required_"
                "for_route"
            )
        )

        return ChatbotRagResult(
            question=question,
            route=route,
            expected_source_kind=None,
            status=(
                RAG_STATUS_NOT_APPLICABLE
            ),
            attempts=0,
            route_decision=(
                route_decision
            ),
            verification=None,
            evidence_pack=None,
            reasons=(
                reasons,
            ),
            retrieval_trace=tuple(),
        )

    if not expected_source_kind:

        return ChatbotRagResult(
            question=question,
            route=route,
            expected_source_kind=None,
            status=VERIFIER_ABSTAIN,
            attempts=0,
            route_decision=(
                route_decision
            ),
            verification=None,
            evidence_pack=None,
            reasons=(
                "rag_source_kind_unresolved",
            ),
            retrieval_trace=tuple(),
        )

    if runtime is None:

        runtime = (
            _get_cached_default_rag_runtime()
        )

    trace = []

    # Attempt 1:
    # narrow, efficient retrieval.
    first, first_trace = (
        _one_attempt(
            runtime,
            question,
            expected_source_kind=(
                expected_source_kind
            ),
            attempt=1,
            max_attempts=2,
            source_top_k=20,
            rrf_top_k=10,
            rerank_top_k=6,
        )
    )

    trace.append(
        first_trace
    )

    if first.status in {
        VERIFIER_PASS,
        VERIFIER_ABSTAIN,
    }:

        return ChatbotRagResult(
            question=question,
            route=route,
            expected_source_kind=(
                expected_source_kind
            ),
            status=first.status,
            attempts=1,
            route_decision=(
                route_decision
            ),
            verification=first,
            evidence_pack=(
                first.evidence_pack
            ),
            reasons=first.reasons,
            retrieval_trace=tuple(
                trace
            ),
        )

    if first.status != (
        VERIFIER_RETRIEVE_MORE
    ):

        raise RuntimeError(
            "Unexpected retrieval "
            f"verification status: "
            f"{first.status}"
        )

    # Attempt 2:
    # expanded candidate recall.
    second, second_trace = (
        _one_attempt(
            runtime,
            question,
            expected_source_kind=(
                expected_source_kind
            ),
            attempt=2,
            max_attempts=2,
            source_top_k=50,
            rrf_top_k=25,
            rerank_top_k=10,
        )
    )

    trace.append(
        second_trace
    )

    return ChatbotRagResult(
        question=question,
        route=route,
        expected_source_kind=(
            expected_source_kind
        ),
        status=second.status,
        attempts=2,
        route_decision=(
            route_decision
        ),
        verification=second,
        evidence_pack=(
            second.evidence_pack
        ),
        reasons=second.reasons,
        retrieval_trace=tuple(
            trace
        ),
    )
