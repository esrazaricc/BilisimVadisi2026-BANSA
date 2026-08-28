from src.scraping.campaign_page_fetcher import build_request_url


CONFIG = {
    "base_url": "https://www.turkiyefinans.com.tr",
}


def test_happy_apex_is_always_normalized_to_www():
    result = build_request_url(
        (
            "https://happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
        CONFIG,
        source_page=(
            "https://happycard.com.tr/kampanyalar/"
            "Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/Halalbooking.aspx"
    )


def test_happy_www_stays_www():
    result = build_request_url(
        (
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
        CONFIG,
        source_page=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/Halalbooking.aspx"
    )


def test_happy_query_is_preserved():
    result = build_request_url(
        (
            "https://happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx?x=1"
        ),
        CONFIG,
        source_page=(
            "https://happycard.com.tr/kampanyalar/"
            "Sayfalar/default.aspx"
        ),
    )

    assert result.endswith(
        "/kampanyalar/Sayfalar/Halalbooking.aspx?x=1"
    )


def test_other_external_source_is_not_changed_by_happy_rule():
    result = build_request_url(
        (
            "https://www.turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/ornek.aspx"
        ),
        CONFIG,
        source_page=(
            "https://www.turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
    )

    assert result.startswith(
        "https://www.turkiyefinansala.com/"
    )
