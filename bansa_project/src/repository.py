from __future__ import annotations

import pandas as pd

from src.db import get_connection


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

    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("id", ascending=False)
        .reset_index(drop=True)
    )


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
