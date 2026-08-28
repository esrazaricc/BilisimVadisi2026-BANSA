from __future__ import annotations

import pandas as pd

from src.db import get_connection
from src.source_link_resolver import resolve_campaign_detail_url
from src.pricing_guardrails import (
    filter_authoritative_pricing_frame,
    sanitize_product_rate_frame,
)


LIVE_ID_OFFSET = 1_000_000_000


def _table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def save_analysis(
    bank_name,
    title,
    source_url,
    raw_text,
    classification,
    extraction,
):
    """
    Eski manuel analiz ekranıyla geriye dönük uyumluluğu korur.

    Canlı tarama sonuçları ``live_*`` tablolarında tutulur.
    Bu fonksiyon ise eski manuel analiz akışının ``pages`` ve
    ``campaigns`` tablolarına yazmaya devam etmesini sağlar.
    """
    with get_connection() as connection:
        if source_url:
            old_page = connection.execute(
                "SELECT id FROM pages WHERE source_url = ?",
                (source_url,),
            ).fetchone()
            if old_page:
                connection.execute(
                    "DELETE FROM pages WHERE id = ?",
                    (old_page["id"],),
                )

        cursor = connection.execute(
            """
            INSERT INTO pages (
                bank_name,
                page_title,
                source_url,
                raw_text,
                page_type,
                is_campaign,
                classification_reason,
                classification_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bank_name,
                title,
                source_url,
                raw_text,
                classification["page_type"],
                int(classification["is_campaign"]),
                "; ".join(classification["reasons"]),
                classification["confidence"],
            ),
        )
        page_id = cursor.lastrowid

        if extraction:
            connection.execute(
                """
                INSERT INTO campaigns (
                    page_id,
                    bank_name,
                    campaign_name,
                    campaign_type,
                    linked_product_type,
                    target_audience,
                    profit_share_rate,
                    financing_amount,
                    maturity_months,
                    installment_count,
                    reward_amount,
                    discount_rate,
                    shopping_points,
                    minimum_spending,
                    maximum_benefit,
                    expense_status,
                    campaign_start_date,
                    campaign_end_date,
                    campaign_conditions,
                    source_url,
                    source_evidence,
                    is_active,
                    extraction_confidence
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    page_id,
                    bank_name,
                    extraction["campaign_name"],
                    extraction["campaign_type"],
                    extraction["linked_product_type"],
                    extraction["target_audience"],
                    extraction["profit_share_rate"],
                    extraction["financing_amount"],
                    extraction["maturity_months"],
                    extraction["installment_count"],
                    extraction["reward_amount"],
                    extraction["discount_rate"],
                    extraction["shopping_points"],
                    extraction["minimum_spending"],
                    extraction["maximum_benefit"],
                    extraction["expense_status"],
                    extraction["campaign_start_date"],
                    extraction["campaign_end_date"],
                    extraction["campaign_conditions"],
                    source_url,
                    extraction["source_evidence"],
                    (
                        None
                        if extraction["is_active"] is None
                        else int(extraction["is_active"])
                    ),
                    extraction["extraction_confidence"],
                ),
            )

        return int(page_id)


def _legacy_pages(connection) -> pd.DataFrame:
    if not _table_exists(connection, "pages"):
        return pd.DataFrame()

    return pd.read_sql_query(
        f"""
        SELECT
            {LIVE_ID_OFFSET} + id AS id,
            bank_name,
            page_title,
            source_url,
            raw_text,
            page_type,
            is_campaign,
            classification_reason,
            classification_confidence,
            retrieved_at
        FROM pages
        ORDER BY id DESC
        """,
        connection,
    )


