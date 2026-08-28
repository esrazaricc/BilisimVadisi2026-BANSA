import json

from src.scraping.campaign_page_fetcher import (
    extract_campaign_text,
    hash_text,
    load_discovered_pages,
    unwrap_url,
)


def test_unwrap_url_supports_nested_old_format():
    assert unwrap_url({"url": {"value": "https://example.com/a"}}) == (
        "https://example.com/a"
    )


def test_extracts_title_and_campaign_content():
    html = """
    <html>
      <head><title>Site Başlığı</title></head>
      <body>
        <header>Üst menü</header>
        <main class="campaign-detail">
          <h1>Market Kampanyası</h1>
          <p>1.000 TL harcamaya 100 TL ödül kazanabilirsiniz.</p>
          <p>Kampanya 31 Aralık 2026 tarihine kadar geçerlidir.</p>
        </main>
        <footer>Tüm Hakları Saklıdır</footer>
      </body>
    </html>
    """

    title, raw_text, clean_text = extract_campaign_text(html)

    assert title == "Market Kampanyası"
    assert "100 TL ödül" in raw_text
    assert "100 TL ödül" in clean_text
    assert "Üst menü" not in clean_text
    assert "Tüm Hakları Saklıdır" not in clean_text


def test_repeated_title_is_removed_from_clean_text():
    html = """
    <main>
      <h1>Yeni Müşteri Kampanyası</h1>
      <p>Yeni Müşteri Kampanyası</p>
      <p>Mobil uygulamadan müşteri olanlara ödül verilir.</p>
    </main>
    """

    title, _, clean_text = extract_campaign_text(html)

    assert title == "Yeni Müşteri Kampanyası"
    assert clean_text.startswith(
        "Mobil uygulamadan müşteri olanlara"
    )


def test_hash_is_stable_after_whitespace_normalization():
    assert hash_text("Kampanya   koşulları") == hash_text(
        "Kampanya koşulları"
    )


def test_discovered_pages_are_deduplicated_and_filterable(tmp_path):
    input_file = tmp_path / "pages.json"
    input_file.write_text(
        json.dumps(
            [
                {
                    "bank_name": "Albaraka Türk",
                    "url": "https://www.albaraka.com.tr/a?utm_source=x",
                    "source_page": "https://www.albaraka.com.tr/kampanyalar",
                },
                {
                    "bank_name": "Albaraka Türk",
                    "url": {"url": "https://albaraka.com.tr/a"},
                    "source_page": "",
                },
                {
                    "bank_name": "Başka Banka",
                    "url": "https://example.com/b",
                    "source_page": "",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    pages = load_discovered_pages(
        input_file,
        bank_name="Albaraka Türk",
    )

    assert len(pages) == 1
    assert pages[0]["url"] == "https://albaraka.com.tr/a"
