# RAG_EMBEDDING_QWEN_V1

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np
import torch

from sentence_transformers import (
    SentenceTransformer,
)


DEFAULT_MODEL_NAME = (
    "Qwen/Qwen3-Embedding-0.6B"
)

EXPECTED_DIMENSION = 1024


class QwenEmbeddingError(
    RuntimeError
):
    pass


def _require_cuda() -> None:

    if not torch.cuda.is_available():

        raise QwenEmbeddingError(
            "CUDA is unavailable. "
            "Silent CPU fallback is disabled."
        )


@lru_cache(maxsize=2)
def load_qwen_embedding_model(
    model_name: str = DEFAULT_MODEL_NAME,
) -> SentenceTransformer:

    _require_cuda()

    try:

        model = SentenceTransformer(
            model_name,
            device="cuda",
            model_kwargs={
                "torch_dtype":
                    torch.float16,
            },
        )

    except Exception as exc:

        raise QwenEmbeddingError(
            "Qwen embedding model "
            "could not be loaded."
        ) from exc

    device_text = str(
        model.device
    ).lower()

    if not device_text.startswith(
        "cuda"
    ):

        raise QwenEmbeddingError(
            "Qwen embedding model "
            "is not running on CUDA."
        )

    if hasattr(
        model,
        "get_embedding_dimension",
    ):

        dimension = (
            model.get_embedding_dimension()
        )

    else:

        dimension = (
            model
            .get_sentence_embedding_dimension()
        )

    if (
        dimension is not None
        and int(dimension)
        != EXPECTED_DIMENSION
    ):

        raise QwenEmbeddingError(
            "Unexpected embedding "
            f"dimension: {dimension}"
        )

    prompts = getattr(
        model,
        "prompts",
        None,
    )

    if not (
        isinstance(
            prompts,
            dict,
        )
        and "query" in prompts
    ):

        raise QwenEmbeddingError(
            "Model query prompt "
            "was not found."
        )

    return model


class QwenEmbeddingBackend:

    def __init__(
        self,
        *,
        model_name: str = (
            DEFAULT_MODEL_NAME
        ),
        batch_size: int = 1,
        model=None,
    ):

        self.model_name = str(
            model_name
        )

        self.batch_size = max(
            1,
            int(batch_size),
        )

        self._injected_model = model

    @property
    def model(self):

        if self._injected_model is not None:

            return self._injected_model

        return load_qwen_embedding_model(
            self.model_name
        )

    @property
    def dimension(self) -> int:

        model = self.model

        if hasattr(
            model,
            "get_embedding_dimension",
        ):

            value = (
                model
                .get_embedding_dimension()
            )

        else:

            value = (
                model
                .get_sentence_embedding_dimension()
            )

        return int(
            value
        )

    def _validate_vectors(
        self,
        vectors,
        expected_count: int,
    ) -> np.ndarray:

        array = np.asarray(
            vectors
        )

        if array.ndim != 2:

            raise QwenEmbeddingError(
                "Embedding output must "
                "be a 2D matrix."
            )

        if array.shape[0] != int(
            expected_count
        ):

            raise QwenEmbeddingError(
                "Embedding backend "
                "returned unexpected "
                "vector count."
            )

        if array.shape[1] != (
            EXPECTED_DIMENSION
        ):

            raise QwenEmbeddingError(
                "Embedding backend "
                "returned unexpected "
                f"dimension: "
                f"{array.shape[1]}"
            )

        if not np.isfinite(
            array
        ).all():

            raise QwenEmbeddingError(
                "Embedding output "
                "contains NaN or Inf."
            )

        return array

    def encode_documents(
        self,
        texts: Sequence[str],
    ) -> np.ndarray:

        values = [
            str(text or "").strip()
            for text in texts
        ]

        if not values:

            return np.empty(
                (
                    0,
                    EXPECTED_DIMENSION,
                ),
                dtype=np.float32,
            )

        try:

            vectors = self.model.encode(
                values,
                batch_size=(
                    self.batch_size
                ),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

        except Exception as exc:

            raise QwenEmbeddingError(
                "Document embedding "
                "failed."
            ) from exc

        return self._validate_vectors(
            vectors,
            len(values),
        )

    def encode_queries(
        self,
        texts: Sequence[str],
    ) -> np.ndarray:

        values = [
            str(text or "").strip()
            for text in texts
        ]

        if not values:

            return np.empty(
                (
                    0,
                    EXPECTED_DIMENSION,
                ),
                dtype=np.float32,
            )

        prompts = getattr(
            self.model,
            "prompts",
            None,
        )

        if not (
            isinstance(
                prompts,
                dict,
            )
            and "query" in prompts
        ):

            raise QwenEmbeddingError(
                "Qwen query prompt "
                "is unavailable."
            )

        try:

            vectors = self.model.encode(
                values,
                prompt_name="query",
                batch_size=(
                    self.batch_size
                ),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

        except Exception as exc:

            raise QwenEmbeddingError(
                "Query embedding failed."
            ) from exc

        return self._validate_vectors(
            vectors,
            len(values),
        )

    def embed_for_semantic_split(
        self,
        texts: list[str],
    ) -> np.ndarray:

        # Semantic chunking compares
        # document passages with each
        # other. Therefore the query
        # instruction MUST NOT be used.
        return self.encode_documents(
            texts
        )


def create_qwen_embedding_backend(
    *,
    batch_size: int = 1,
) -> QwenEmbeddingBackend:

    return QwenEmbeddingBackend(
        batch_size=batch_size,
    )