def _live_pages(connection) -> pd.DataFrame:
    if not _table_exists(connection, "live_campaigns"):
        return pd.DataFrame()

    return pd.read_sql_query(
        """
        SELECT
            id,
            bank_name,
            title AS page_title,
            source_url,
            clean_text AS raw_text,
            CASE
                WHEN record_kind = 'campaign' THEN 'campaign'
                WHEN record_kind = 'standard_product'
                    THEN 'standard_product'
                ELSE 'other'
            END AS page_type,
            CASE
                WHEN record_kind = 'campaign' THEN 1
                ELSE 0
            END AS is_campaign,
            classification_reason,
            classification_confidence,
            last_checked_at AS retrieved_at
        FROM live_campaigns
        ORDER BY id DESC
        """,
        connection,
    )


def get_pages():
    """
    Canlı ve eski kayıtları tek, eski arayüzle uyumlu DataFrame
    halinde döndürür.
    """
    with get_connection() as connection:
        live = _live_pages(connection)
        legacy = _legacy_pages(connection)

    frames = [
        frame
        for frame in (live, legacy)
        if not frame.empty
    ]
    if not frames:
        return pd.DataFrame(
            columns=[
                "id",
                "bank_name",
                "page_title",
                "source_url",
                "raw_text",
                "page_type",
                "is_campaign",
                "classification_reason",
                "classification_confidence",
                "retrieved_at",
            ]
        )

    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("id", ascending=False)
        .reset_index(drop=True)
    )


def _legacy_campaigns(connection) -> pd.DataFrame:
    if not _table_exists(connection, "campaigns"):
        return pd.DataFrame()

    return pd.read_sql_query(
        f"""
        SELECT
            {LIVE_ID_OFFSET} + id AS id,
            {LIVE_ID_OFFSET} + page_id AS page_id,
            bank_name,
            campaign_name,
            campaign_type,
            linked_product_type,
            target_audience,
            profit_share_rate,
            financing_amount,
            maturity_months,
            installment_count,
            reward_amount,
            discount_rate,
            shopping_points,
            minimum_spending,
            maximum_benefit,
            expense_status,
            campaign_start_date,
            campaign_end_date,
            campaign_conditions,
            source_url,
            source_evidence,
            is_active,
            extraction_confidence,
            created_at
        FROM campaigns
        ORDER BY id DESC
        """,
        connection,
    )


def _live_campaigns(connection) -> pd.DataFrame:
    if not _table_exists(connection, "live_campaigns"):
        return pd.DataFrame()

    return pd.read_sql_query(
        """
        WITH benefit_summary AS (
            SELECT
                campaign_id,
                MAX(
                    CASE
                        WHEN benefit_type IN ('reward', 'cashback')
                        THEN amount
                    END
                ) AS reward_amount,
                MAX(
                    CASE
                        WHEN benefit_type IN ('discount', 'cashback')
                        THEN rate
                    END
                ) AS discount_rate,
                MAX(
                    CASE
                        WHEN benefit_type = 'shopping_points'
                        THEN points
                    END
                ) AS shopping_points,
                MIN(minimum_spending) AS minimum_spending,
                MAX(maximum_benefit) AS maximum_benefit,
                MAX(
                    CASE
                        WHEN benefit_type = 'installment'
                        THEN CAST(description AS INTEGER)
                    END
                ) AS benefit_installment_count
            FROM live_campaign_benefits
            GROUP BY campaign_id
        ),
        audience_summary AS (
            SELECT
                campaign_id,
                GROUP_CONCAT(DISTINCT audience_label)
                    AS target_audience
            FROM live_campaign_audiences
            GROUP BY campaign_id
        )
        SELECT
            c.id,
            c.id AS page_id,
            c.bank_name,
            c.title AS campaign_name,
            c.campaign_category AS campaign_type,
            f.finance_type AS linked_product_type,
            a.target_audience,
            t.minimum_transaction_amount,
            t.maximum_transaction_amount,
            t.installment_cost_rate,
            t.installment_cost_text,
            COALESCE(
                f.profit_share_rate_min,
                f.profit_share_rate_max
            ) AS profit_share_rate,
            COALESCE(
                f.financing_amount_max,
                f.financing_amount_min
            ) AS financing_amount,
            COALESCE(
                f.maturity_max_months,
                f.maturity_min_months
            ) AS maturity_months,
            COALESCE(
                f.installment_count,
                t.installment_count,
                b.benefit_installment_count
            ) AS installment_count,
            b.reward_amount,
            b.discount_rate,
            b.shopping_points,
            b.minimum_spending,
            b.maximum_benefit,
            f.expense_status,
            c.start_date AS campaign_start_date,
            c.end_date AS campaign_end_date,
            c.clean_text AS campaign_conditions,
            c.source_url,
            COALESCE(
                f.evidence_text,
                c.classification_reason
            ) AS source_evidence,
            CASE
                WHEN c.current_status = 'active'
                     AND c.is_current = 1
                THEN 1
                WHEN c.current_status IN ('expired', 'removed')
                     OR c.is_current = 0
                THEN 0
                ELSE NULL
            END AS is_active,
            COALESCE(
                f.extraction_confidence,
                c.classification_confidence
            ) AS extraction_confidence,
            c.created_at
        FROM live_campaigns AS c
        LEFT JOIN live_campaign_finance_details AS f
            ON f.campaign_id = c.id
        LEFT JOIN benefit_summary AS b
            ON b.campaign_id = c.id
        LEFT JOIN audience_summary AS a
            ON a.campaign_id = c.id
        LEFT JOIN live_campaign_installment_terms AS t
            ON t.campaign_id = c.id
        WHERE c.record_kind = 'campaign'
          AND c.is_current = 1
        ORDER BY c.id DESC
        """,
        connection,
    )


