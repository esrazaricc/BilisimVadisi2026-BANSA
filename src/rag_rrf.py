# RAG_RRF_V1

from __future__ import annotations

from dataclasses import dataclass


from src.rag_dense_index import (
    DenseIndexRecord,
)


@dataclass(frozen=True)
class RRFSearchHit:

    rank: int

    rrf_score: float

    record: DenseIndexRecord

    dense_rank: int | None
    dense_score: float | None

    bm25_rank: int | None
    bm25_score: float | None


def reciprocal_rank_fusion(
    *,
    dense_hits,
    bm25_hits,
    rrf_k: int = 60,
    top_k: int = 10,
) -> list[RRFSearchHit]:

    k = max(
        1,
        int(rrf_k),
    )

    candidates = {}

    for hit in dense_hits:

        chunk_id = (
            hit.record.chunk_id
        )

        entry = candidates.setdefault(
            chunk_id,
            {
                "record":
                    hit.record,
                "rrf_score":
                    0.0,
                "dense_rank":
                    None,
                "dense_score":
                    None,
                "bm25_rank":
                    None,
                "bm25_score":
                    None,
            },
        )

        entry[
            "dense_rank"
        ] = int(
            hit.rank
        )

        entry[
            "dense_score"
        ] = float(
            hit.score
        )

        entry[
            "rrf_score"
        ] += (
            1.0
            / (
                k
                + int(
                    hit.rank
                )
            )
        )

    for hit in bm25_hits:

        chunk_id = (
            hit.record.chunk_id
        )

        entry = candidates.setdefault(
            chunk_id,
            {
                "record":
                    hit.record,
                "rrf_score":
                    0.0,
                "dense_rank":
                    None,
                "dense_score":
                    None,
                "bm25_rank":
                    None,
                "bm25_score":
                    None,
            },
        )

        entry[
            "bm25_rank"
        ] = int(
            hit.rank
        )

        entry[
            "bm25_score"
        ] = float(
            hit.score
        )

        entry[
            "rrf_score"
        ] += (
            1.0
            / (
                k
                + int(
                    hit.rank
                )
            )
        )

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            item["rrf_score"],
            (
                item["dense_rank"]
                is not None
            )
            + (
                item["bm25_rank"]
                is not None
            ),
            item["record"].chunk_id,
        ),
        reverse=True,
    )

    limit = max(
        1,
        int(top_k),
    )

    return [
        RRFSearchHit(
            rank=rank,
            rrf_score=float(
                item["rrf_score"]
            ),
            record=item[
                "record"
            ],
            dense_rank=item[
                "dense_rank"
            ],
            dense_score=item[
                "dense_score"
            ],
            bm25_rank=item[
                "bm25_rank"
            ],
            bm25_score=item[
                "bm25_score"
            ],
        )
        for rank, item in enumerate(
            ordered[:limit],
            start=1,
        )
    ]


def hybrid_search(
    query: str,
    *,
    dense_index,
    bm25_index,
    embed_queries,
    source_top_k: int = 20,
    final_top_k: int = 10,
    rrf_k: int = 60,
    predicate=None,
) -> list[RRFSearchHit]:

    source_limit = max(
        int(source_top_k),
        int(final_top_k),
        1,
    )

    dense_hits = (
        dense_index.search(
            query,
            embed_queries=(
                embed_queries
            ),
            top_k=source_limit,
            predicate=predicate,
        )
    )

    bm25_hits = (
        bm25_index.search(
            query,
            top_k=source_limit,
            predicate=predicate,
        )
    )

    return reciprocal_rank_fusion(
        dense_hits=dense_hits,
        bm25_hits=bm25_hits,
        rrf_k=rrf_k,
        top_k=final_top_k,
    )
