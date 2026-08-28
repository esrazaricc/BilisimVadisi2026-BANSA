import numpy as np

from dataclasses import dataclass


from src.rag_reranker_qwen import (
    QwenRerankerBackend,
    QwenRerankerError,
)


@dataclass
class FakeRecord:

    chunk_id: str
    embedding_text: str


@dataclass
class FakeRRFHit:

    rank: int
    rrf_score: float
    record: FakeRecord

    dense_rank: int | None = None
    dense_score: float | None = None

    bm25_rank: int | None = None
    bm25_score: float | None = None


class FakeModel:

    def __init__(
        self,
    ):

        self.calls = []

    def predict(
        self,
        pairs,
        *,
        batch_size,
        show_progress_bar,
    ):

        self.calls.append(
            {
                "pairs":
                    list(pairs),
                "batch_size":
                    batch_size,
            }
        )

        scores = []

        for query, passage in pairs:

            lowered = (
                passage.casefold()
            )

            if (
                "egitim finansmani"
                in lowered
            ):

                scores.append(
                    5.0
                )

            elif (
                "egitim"
                in lowered
            ):

                scores.append(
                    2.0
                )

            else:

                scores.append(
                    -1.0
                )

        return np.asarray(
            scores,
            dtype=np.float32,
        )


def test_reranker_scores_pairs():

    model = FakeModel()

    backend = QwenRerankerBackend(
        model=model,
        batch_size=1,
    )

    scores = backend.score(
        "Egitim masraflari",
        [
            "Egitim Finansmani bilgisi",
            "Tasit Finansmani bilgisi",
        ],
    )

    assert scores.shape == (
        2,
    )

    assert scores[0] > scores[1]

    assert (
        model.calls[-1][
            "batch_size"
        ]
        == 1
    )


def test_reranker_preserves_rrf_metadata():

    backend = QwenRerankerBackend(
        model=FakeModel(),
    )

    hits = [
        FakeRRFHit(
            rank=1,
            rrf_score=0.03,
            record=FakeRecord(
                chunk_id="vehicle",
                embedding_text=(
                    "Tasit Finansmani"
                ),
            ),
            dense_rank=1,
            bm25_rank=1,
        ),
        FakeRRFHit(
            rank=2,
            rrf_score=0.02,
            record=FakeRecord(
                chunk_id="education",
                embedding_text=(
                    "Egitim Finansmani"
                ),
            ),
            dense_rank=2,
            bm25_rank=2,
        ),
    ]

    reranked = (
        backend.rerank_rrf_hits(
            "Egitim masraflari",
            hits,
            top_k=2,
        )
    )

    assert (
        reranked[0]
        .record
        .chunk_id
        == "education"
    )

    assert (
        reranked[0]
        .rrf_rank
        == 2
    )

    assert (
        reranked[0]
        .dense_rank
        == 2
    )

    assert (
        reranked[0]
        .bm25_rank
        == 2
    )


def test_empty_query_guard():

    backend = QwenRerankerBackend(
        model=FakeModel(),
    )

    try:

        backend.score(
            "",
            ["document"],
        )

    except QwenRerankerError:

        pass

    else:

        raise AssertionError(
            "Empty query guard failed."
        )


def test_empty_passages():

    backend = QwenRerankerBackend(
        model=FakeModel(),
    )

    scores = backend.score(
        "query",
        [],
    )

    assert scores.shape == (
        0,
    )


def test_nan_guard():

    class NanModel:

        def predict(
            self,
            pairs,
            **kwargs,
        ):

            return np.asarray(
                [np.nan]
                * len(pairs),
                dtype=np.float32,
            )

    backend = QwenRerankerBackend(
        model=NanModel(),
    )

    try:

        backend.score(
            "query",
            ["document"],
        )

    except QwenRerankerError as exc:

        assert (
            "nan or inf"
            in str(exc).lower()
        )

    else:

        raise AssertionError(
            "NaN guard failed."
        )