def get_campaigns():
    """
    Eski Streamlit sayfalarının beklediği sütunları koruyarak
    canlı kampanya tablolarını okur.

    Böylece mevcut ``app.py`` ve ``pages`` dosyaları tek tek
    değiştirilmeden Albaraka Türk ve Kuveyt Türk kayıtlarını görür.
    """
    with get_connection() as connection:
        live = _live_campaigns(connection)
        legacy = _legacy_campaigns(connection)

    frames = [
        frame
        for frame in (live, legacy)
        if not frame.empty
    ]
    if not frames:
        return pd.DataFrame(
            columns=[
                "id",
                "page_id",
                "bank_name",
                "campaign_name",
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
                "campaign_conditions",
                "source_url",
                "source_evidence",
                "is_active",
                "extraction_confidence",
                "created_at",
            ]
        )

    result = (
        pd.concat(frames, ignore_index=True)
        .sort_values("id", ascending=False)
        .reset_index(drop=True)
    )
    if not result.empty and {"bank_name", "campaign_name", "source_url"}.issubset(result.columns):
        result["source_url"] = result.apply(
            lambda row: resolve_campaign_detail_url(
                row.get("bank_name"), row.get("campaign_name"), row.get("source_url")
            ),
            axis=1,
        )
    return result


def dashboard_metrics():
    pages = get_pages()
    campaigns = get_campaigns()

    total_pages = len(pages)
    total_campaigns = len(campaigns)

    if "is_active" in campaigns.columns:
        active_campaigns = int(
            (campaigns["is_active"] == 1).sum()
        )
    else:
        active_campaigns = 0

    if "page_type" in pages.columns:
        standard_products = int(
            (pages["page_type"] == "standard_product").sum()
        )
    else:
        standard_products = 0

    return {
        "total_pages": total_pages,
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "standard_products": standard_products,
    }


