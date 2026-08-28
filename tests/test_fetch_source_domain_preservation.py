from src.scraping.campaign_page_fetcher import build_request_url


TF_CONFIG = {
    "base_url": "https://www.turkiyefinans.com.tr",
}


def test_happy_card_apex_is_canonicalized_to_www():
    discovered = (
        "https://happycard.com.tr/kampanyalar/"
        "Sayfalar/Halalbooking.aspx"
    )
    source_page = (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/default.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=source_page,
    )

    assert result == (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/Halalbooking.aspx"
    )


def test_ala_domain_is_not_rewritten():
    discovered = (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/ornek.aspx"
    )
    source_page = (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/default.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=source_page,
    )

    assert result == discovered


def test_untrusted_foreign_domain_is_still_rewritten():
    discovered = (
        "https://ornek-site.com/kampanyalar/test.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=(
            "https://www.turkiyefinans.com.tr/"
            "tr-tr/kampanyalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.turkiyefinans.com.tr/"
        "kampanyalar/test.aspx"
    )


def test_normal_bank_campaign_still_uses_configured_host():
    discovered = (
        "https://turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=(
            "https://turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
    )
