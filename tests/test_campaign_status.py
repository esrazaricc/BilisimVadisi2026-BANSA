from datetime import date

from src.scraping.campaign_status import (
    detect_listing_status,
    evaluate_campaign_status,
)


def test_listing_expired_marker():
    status, evidence = detect_listing_status(
        "Bu kampanya sona ermiştir."
    )

    assert status == "expired"
    assert evidence


def test_remaining_days_means_active():
    status, evidence = detect_listing_status(
        "Son 17 Gün"
    )

    assert status == "active"
    assert evidence == "Son 17 Gün"


def test_passed_end_date_becomes_expired():
    result = evaluate_campaign_status(
        text="Kampanya 15 Temmuz 2026 tarihine kadar geçerlidir.",
        reference_date=date(2026, 7, 30),
    )

    assert result.status == "expired"
    assert result.end_date == "2026-07-15"
    assert result.reason == "end_date_passed"


def test_future_start_date_becomes_upcoming():
    result = evaluate_campaign_status(
        text=(
            "Kampanya 10 Ağustos 2026 tarihinde başlayacak "
            "ve 31 Ağustos 2026 tarihine kadar sürecektir."
        ),
        reference_date=date(2026, 7, 30),
    )

    assert result.status == "upcoming"
    assert result.start_date == "2026-08-10"


def test_active_date_range():
    result = evaluate_campaign_status(
        text=(
            "Kampanya 1 Temmuz 2026 - 31 Ağustos 2026 "
            "tarihleri arasında geçerlidir."
        ),
        reference_date=date(2026, 7, 30),
    )

    assert result.status == "active"
    assert result.start_date == "2026-07-01"
    assert result.end_date == "2026-08-31"


def test_listing_status_is_used_when_date_missing():
    result = evaluate_campaign_status(
        text="Kampanya koşulları açıklanmıştır.",
        listing_status="active",
        listing_evidence="Son 8 Gün",
        reference_date=date(2026, 7, 30),
    )

    assert result.status == "active"
    assert result.reason == "listing_status"
