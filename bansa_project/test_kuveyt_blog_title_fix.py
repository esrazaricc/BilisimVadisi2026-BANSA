from bs4 import BeautifulSoup

from src.scraping.campaign_page_fetcher import (
    extract_campaign_text,
    extract_title,
    is_usable_title,
)


def test_blog_heading_is_rejected_and_slug_used():
    html = """
    <html>
      <head>
        <title>Kuveyt Türk Katılım Bankası</title>
      </head>
      <body>
        <main>
          <h1>Blog</h1>
          <p>Kampanya detayları burada yer alır.</p>
        </main>
      </body>
    </html>
    """

    title, _, _ = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://www.kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/kart-kampanyalari/"
            "akaryakit-odemelerinizde-500-tl-worldpuan"
        ),
    )

    assert title == (
        "Akaryakıt Ödemelerinizde 500 TL Worldpuan"
    )


def test_real_heading_beats_url_fallback():
    html = """
    <html>
      <body>
        <main>
          <h1>Blog</h1>
          <h2>Akaryakıt Ödemelerinizde 500 TL Worldpuan!</h2>
        </main>
      </body>
    </html>
    """

    title, _, _ = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://www.kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/kart-kampanyalari/"
            "akaryakit-odemelerinizde-500-tl-worldpuan"
        ),
    )

    assert title == (
        "Akaryakıt Ödemelerinizde 500 TL Worldpuan!"
    )


def test_blog_is_not_usable_title():
    assert not is_usable_title(
        "Blog",
        bank_name="Kuveyt Türk",
    )


def test_meta_campaign_title_beats_blog():
    html = """
    <html>
      <head>
        <meta
          property="og:title"
          content="Yeni Müşterilere Özel İhtiyaç Finansmanı Kampanyası"
        />
      </head>
      <body><main><h1>Blog</h1></main></body>
    </html>
    """

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(
        soup,
        bank_name="Kuveyt Türk",
        url=(
            "https://www.kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/musteri-ol-kampanyalari/"
            "yeni-musterilere-ozel-ihtiyac-finansmani-kampanyasi"
        ),
    )

    assert title == (
        "Yeni Müşterilere Özel İhtiyaç Finansmanı Kampanyası"
    )
