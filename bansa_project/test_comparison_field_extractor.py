import sqlite3
from pathlib import Path

from src.extraction.comparison_field_extractor import (
    detect_finance_type,
    extract_audiences,
    extract_benefits,
    extract_finance_fields,
)


def test_finance_fields():
    result = extract_finance_fields(
        "Togg Finansmanı",
        (
            "Togg alımlarına özel 1.500.000 TL'ye kadar "
            "finansman, 48 ay vade ve aylık kâr payı oranı "
            "%2,99 sunulmaktadır. Tahsis ücreti alınmaz."
        ),
    )

    assert result.finance_type == "Togg Taşıt Finansmanı"
    assert result.financing_amount_max == 1_500_000
    assert result.maturity_max_months == 48
    assert result.profit_share_rate_min == 2.99
    assert result.allocation_fee_status == "Tahsis ücreti yok"


def test_finance_type_umre():
    assert (
        detect_finance_type(
            "Şubesiz Umre Finansmanı",
            "Avantajlı finansman",
        )
        == "Umre Finansmanı"
    )


def test_points_and_minimum_spending():
    benefits = extract_benefits(
        "Akaryakıt Kampanyası",
        (
            "En az 1.000 TL harcamaya 100 TL Worldpuan "
            "kazanabilirsiniz."
        ),
    )

    points = [
        item
        for item in benefits
        if item.benefit_type == "shopping_points"
    ][0]

    assert points.points == 100
    assert points.minimum_spending == 1000


def test_discount():
    benefits = extract_benefits(
        "Otel Kampanyası",
        "Seçili otellerde %20 indirim fırsatı.",
    )

    discount = [
        item
        for item in benefits
        if item.benefit_type == "discount"
    ][0]

    assert discount.rate == 20


def test_audience():
    audiences = extract_audiences(
        "Yeni Müşterilere Özel",
        "Yeni müşterilerimize özel 500 TL ödül.",
    )

    assert audiences[0].audience_type == "new_customer"


def test_database_integration(tmp_path: Path):
    db_path = tmp_path / "campaigns.db"
    connection = sqlite3.connect(db_path)

    connection.executescript(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY,
            bank_name TEXT NOT NULL,
            title TEXT,
            clean_text TEXT,
            campaign_category TEXT,
            record_kind TEXT,
            current_status TEXT,
            source_url TEXT,
            start_date TEXT,
            end_date TEXT
        );

        INSERT INTO live_campaigns VALUES (
            1,
            'Albaraka Türk',
            'Togg Finansmanı',
            '1.500.000 TL''ye kadar finansman ve 48 ay vade.',
            'finance_campaign',
            'campaign',
            'active',
            'https://example.com/togg',
            NULL,
            NULL
        );
        """
    )
    connection.commit()
    connection.close()

    assert db_path.exists()
