# RAG_CORPUS_BUILDER_V1

from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.rag_document_model import (
    SOURCE_KIND_CAMPAIGN,
    SOURCE_KIND_PRODUCT,
    RagChunkCandidate,
    RagDocument,
    build_rag_document,
)

from src.rag_structure_chunker import (
    sectionize_document,
)

from src.rag_semantic_splitter import (
    semantic_split_chunks,
)


_PRODUCT_STRUCTURED_FIELDS = (
    "minimum_financing_amount",
    "maximum_financing_amount",
    "minimum_maturity_months",
    "maximum_maturity_months",
    "profit_share_rate",
    "profit_share_rate_text",
    "interest_free",
    "interest_free_text",
    "maturity_rules_text",
    "maturity_reference_upper_amount",
    "financing_ratio_rules_text",
    "maximum_financing_ratio",
    "vehicle_finance_rules_text",
    "vehicle_age_rules_text",
    "shopping_general_limit_amount",
    "shopping_general_max_maturity_months",
    "shopping_finance_rules_text",
    "shopping_phone_rule_text",
    "shopping_tablet_max_maturity_months",
    "shopping_computer_max_maturity_months",
    "fee_waiver_text",
    "insurance_fee_waived",
    "allocation_fee_waived",
    "commission_fee_waived",
    "housing_first_home_rules_text",
    "housing_additional_home_rules_text",
    "housing_finance_rules_json",
    "finance_rules_json",
)


_CAMPAIGN_STRUCTURED_FIELDS = (
    "campaign_type",
    "linked_product_type",
    "target_audience",
    "minimum_transaction_amount",
    "maximum_transaction_amount",
    "installment_cost_rate",
    "installment_cost_text",
    "profit_share_rate",
    "financing_amount",
    "maturity_months",
    "installment_count",
    "reward_amount",
    "discount_rate",
    "shopping_points",
    "minimum_spending",
    "maximum_benefit",
    "expense_status",
    "campaign_start_date",
    "campaign_end_date",
    "source_evidence",
    "is_active",
    "extraction_confidence",
)


def _missing(
    value,
) -> bool:

    if value is None:
        return True

    try:

        result = pd.isna(
            value
        )

        if isinstance(
            result,
            bool,
        ):
            return result

        try:
            return bool(
                result
            )
        except Exception:
            return False

    except Exception:
        return False


def _text(
    value,
) -> str:

    if _missing(
        value
    ):
        return ""

    return str(
        value
    ).strip()


def _metadata_value(
    value,
):

    if _missing(
        value
    ):
        return None

    if hasattr(
        value,
        "item",
    ):

        try:
            return value.item()
        except Exception:
            pass

    if hasattr(
        value,
        "isoformat",
    ):

        try:
            return value.isoformat()
        except Exception:
            pass

    return value


def _structured_metadata(
    row,
    fields,
) -> dict:

    output = {}

    for field in fields:

        if field not in row:
            continue

        value = _metadata_value(
            row[field]
        )

        if value is not None:
            output[field] = value

    return output


def _product_fallback_text(
    row,
) -> str:

    parts = []

    bank = _text(
        row.get(
            "bank_name"
        )
    )

    product = _text(
        row.get(
            "product_name"
        )
    )

    family = _text(
        row.get(
            "product_family"
        )
    )

    source_page = _text(
        row.get(
            "source_page"
        )
    )

    if bank:
        parts.append(
            f"Banka: {bank}."
        )

    if product:
        parts.append(
            f"?r?n: {product}."
        )

    if family:
        parts.append(
            f"?r?n ailesi: {family}."
        )

    if (
        source_page
        and source_page
        != product
    ):
        parts.append(
            f"Kaynak sayfa: {source_page}."
        )

    return " ".join(
        parts
    ).strip()


