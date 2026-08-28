import numpy as np

from src.rag_embedding_qwen import (
    EXPECTED_DIMENSION,
    QwenEmbeddingBackend,
    QwenEmbeddingError,
)


class FakeModel:

    device = "cuda:0"

    prompts = {
        "query":
            "Instruct: retrieve passage\nQuery:",
        "document":
            "",
    }

    def __init__(self):
        self.calls = []

    def get_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(
        self,
        texts,
        *,
        batch_size,
        normalize_embeddings,
        convert_to_numpy,
        show_progress_bar,
        prompt_name=None,
    ):

        self.calls.append(
            {
                "texts":
                    list(texts),
                "prompt_name":
                    prompt_name,
            }
        )

        vectors = np.zeros(
            (
                len(texts),
                EXPECTED_DIMENSION,
            ),
            dtype=np.float32,
        )

        vectors[:, 0] = 1.0

        return vectors


def test_document_embedding_has_no_query_prompt():

    model = FakeModel()

    backend = QwenEmbeddingBackend(
        model=model,
    )

    vectors = backend.encode_documents(
        [
            "Kampanya kosullari",
            "Egitim finansmani",
        ]
    )

    assert vectors.shape == (
        2,
        EXPECTED_DIMENSION,
    )

    assert (
        model.calls[-1]["prompt_name"]
        is None
    )


def test_query_embedding_uses_model_query_prompt():

    model = FakeModel()

    backend = QwenEmbeddingBackend(
        model=model,
    )

    vectors = backend.encode_queries(
        [
            "Egitim finansmani nedir?"
        ]
    )

    assert vectors.shape == (
        1,
        EXPECTED_DIMENSION,
    )

    assert (
        model.calls[-1]["prompt_name"]
        == "query"
    )


def test_semantic_split_embedding_is_document_mode():

    model = FakeModel()

    backend = QwenEmbeddingBackend(
        model=model,
    )

    backend.embed_for_semantic_split(
        [
            "Birinci bolum.",
            "Ikinci bolum.",
        ]
    )

    assert (
        model.calls[-1]["prompt_name"]
        is None
    )


def test_dimension_guard():

    class BadModel(
        FakeModel
    ):

        def encode(
            self,
            texts,
            **kwargs,
        ):

            return np.zeros(
                (
                    len(texts),
                    12,
                ),
                dtype=np.float32,
            )

    backend = QwenEmbeddingBackend(
        model=BadModel(),
    )

    try:

        backend.encode_documents(
            ["test"]
        )

    except QwenEmbeddingError as exc:

        assert (
            "unexpected dimension"
            in str(exc).lower()
        )

    else:

        raise AssertionError(
            "Dimension guard failed."
        )


def test_nan_guard():

    class NanModel(
        FakeModel
    ):

        def encode(
            self,
            texts,
            **kwargs,
        ):

            result = np.zeros(
                (
                    len(texts),
                    EXPECTED_DIMENSION,
                ),
                dtype=np.float32,
            )

            result[0, 0] = np.nan

            return result

    backend = QwenEmbeddingBackend(
        model=NanModel(),
    )

    try:

        backend.encode_documents(
            ["test"]
        )

    except QwenEmbeddingError as exc:

        assert (
            "nan or inf"
            in str(exc).lower()
        )

    else:

        raise AssertionError(
            "NaN guard failed."
        )
