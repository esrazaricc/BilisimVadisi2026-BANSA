import json

from src.scraping.campaign_content_override import (
    build_override_snapshot,
    find_content_override,
)


OLD_URL = (
    "https://kuveytturk.com.tr/kampanyalar/"
    "kendim-icin/kart-kampanyalari/"
    "konforda-vade-farksiz-9-aya-varan-taksit-firsati"
)


def test_override_is_found(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            [
                {
                    "bank_name": "Kuveyt Türk",
                    "source_urls": [OLD_URL],
                    "effective_url": (
                        "https://milesandsmiles."
                        "kuveytturk.com.tr/kampanyalar/konfor"
                    ),
                    "title": "Konfor Kampanyası",
                    "clean_text": "Kampanya metni yeterince uzundur.",
                    "campaign_end_date": "2026-12-31",
                    "current_status": "active",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = find_content_override(
        "Kuveyt Türk",
        OLD_URL,
        path=path,
    )

    assert result is not None
    assert result["title"] == "Konfor Kampanyası"


def test_wrong_bank_does_not_match(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            [
                {
                    "bank_name": "Kuveyt Türk",
                    "source_urls": [OLD_URL],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = find_content_override(
        "Albaraka Türk",
        OLD_URL,
        path=path,
    )

    assert result is None


def test_override_snapshot_is_active_and_traceable():
    page = {
        "bank_name": "Kuveyt Türk",
        "url": OLD_URL,
        "source_page": "",
        "page_type": "campaign_detail",
        "discovery_mode": "detail_links",
        "source_group": "Kart Kampanyaları",
        "listing_status": "active",
    }
    override = {
        "effective_url": (
            "https://milesandsmiles.kuveytturk.com.tr/"
            "kampanyalar/konfor"
        ),
        "title": (
            "Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!"
        ),
        "clean_text": (
            "Kampanya 31 Aralık 2026 tarihine kadar geçerlidir. "
            "Kuveyt Türk bireysel kredi kartlarıyla yapılan uygun "
            "alışverişlerde 9 aya varan taksit imkânı sunulur. "
            "Taksit seçimi ödeme anında yapılmalıdır."
        ),
        "campaign_end_date": "2026-12-31",
        "current_status": "active",
        "verification_note": "Resmî sayfa doğrulandı.",
    }

    snapshot = build_override_snapshot(page, override)

    assert snapshot.fetch_status == "ok"
    assert snapshot.fetch_method == "verified_content_override"
    assert snapshot.current_status == "active"
    assert snapshot.campaign_end_date == "2026-12-31"
    assert snapshot.requested_url == OLD_URL
    assert snapshot.text_length > 120
