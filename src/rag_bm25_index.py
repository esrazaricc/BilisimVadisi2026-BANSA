# RAG_BM25_INDEX_V1

from __future__ import annotations

from collections import (
    Counter,
)

from dataclasses import dataclass

import math
import re
import unicodedata

from typing import (
    Iterable,
    Sequence,
)


from src.rag_dense_index import (
    DenseIndexRecord,
    build_dense_records,
)

from src.rag_document_model import (
    RagChunkCandidate,
)


_TOKEN_RE = re.compile(
    r"[a-z0-9]+"
)


_TURKISH_TRANSLATION = str.maketrans(
    {
        "\u0131": "i",
        "\u0130": "I",
    }
)


def lexical_normalize(
    text: str,
) -> str:

    value = str(
        text or ""
    ).translate(
        _TURKISH_TRANSLATION
    )

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )

    return value.casefold()


def tokenize(
    text: str,
) -> list[str]:

    normalized = (
        lexical_normalize(
            text
        )
    )

    return _TOKEN_RE.findall(
        normalized
    )


@dataclass(frozen=True)
class BM25SearchHit:

    rank: int
    score: float
    record: DenseIndexRecord


class BM25Index:

    def __init__(
        self,
        *,
        records: Sequence[
            DenseIndexRecord
        ],
        k1: float = 1.5,
        b: float = 0.75,
    ):

        self.records = tuple(
            records
        )

        self.k1 = float(
            k1
        )

        self.b = float(
            b
        )

        self._term_frequencies = []
        self._doc_lengths = []
        self._document_frequency = (
            Counter()
        )

        for record in self.records:

            tokens = tokenize(
                record.embedding_text
            )

            frequencies = Counter(
                tokens
            )

            self._term_frequencies.append(
                frequencies
            )

            self._doc_lengths.append(
                len(tokens)
            )

            for term in frequencies:

                self._document_frequency[
                    term
                ] += 1

        if self._doc_lengths:

            self.avg_doc_length = (
                sum(
                    self._doc_lengths
                )
                / len(
                    self._doc_lengths
                )
            )

        else:

            self.avg_doc_length = 0.0

    @classmethod
    def build(
        cls,
        chunks: Iterable[
            RagChunkCandidate
        ],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> "BM25Index":

        # Dense and BM25 deliberately share
        # the exact same eligible record
        # contract and chunk_id identity.
        records = build_dense_records(
            chunks
        )

        return cls(
            records=records,
            k1=k1,
            b=b,
        )

    def _idf(
        self,
        term: str,
    ) -> float:

        n = len(
            self.records
        )

        df = self._document_frequency.get(
            term,
            0,
        )

        if (
            n == 0
            or df == 0
        ):
            return 0.0

        return math.log(
            1.0
            + (
                n - df + 0.5
            )
            / (
                df + 0.5
            )
        )

    def _score_document(
        self,
        index: int,
        query_terms: Counter,
    ) -> float:

        if not query_terms:
            return 0.0

        frequencies = (
            self._term_frequencies[
                index
            ]
        )

        doc_length = (
            self._doc_lengths[
                index
            ]
        )

        score = 0.0

        for term, query_tf in (
            query_terms.items()
        ):

            tf = frequencies.get(
                term,
                0,
            )

            if tf <= 0:
                continue

            idf = self._idf(
                term
            )

            if self.avg_doc_length > 0:

                length_norm = (
                    1.0
                    - self.b
                    + self.b
                    * doc_length
                    / self.avg_doc_length
                )

            else:

                length_norm = 1.0

            numerator = (
                tf
                * (
                    self.k1
                    + 1.0
                )
            )

            denominator = (
                tf
                + self.k1
                * length_norm
            )

            score += (
                float(query_tf)
                * idf
                * numerator
                / denominator
            )

        return float(
            score
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        predicate=None,
    ) -> list[BM25SearchHit]:

        if not self.records:
            return []

        query_tokens = tokenize(
            query
        )

        if not query_tokens:
            return []

        query_terms = Counter(
            query_tokens
        )

        candidates = []

        for index, record in enumerate(
            self.records
        ):

            if (
                predicate is not None
                and not predicate(
                    record
                )
            ):
                continue

            score = (
                self._score_document(
                    index,
                    query_terms,
                )
            )

            if score <= 0:
                continue

            candidates.append(
                (
                    score,
                    record,
                )
            )

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1].chunk_id,
            ),
            reverse=True,
        )

        limit = max(
            1,
            int(top_k),
        )

        return [
            BM25SearchHit(
                rank=rank,
                score=score,
                record=record,
            )
            for rank, (
                score,
                record,
            )
            in enumerate(
                candidates[:limit],
                start=1,
            )
        ]