def get_standard_products():
    """
    Güncel standart finansman ürünlerini ve yapılandırılmış
    ürün detaylarını döndürür.

    Kampanya kayıtları bu sorguya dahil edilmez.
    """
    columns = [
        "id",
        "bank_name",
        "product_family_key",
        "product_family",
        "product_name",
        "scope",
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
        "source_url",
        "source_page",
        "clean_text",
        "last_checked_at",
    ]

    with get_connection() as connection:
        if not _table_exists(
            connection,
            "live_standard_product_details",
        ):
            return pd.DataFrame(columns=columns)

        frame = pd.read_sql_query(
            """
            SELECT
                c.id,
                c.bank_name,
                d.product_family_key,
                d.product_family,
                d.product_name,
                d.scope,
                d.minimum_financing_amount,
                d.maximum_financing_amount,
                d.minimum_maturity_months,
                d.maximum_maturity_months,
                d.profit_share_rate,
                d.profit_share_rate_text,
                d.interest_free,
                d.interest_free_text,
                d.maturity_rules_text,
                d.maturity_reference_upper_amount,
                d.financing_ratio_rules_text,
                d.maximum_financing_ratio,
                d.vehicle_finance_rules_text,
                d.vehicle_age_rules_text,
                d.shopping_general_limit_amount,
                d.shopping_general_max_maturity_months,
                d.shopping_finance_rules_text,
                d.shopping_phone_rule_text,
                d.shopping_tablet_max_maturity_months,
                d.shopping_computer_max_maturity_months,
                d.fee_waiver_text,
                d.insurance_fee_waived,
                d.allocation_fee_waived,
                d.commission_fee_waived,
                d.finance_rules_json,
                d.housing_first_home_rules_text,
                d.housing_additional_home_rules_text,
                d.housing_finance_rules_json,
                c.source_url,
                d.source_page,
                c.clean_text,
                c.last_checked_at
            FROM live_campaigns AS c
            JOIN live_standard_product_details AS d
                ON d.product_id = c.id
            WHERE c.record_kind = 'standard_product'
              AND c.is_current = 1
            ORDER BY
                d.product_family,
                c.bank_name,
                d.product_name
            """,
            connection,
        )

    if frame.empty:
        return pd.DataFrame(columns=columns)

    return sanitize_product_rate_frame(frame)


def get_standard_product_changes(limit: int = 100):
    """
    Standart ürünlerin son değişiklik geçmişini döndürür.
    """
    columns = [
        "id",
        "product_id",
        "bank_name",
        "product_family",
        "product_name",
        "source_url",
        "change_type",
        "changed_fields_json",
        "before_json",
        "after_json",
        "detected_at",
    ]

    with get_connection() as connection:
        if not _table_exists(
            connection,
            "live_standard_product_changes",
        ):
            return pd.DataFrame(columns=columns)

        frame = pd.read_sql_query(
            """
            SELECT
                id,
                product_id,
                bank_name,
                product_family,
                product_name,
                source_url,
                change_type,
                changed_fields_json,
                before_json,
                after_json,
                detected_at
            FROM live_standard_product_changes
            ORDER BY detected_at DESC, id DESC
            LIMIT ?
            """,
            connection,
            params=(int(limit),),
        )

    return frame


def get_standard_product_status():
    """
    Ürünlerin son tarama/missing durumunu döndürür.
    """
    columns = [
        "product_id",
        "consecutive_missing_count",
        "last_seen_scan_at",
        "last_missing_scan_at",
        "possible_removed",
    ]

    with get_connection() as connection:
        if not _table_exists(
            connection,
            "live_standard_product_scan_state",
        ):
            return pd.DataFrame(columns=columns)

        return pd.read_sql_query(
            """
            SELECT
                product_id,
                consecutive_missing_count,
                last_seen_scan_at,
                last_missing_scan_at,
                possible_removed
            FROM live_standard_product_scan_state
            """,
            connection,
        )


