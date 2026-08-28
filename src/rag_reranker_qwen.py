# RAG_RERANKER_QWEN_V1

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

import numpy as np
import torch

from sentence_transformers import (
    CrossEncoder,
)


DEFAULT_RERANKER_MODEL = (
    "Qwen/Qwen3-Reranker-0.6B"
)


DEFAULT_RERANK_INSTRUCTION = (
    "Given a Turkish participation-banking "
    "user query, rank official bank product "
    "or campaign passages by how directly "
    "they answer the query. Prefer exact "
    "entities, eligibility conditions, dates, "
    "amounts, maturities, limits and campaign "
    "conditions. Do not reward passages that "
    "are merely topically related."
)


DEFAULT_PROMPT_NAME = "bansa"

DEFAULT_MAX_LENGTH = 2048


class QwenRerankerError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class RerankedSearchHit:

    rank: int

    rerank_score: float

    record: object

    rrf_rank: int
    rrf_score: float

    dense_rank: int | None
    dense_score: float | None

    bm25_rank: int | None
    bm25_score: float | None


def _require_cuda() -> None:

    if not torch.cuda.is_available():

        raise QwenRerankerError(
            "CUDA is unavailable. "
            "Silent CPU fallback is disabled."
        )


@lru_cache(maxsize=2)
def load_qwen_reranker_model(
    model_name: str = DEFAULT_RERANKER_MODEL,
    max_length: int = DEFAULT_MAX_LENGTH,
):

    _require_cuda()

    try:

        model = CrossEncoder(
            model_name,
            device="cuda",
            max_length=int(
                max_length
            ),
            model_kwargs={
                "torch_dtype":
                    torch.float16,
            },
            prompts={
                DEFAULT_PROMPT_NAME:
                    DEFAULT_RERANK_INSTRUCTION,
            },
            default_prompt_name=(
                DEFAULT_PROMPT_NAME
            ),
        )

    except Exception as exc:

        raise QwenRerankerError(
            "Qwen reranker model "
            "could not be loaded."
        ) from exc

    try:

        parameter_device = str(
            next(
                model.model.parameters()
            ).device
        ).lower()

    except Exception as exc:

        raise QwenRerankerError(
            "Could not verify reranker "
            "device."
        ) from exc

    if not parameter_device.startswith(
        "cuda"
    ):

        raise QwenRerankerError(
            "Reranker is not running "
            "on CUDA."
        )

    model.model.eval()

    return model


class QwenRerankerBackend:

    def __init__(
        self,
        *,
        model_name: str = (
            DEFAULT_RERANKER_MODEL
        ),
        batch_size: int = 1,
        max_length: int = (
            DEFAULT_MAX_LENGTH
        ),
        model=None,
    ):

        self.model_name = str(
            model_name
        )

        self.batch_size = max(
            1,
            int(batch_size),
        )

        self.max_length = max(
            256,
            int(max_length),
        )

        self._injected_model = model

    @property
    def model(self):

        if self._injected_model is not None:

            return self._injected_model

        return load_qwen_reranker_model(
            self.model_name,
            self.max_length,
        )

    def score(
        self,
        query: str,
        passages: Sequence[str],
    ) -> np.ndarray:

        query_text = str(
            query or ""
        ).strip()

        if not query_text:

            raise QwenRerankerError(
                "Reranker query "
                "cannot be empty."
            )

        passage_values = [
            str(
                passage or ""
            ).strip()
            for passage in passages
        ]

        if not passage_values:

            return np.empty(
                (0,),
                dtype=np.float32,
            )

        pairs = [
            (
                query_text,
                passage,
            )
            for passage in (
                passage_values
            )
        ]

        try:

            scores = self.model.predict(
                pairs,
                batch_size=(
                    self.batch_size
                ),
                show_progress_bar=False,
            )

        except Exception as exc:

            raise QwenRerankerError(
                "Qwen reranking failed."
            ) from exc

        array = np.asarray(
            scores,
            dtype=np.float32,
        ).reshape(
            -1
        )

        if array.shape[0] != len(
            passage_values
        ):

            raise QwenRerankerError(
                "Reranker returned "
                "unexpected score count."
            )

        if not np.isfinite(
            array
        ).all():

            raise QwenRerankerError(
                "Reranker output contains "
                "NaN or Inf."
            )

        return array

    def rerank_rrf_hits(
        self,
        query: str,
        hits,
        *,
        top_k: int = 5,
    ) -> list[RerankedSearchHit]:

        candidates = list(
            hits
        )

        if not candidates:
            return []

        passages = [
            hit.record.embedding_text
            for hit in candidates
        ]

        scores = self.score(
            query,
            passages,
        )

        combined = [
            (
                float(score),
                hit,
            )
            for score, hit in zip(
                scores,
                candidates,
            )
        ]

        combined.sort(
            key=lambda item: (
                item[0],
                -int(
                    item[1].rank
                ),
                item[
                    1
                ].record.chunk_id,
            ),
            reverse=True,
        )

        limit = max(
            1,
            int(top_k),
        )

        return [
            RerankedSearchHit(
                rank=rank,
                rerank_score=score,
                record=hit.record,
                rrf_rank=int(
                    hit.rank
                ),
                rrf_score=float(
                    hit.rrf_score
                ),
                dense_rank=(
                    hit.dense_rank
                ),
                dense_score=(
                    hit.dense_score
                ),
                bm25_rank=(
                    hit.bm25_rank
                ),
                bm25_score=(
                    hit.bm25_score
                ),
            )
            for rank, (
                score,
                hit,
            )
            in enumerate(
                combined[:limit],
                start=1,
            )
        ]


def create_qwen_reranker_backend(
    *,
    batch_size: int = 1,
    max_length: int = (
        DEFAULT_MAX_LENGTH
    ),
) -> QwenRerankerBackend:

    return QwenRerankerBackend(
        batch_size=batch_size,
        max_length=max_length,
    )
