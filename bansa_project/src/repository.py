import pandas as pd

from src.db import get_connection


def save_analysis(bank_name, title, source_url, raw_text, classification, extraction):
    with get_connection() as connection:
        # Aynı URL yeniden taranırsa eski kaydı güncel sonuçla değiştiriyoruz.
        # Böylece her taramada aynı kampanya tekrar tekrar eklenmiyor.
        if source_url:
            old_page = connection.execute(
                "SELECT id FROM pages WHERE source_url = ?",
                (source_url,),
            ).fetchone()
            if old_page:
                connection.execute("DELETE FROM pages WHERE id = ?", (old_page["id"],))

        cursor = connection.execute(
            """
            INSERT INTO pages (
                bank_name, page_title, source_url, raw_text, page_type,
                is_campaign, classification_reason, classification_confidence
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
                    page_id, bank_name, campaign_name, campaign_type, linked_product_type,
                    target_audience, profit_share_rate, financing_amount, maturity_months,
                    installment_count, reward_amount, discount_rate, shopping_points,
                    minimum_spending, maximum_benefit, expense_status, campaign_start_date,
                    campaign_end_date, campaign_conditions, source_url, source_evidence,
                    is_active, extraction_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    None if extraction["is_active"] is None else int(extraction["is_active"]),
                    extraction["extraction_confidence"],
                ),
            )

        return int(page_id)


def get_pages():
    with get_connection() as connection:
        return pd.read_sql_query(
            "SELECT * FROM pages ORDER BY id DESC",
            connection,
        )


def get_campaigns():
    with get_connection() as connection:
        return pd.read_sql_query(
            "SELECT * FROM campaigns ORDER BY id DESC",
            connection,
        )


def dashboard_metrics():
    with get_connection() as connection:
        total_pages = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        total_campaigns = connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
        active_campaigns = connection.execute(
            "SELECT COUNT(*) FROM campaigns WHERE is_active = 1"
        ).fetchone()[0]
        standard_products = connection.execute(
            "SELECT COUNT(*) FROM pages WHERE page_type = 'standard_product'"
        ).fetchone()[0]

    return {
        "total_pages": total_pages,
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "standard_products": standard_products,
    }
