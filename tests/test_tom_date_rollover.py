from datetime import date

from src.scraping.campaign_status import evaluate_campaign_status


TODAY = date(2026, 8, 10)


def test_december_to_august_rolls_start_year_back():
    result = evaluate_campaign_status(
        text="Kampanya Tarihleri 03 Aralık - 31 Ağustos 2026",
        reference_date=TODAY,
    )
    assert result.start_date == "2025-12-03"
    assert result.end_date == "2026-08-31"
    assert result.status == "active"


def test_october_to_august_rolls_start_year_back():
    result = evaluate_campaign_status(
        text="Kampanya Tarihleri 01 Ekim - 31 Ağustos 2026",
        reference_date=TODAY,
    )
    assert result.start_date == "2025-10-01"
    assert result.end_date == "2026-08-31"
    assert result.status == "active"


def test_october_to_december_same_year_stays_upcoming():
    result = evaluate_campaign_status(
        text="Kampanya Tarihleri 03 Ekim - 31 Aralık 2026",
        reference_date=TODAY,
    )
    assert result.start_date == "2026-10-03"
    assert result.end_date == "2026-12-31"
    assert result.status == "upcoming"


def test_february_same_year_range_is_expired():
    result = evaluate_campaign_status(
        text="Kampanya Tarihleri 05 Şubat - 09 Şubat 2025",
        reference_date=TODAY,
    )
    assert result.start_date == "2025-02-05"
    assert result.end_date == "2025-02-09"
    assert result.status == "expired"
