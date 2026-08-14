from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable, Sequence

import pandas as pd

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover - kullanıcı ortamı kontrolü
    raise RuntimeError(
        'PostgreSQL sürücüsü kurulu değil. '
        'Çalıştırın: python -m pip install "psycopg[binary]"'
    ) from exc


POSTGRES_SCHEMA = "bansa"


def _dsn() -> str:
    value = os.getenv("POSTGRES_DSN", "").strip()
    if not value:
        raise RuntimeError(
            "POSTGRES_DSN tanımlı değil. Finansman Karşılaştırması "
            "PostgreSQL source-of-truth modunda çalışacak şekilde ayarlı."
        )
    return value


@contextmanager
def get_postgres_connection():
    connection = psycopg.connect(
        _dsn(),
        row_factory=dict_row,
        application_name="bansa_streamlit_read",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO bansa, public")
        yield connection
    finally:
        connection.close()


def _query_df(
    sql: str,
    params: Sequence | None = None,
) -> pd.DataFrame:
    with get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            columns = [item.name for item in cursor.description] if cursor.description else []
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def postgres_health() -> dict[str, object]:
    frame = _query_df(
        """
        SELECT
            current_database() AS database_name,
            current_schema() AS schema_name,
            version() AS server_version,
            (SELECT COUNT(*) FROM standard_products WHERE is_current = TRUE) AS current_products,
            (SELECT COUNT(*) FROM campaigns WHERE is_current = TRUE) AS current_campaigns
        """
    )
    if frame.empty:
        raise RuntimeError("PostgreSQL sağlık sorgusu sonuç döndürmedi.")
    return frame.iloc[0].to_dict()


def get_standard_products() -> pd.DataFrame:
    """PostgreSQL'deki güncel standart finansman ürünlerini döndürür."""
    return _query_df(
        """
        SELECT
            p.id,
            b.name AS bank_name,
            f.family_key AS product_family_key,
            f.family_name AS product_family,
            p.product_name,
            p.scope,
            p.minimum_financing_amount,
            p.maximum_financing_amount,
            p.minimum_maturity_months,
            p.maximum_maturity_months,
            p.profit_share_rate,
            p.profit_share_rate_text,
            p.interest_free,
            p.interest_free_text,
            p.maturity_rules_text,
            p.maturity_reference_upper_amount,
            p.financing_ratio_rules_text,
            p.maximum_financing_ratio,
            p.vehicle_finance_rules_text,
            p.vehicle_age_rules_text,
            p.shopping_general_limit_amount,
            p.shopping_general_max_maturity_months,
            p.shopping_finance_rules_text,
            p.shopping_phone_rule_text,
            p.shopping_tablet_max_maturity_months,
            p.shopping_computer_max_maturity_months,
            p.fee_waiver_text,
            p.insurance_fee_waived,
            p.allocation_fee_waived,
            p.commission_fee_waived,
            p.housing_first_home_rules_text,
            p.housing_additional_home_rules_text,
            p.housing_finance_rules::text AS housing_finance_rules_json,
            p.finance_rules::text AS finance_rules_json,
            s.url AS source_url,
            s.page_title AS source_page,
            s.clean_text,
            p.last_checked_at
        FROM standard_products AS p
        JOIN banks AS b
            ON b.id = p.bank_id
        JOIN product_families AS f
            ON f.id = p.family_id
        LEFT JOIN source_pages AS s
            ON s.id = p.source_page_id
        WHERE p.is_current = TRUE
        ORDER BY
            f.family_name,
            b.name,
            p.product_name
        """
    )


def get_standard_product_changes(limit: int = 100) -> pd.DataFrame:
    return _query_df(
        """
        SELECT
            e.id,
            e.product_id,
            b.name AS bank_name,
            e.product_family,
            e.product_name,
            e.source_url,
            e.change_type,
            e.changed_fields::text AS changed_fields_json,
            e.before_data::text AS before_json,
            e.after_data::text AS after_json,
            e.detected_at
        FROM product_change_events AS e
        JOIN banks AS b
            ON b.id = e.bank_id
        ORDER BY e.detected_at DESC, e.id DESC
        LIMIT %s
        """,
        (int(limit),),
    )


def get_standard_product_status() -> pd.DataFrame:
    return _query_df(
        """
        SELECT
            product_id,
            consecutive_missing_count,
            last_seen_scan_at,
            last_missing_scan_at,
            possible_removed
        FROM product_scan_state
        ORDER BY product_id
        """
    )


def _id_filter(
    product_ids: Iterable[int] | None,
    alias: str = "r",
) -> tuple[str, list[int]]:
    ids = [int(value) for value in (product_ids or [])]
    if not ids:
        return "", []
    placeholders = ",".join(["%s"] * len(ids))
    return f" WHERE {alias}.product_id IN ({placeholders})", ids


def _rule_query(
    table_name: str,
    order_by: str,
    product_ids: Iterable[int] | None,
) -> pd.DataFrame:
    where, params = _id_filter(product_ids)
    return _query_df(
        f"""
        SELECT
            r.*,
            b.name AS bank_name,
            p.product_name,
            f.family_name AS product_family,
            s.url AS source_url
        FROM {table_name} AS r
        JOIN standard_products AS p
            ON p.id = r.product_id
        JOIN banks AS b
            ON b.id = p.bank_id
        JOIN product_families AS f
            ON f.id = p.family_id
        LEFT JOIN source_pages AS s
            ON s.id = p.source_page_id
        {where}
        ORDER BY {order_by}
        """,
        params,
    )


def get_standard_product_rule_sets(
    product_ids: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    """Normalize edilmiş finansman kural tablolarını PostgreSQL'den okur."""
    category = _rule_query(
        "product_category_rules",
        "b.name, p.product_name, r.category_label, r.min_amount NULLS FIRST",
        product_ids,
    )
    amount_maturity = _rule_query(
        "product_amount_maturity_rules",
        "b.name, p.product_name, r.min_amount NULLS FIRST, r.max_amount NULLS LAST",
        product_ids,
    )
    pricing = _rule_query(
        "product_pricing_tiers",
        "b.name, p.product_name, r.maturity_months, r.pricing_variant NULLS FIRST",
        product_ids,
    )
    fee = _rule_query(
        "product_fee_rules",
        "b.name, p.product_name, r.fee_label",
        product_ids,
    )
    offer = _rule_query(
        "product_offer_rules",
        "b.name, p.product_name, r.max_amount NULLS LAST, r.max_installments NULLS LAST",
        product_ids,
    )
    feature = _rule_query(
        "product_features",
        "b.name, p.product_name, r.feature_label",
        product_ids,
    )

    return {
        "category": category,
        "amount_maturity": amount_maturity,
        "pricing": pricing,
        "fee": fee,
        "offer": offer,
        "feature": feature,
    }
