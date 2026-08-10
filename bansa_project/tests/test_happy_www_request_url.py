from src.scraping.campaign_page_fetcher import build_request_url


TF_CONFIG = {
    "base_url": "https://www.turkiyefinans.com.tr",
}


def test_happy_apex_is_normalized_to_www_source_host():
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


def test_happy_existing_www_is_preserved():
    discovered = (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/test.aspx"
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

    assert result == discovered


def test_ala_source_host_is_preserved():
    discovered = (
        "https://turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
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

    assert result == (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
    )


def test_normal_tf_url_still_uses_configured_www_host():
    discovered = (
        "https://turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
    )
    source_page = (
        "https://turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/default.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=source_page,
    )

    assert result == (
        "https://www.turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/test.aspx"
    )


def test_foreign_domain_is_not_trusted():
    discovered = (
        "https://ornek-site.com/kampanyalar/test.aspx"
    )
    source_page = (
        "https://www.turkiyefinans.com.tr/"
        "tr-tr/kampanyalar/default.aspx"
    )

    result = build_request_url(
        discovered,
        TF_CONFIG,
        source_page=source_page,
    )

    assert result == (
        "https://www.turkiyefinans.com.tr/"
        "kampanyalar/test.aspx"
    )