def get_standard_product_rule_sets(
    product_ids: list[int] | None = None,
):
    """
    Normalize finansman kural tablolarını döndürür.
    """
    empty = {
        "category": pd.DataFrame(),
        "amount_maturity": pd.DataFrame(),
        "pricing": pd.DataFrame(),
        "pricing_all": pd.DataFrame(),
        "evidence": pd.DataFrame(),
        "fee": pd.DataFrame(),
        "offer": pd.DataFrame(),
        "feature": pd.DataFrame(),
    }

    with get_connection() as connection:
        needed = [
            "live_product_category_rules",
            "live_product_amount_maturity_rules",
            "live_product_pricing_tiers",
            "live_product_fee_rules",
            "live_product_offer_rules",
        ]
        if not all(
            _table_exists(connection, table)
            for table in needed
        ):
            return empty

        where = ""
        params: list[int] = []

        if product_ids:
            placeholders = ",".join(
                "?"
                for _ in product_ids
            )
            where = (
                f" WHERE r.product_id IN ({placeholders})"
            )
            params = [
                int(value)
                for value in product_ids
            ]

        category = pd.read_sql_query(
            f"""
            SELECT
                r.*,
                c.bank_name,
                d.product_name,
                d.product_family,
                c.source_url
            FROM live_product_category_rules AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            JOIN live_standard_product_details AS d
                ON d.product_id=r.product_id
            {where}
            ORDER BY
                c.bank_name,
                d.product_name,
                r.category_label,
                r.min_amount
            """,
            connection,
            params=params,
        )

        amount_maturity = pd.read_sql_query(
            f"""
            SELECT
                r.*,
                c.bank_name,
                d.product_name,
                d.product_family,
                c.source_url
            FROM live_product_amount_maturity_rules AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            JOIN live_standard_product_details AS d
                ON d.product_id=r.product_id
            {where}
            ORDER BY
                c.bank_name,
                d.product_name,
                r.min_amount
            """,
            connection,
            params=params,
        )

        pricing_all = pd.read_sql_query(
            f"""
            SELECT
                r.*,
                c.bank_name,
                d.product_name,
                d.product_family,
                c.source_url AS product_source_url
            FROM live_product_pricing_tiers AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            JOIN live_standard_product_details AS d
                ON d.product_id=r.product_id
            {where}
            ORDER BY
                c.bank_name,
                d.product_name,
                r.maturity_months
            """,
            connection,
            params=params,
        )
        pricing = filter_authoritative_pricing_frame(pricing_all)

        if _table_exists(connection, "live_finance_fact_evidence"):
            evidence = pd.read_sql_query(
                f"""
                SELECT r.*, c.bank_name, d.product_name, d.product_family
                FROM live_finance_fact_evidence AS r
                JOIN live_campaigns AS c ON c.id=r.product_id
                JOIN live_standard_product_details AS d ON d.product_id=r.product_id
                {where}
                ORDER BY c.bank_name,d.product_name,r.fact_key
                """,
                connection,
                params=params,
            )
        else:
            evidence = pd.DataFrame()

        fee = pd.read_sql_query(
            f"""
            SELECT
                r.*,
                c.bank_name,
                d.product_name,
                d.product_family,
                c.source_url
            FROM live_product_fee_rules AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            JOIN live_standard_product_details AS d
                ON d.product_id=r.product_id
            {where}
            ORDER BY
                c.bank_name,
                d.product_name,
                r.fee_label
            """,
            connection,
            params=params,
        )

        offer = pd.read_sql_query(
            f"""
            SELECT
                r.*,
                c.bank_name,
                d.product_name,
                d.product_family,
                c.source_url
            FROM live_product_offer_rules AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            JOIN live_standard_product_details AS d
                ON d.product_id=r.product_id
            {where}
            ORDER BY
                c.bank_name,
                d.product_name,
                r.max_amount,
                r.max_installments
            """,
            connection,
            params=params,
        )

        if _table_exists(
            connection,
            "live_product_features",
        ):
            feature = pd.read_sql_query(
                f"""
                SELECT
                    r.*,
                    c.bank_name,
                    d.product_name,
                    d.product_family,
                    c.source_url
                FROM live_product_features AS r
                JOIN live_campaigns AS c
                    ON c.id=r.product_id
                JOIN live_standard_product_details AS d
                    ON d.product_id=r.product_id
                {where}
                ORDER BY
                    c.bank_name,
                    d.product_name,
                    r.feature_label
                """,
                connection,
                params=params,
            )
        else:
            feature = pd.DataFrame()

    return {
        "category": category,
        "amount_maturity": amount_maturity,
        "pricing": pricing,
        "pricing_all": pricing_all,
        "evidence": evidence,
        "fee": fee,
        "offer": offer,
        "feature": feature,
    }

