import sqlite3

from scripts.audit_kuveyt_nonfinance_extraction import (
    audit_campaign,
)


def row(values):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    columns = ", ".join(
        f'? AS "{key}"'
        for key in values
    )
    return connection.execute(
        f"SELECT {columns}",
        tuple(values.values()),
    ).fetchone()


def test_missing_reward_and_new_customer_audience_are_high():
    campaign = row(
        {
            "id": 1,
            "title": "Yeni Müşterilere 500 TL Hediye",
            "source_url": "https://example.com/campaign",
            "source_group": "Müşteri Ol Kampanyaları",
            "clean_text": (
                "Mobil üzerinden yeni müşterimiz olun, "
                "500 TL hediye kazanın."
            ),
            "campaign_category": "new_customer_campaign",
            "current_status": "active",
        }
    )

    result = audit_campaign(
        campaign,
        benefits=[],
        audiences=[],
    )

    assert result["severity"] == "high"
    assert "reward" in result["detected_signals"]
    assert any(
        "new_customer" in reason
        for reason in result["high_reasons"]
    )


def test_complete_discount_card_campaign_is_clean():
    campaign = row(
        {
            "id": 2,
            "title": "Kart Sahiplerine %20 İndirim",
            "source_url": "https://example.com/discount",
            "source_group": "Kart Kampanyaları",
            "clean_text": (
                "Kart sahipleri alışverişlerinde %20 indirim kazanır."
            ),
            "campaign_category": "discount_campaign",
            "current_status": "active",
        }
    )
    benefit = row(
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 20.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "İndirim oranı",
            "evidence": (
                "Kart sahipleri alışverişlerinde %20 indirim kazanır."
            ),
        }
    )
    audience = row(
        {
            "audience_type": "card_holder",
            "audience_label": "Kart Sahipleri",
            "details": None,
        }
    )

    result = audit_campaign(
        campaign,
        benefits=[benefit],
        audiences=[audience],
    )

    assert result["severity"] == "ok"


def test_miles_signal_without_structured_benefit_is_high():
    campaign = row(
        {
            "id": 3,
            "title": "10.000 Mil Fırsatı",
            "source_url": "https://example.com/miles",
            "source_group": "Kart Kampanyaları",
            "clean_text": (
                "Miles&Smiles kart ile 10.000 Mil kazanabilirsiniz."
            ),
            "campaign_category": "points_campaign",
            "current_status": "active",
        }
    )

    result = audit_campaign(
        campaign,
        benefits=[],
        audiences=[],
    )

    assert result["severity"] == "high"
    assert "miles" in result["detected_signals"]