def build_standard_product_documents(
    products=None,
) -> list[RagDocument]:

    if products is None:

        from src.postgres_repository import (
            get_standard_products,
        )

        products = (
            get_standard_products()
        )

    documents = []

    for _, row in products.iterrows():

        product_id = _text(
            row.get(
                "id"
            )
        )

        bank = _text(
            row.get(
                "bank_name"
            )
        )

        title = _text(
            row.get(
                "product_name"
            )
        )

        source_url = _text(
            row.get(
                "source_url"
            )
        )

        clean_text = _text(
            row.get(
                "clean_text"
            )
        )

        if clean_text:

            body = clean_text
            text_origin = (
                "official_clean_text"
            )
            grounding_limited = False

        else:

            body = (
                _product_fallback_text(
                    row
                )
            )

            text_origin = (
                "identity_fallback"
            )

            # An empty official body can still
            # be discoverable by name/family,
            # but the fallback is NOT enough
            # evidence for free-form claims.
            grounding_limited = True

        if not body:
            continue

        metadata = {
            "product_family_key":
                _text(
                    row.get(
                        "product_family_key"
                    )
                ),
            "product_family":
                _text(
                    row.get(
                        "product_family"
                    )
                ),
            "scope":
                _text(
                    row.get(
                        "scope"
                    )
                ),
            "source_page":
                _text(
                    row.get(
                        "source_page"
                    )
                ),
            "text_origin":
                text_origin,
            "grounding_limited":
                grounding_limited,
            "structured_fields":
                _structured_metadata(
                    row,
                    _PRODUCT_STRUCTURED_FIELDS,
                ),
        }

        document = build_rag_document(
            source_kind=(
                SOURCE_KIND_PRODUCT
            ),
            source_id=product_id,
            bank_name=bank,
            title=title,
            text=body,
            source_url=source_url,
            checked_at=_metadata_value(
                row.get(
                    "last_checked_at"
                )
            ),
            metadata=metadata,
        )

        documents.append(
            document
        )

    return documents


def build_campaign_documents(
    campaigns=None,
    *,
    active_only: bool = True,
) -> list[RagDocument]:

    if campaigns is None:

        from src.repository import (
            get_campaigns,
        )

        campaigns = get_campaigns()

    documents = []

    for _, row in campaigns.iterrows():

        active_raw = row.get(
            "is_active"
        )

        active = False

        if not _missing(
            active_raw
        ):

            try:
                active = (
                    float(active_raw)
                    == 1.0
                )
            except Exception:
                active = bool(
                    active_raw
                )

        if (
            active_only
            and not active
        ):
            continue

        campaign_id = _text(
            row.get(
                "id"
            )
        )

        bank = _text(
            row.get(
                "bank_name"
            )
        )

        title = _text(
            row.get(
                "campaign_name"
            )
        )

        source_url = _text(
            row.get(
                "source_url"
            )
        )

        conditions = _text(
            row.get(
                "campaign_conditions"
            )
        )

        if conditions:

            body = conditions
            text_origin = (
                "official_campaign_conditions"
            )
            grounding_limited = False

        else:

            body = title
            text_origin = (
                "campaign_title_fallback"
            )
            grounding_limited = True

        if not body:
            continue

        metadata = {
            "page_id":
                _metadata_value(
                    row.get(
                        "page_id"
                    )
                ),
            "campaign_type":
                _text(
                    row.get(
                        "campaign_type"
                    )
                ),
            "is_active":
                active,
            "text_origin":
                text_origin,
            "grounding_limited":
                grounding_limited,
            "structured_fields":
                _structured_metadata(
                    row,
                    _CAMPAIGN_STRUCTURED_FIELDS,
                ),
        }

        document = build_rag_document(
            source_kind=(
                SOURCE_KIND_CAMPAIGN
            ),
            source_id=campaign_id,
            bank_name=bank,
            title=title,
            text=body,
            source_url=source_url,
            checked_at=_metadata_value(
                row.get(
                    "created_at"
                )
            ),
            metadata=metadata,
        )

        documents.append(
            document
        )

    return documents


def build_rag_documents(
    *,
    products=None,
    campaigns=None,
    include_products: bool = True,
    include_campaigns: bool = True,
    active_campaigns_only: bool = True,
) -> list[RagDocument]:

    documents = []

    if include_products:

        documents.extend(
            build_standard_product_documents(
                products
            )
        )

    if include_campaigns:

        documents.extend(
            build_campaign_documents(
                campaigns,
                active_only=(
                    active_campaigns_only
                ),
            )
        )

    return documents


def build_structure_chunks(
    documents: Iterable[
        RagDocument
    ],
    *,
    semantic_split_threshold: int = 1800,
) -> list[RagChunkCandidate]:

    chunks = []

    for document in documents:

        chunks.extend(
            sectionize_document(
                document,
                semantic_split_threshold=(
                    semantic_split_threshold
                ),
            )
        )

    return chunks


def finish_semantic_chunks(
    chunks: Iterable[
        RagChunkCandidate
    ],
    *,
    embed_texts,
    min_chars: int = 350,
    max_chars: int = 1400,
    context_radius: int = 1,
    breakpoint_percentile: float = 80.0,
) -> list[RagChunkCandidate]:

    return semantic_split_chunks(
        chunks,
        embed_texts=embed_texts,
        min_chars=min_chars,
        max_chars=max_chars,
        context_radius=context_radius,
        breakpoint_percentile=(
            breakpoint_percentile
        ),
    )
