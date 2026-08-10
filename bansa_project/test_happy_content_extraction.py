from src.scraping.campaign_page_fetcher import (
    MIN_ACCEPTABLE_TEXT_LENGTH,
    extract_campaign_text,
)


def happy_like_html():
    # "campaign-header-content" sınıfı mevcut agresif temizleyicide
    # header kelimesi nedeniyle tamamen silinir. İçerik p/li yerine
    # div/span içinde tutulduğu için semantic blok yedeği de tek başına
    # yeterli değildir.
    campaign_text = (
        "Kampanya kapsamında Happy Bonus Kart sahipleri "
        "Halalbooking rezervasyonlarında indirim avantajından "
        "yararlanabilir. Kampanyaya katılım, geçerlilik tarihleri, "
        "harcama koşulları ve diğer kampanya koşulları bu sayfada "
        "açıklanmaktadır. "
    ) * 3

    return f"""
    <html>
      <head>
        <title>
          Happy Bonus Kartınıza Halalbooking Ayrıcalığı
        </title>
      </head>
      <body>
        <header>Happy Kart Menü</header>
        <div class="campaign-header-content">
          <div class="campaign-name">
            Happy Bonus Kartınıza Halalbooking Ayrıcalığı
          </div>
          <div class="campaign-copy">
            <span>{campaign_text}</span>
          </div>
        </div>
        <footer>İletişim ve yasal bilgiler</footer>
      </body>
    </html>
    """


def test_happy_title_comes_from_document_title():
    title, _, _ = extract_campaign_text(
        happy_like_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert title == (
        "Happy Bonus Kartınıza Halalbooking Ayrıcalığı"
    )


def test_happy_body_survives_aggressive_class_cleanup():
    _, raw_text, clean_text = extract_campaign_text(
        happy_like_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert len(raw_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
    assert len(clean_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
    assert "Halalbooking" in clean_text
    assert "kampanya koşulları" in clean_text.casefold()


def test_navigation_and_footer_noise_are_not_used_as_campaign_text():
    _, _, clean_text = extract_campaign_text(
        happy_like_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert "Happy Kart Menü" not in clean_text
    assert "İletişim ve yasal bilgiler" not in clean_text


def test_regular_campaign_extraction_still_works():
    html = """
    <html>
      <head><title>Örnek Kampanya</title></head>
      <body>
        <main>
          <h1>Örnek Kampanya</h1>
          <p>
            Kampanya kapsamında 31 Aralık 2026 tarihine kadar
            alışverişlerinizde indirim ve taksit avantajı sunulur.
            Kampanyaya katılım koşulları sayfada açıklanmıştır.
          </p>
        </main>
      </body>
    </html>
    """

    title, _, clean_text = extract_campaign_text(
        html,
        bank_name="Türkiye Finans",
        url=(
            "https://www.turkiyefinans.com.tr/"
            "kampanyalar/ornek.aspx"
        ),
    )

    assert title == "Örnek Kampanya"
    assert len(clean_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
