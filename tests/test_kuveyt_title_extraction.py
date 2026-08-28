from bs4 import BeautifulSoup

from src.scraping.campaign_page_fetcher import (
    extract_campaign_text,
    extract_title,
    is_generic_title,
    title_from_url,
)


def test_generic_bank_h1_is_skipped_for_campaign_heading():
    html = """
    <html>
      <head>
        <title>Kuveyt Türk Katılım Bankası</title>
      </head>
      <body>
        <h1>Kuveyt Türk Katılım Bankası</h1>
        <main>
          <h3>Yeni Müşterilere Özel İhtiyaç Kart'ta %1,99 Oran Fırsatı!</h3>
          <p>100.000 TL'ye kadar avantajlı kampanya.</p>
        </main>
      </body>
    </html>
    """

    title, _, _ = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://www.kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/musteri-ol-kampanyalari/"
            "yeni-musterilere-ozel-ihtiyac-kartta-199-oran-firsati"
        ),
    )

    assert title.startswith("Yeni Müşterilere Özel")


def test_json_ld_headline_is_used():
    html = """
    <html>
      <head>
        <title>Kuveyt Türk Katılım Bankası</title>
        <script type="application/ld+json">
          {
            "@type": "Article",
            "headline": "MTV Ödemelerinizde Vade Farksız 3 Taksit Fırsatı!"
          }
        </script>
      </head>
      <body><p>Kampanya detayları.</p></body>
    </html>
    """

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(
        soup,
        bank_name="Kuveyt Türk",
        url="https://example.com/test",
    )

    assert title.startswith("MTV Ödemelerinizde")


def test_url_slug_is_last_fallback():
    html = """
    <html>
      <head><title>Kuveyt Türk Katılım Bankası</title></head>
      <body><h1>Kuveyt Türk Katılım Bankası</h1></body>
    </html>
    """

    title, _, _ = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://www.kuveytturk.com.tr/kampanyalar/"
            "isim-icin/kobi-kampanyalari/"
            "arac-finansmani-onaylanan-kobilere-hgs-kampanyasi"
        ),
    )

    assert title == (
        "Araç Finansmanı Onaylanan Kobilere HGS Kampanyası"
    )


def test_generic_title_detection():
    assert is_generic_title(
        "Kuveyt Türk Katılım Bankası",
        bank_name="Kuveyt Türk",
    )
    assert not is_generic_title(
        "Gelir Vergisi Ödemelerinizde 3 Taksit Fırsatı!",
        bank_name="Kuveyt Türk",
    )


def test_turkish_slug_title():
    title = title_from_url(
        (
            "https://example.com/"
            "yeni-musterilere-ozel-ihtiyac-finansmani-kampanyasi"
        )
    )

    assert title == (
        "Yeni Müşterilere Özel İhtiyaç Finansmanı Kampanyası"
    )
