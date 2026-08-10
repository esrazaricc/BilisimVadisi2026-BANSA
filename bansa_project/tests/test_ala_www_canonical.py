from src.scraping.campaign_page_fetcher import build_request_url


CONFIG = {
    "base_url": "https://www.turkiyefinans.com.tr",
}


def test_ala_apex_is_normalized_to_www():
    result = build_request_url(
        (
            "https://turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/ala-aksa-nisan-2026.aspx"
        ),
        CONFIG,
        source_page=(
            "https://turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/ala-aksa-nisan-2026.aspx"
    )


def test_ala_www_stays_www():
    result = build_request_url(
        (
            "https://www.turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/ala-aksa-nisan-2026.aspx"
        ),
        CONFIG,
        source_page=(
            "https://www.turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/ala-aksa-nisan-2026.aspx"
    )


def test_ala_path_and_query_are_preserved():
    result = build_request_url(
        (
            "https://turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/ala-bes-2026.aspx?x=1"
        ),
        CONFIG,
        source_page=(
            "https://turkiyefinansala.com/tr-tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
    )

    assert result == (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/ala-bes-2026.aspx?x=1"
    )


def test_happy_rule_is_preserved():
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
