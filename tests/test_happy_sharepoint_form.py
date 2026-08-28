from src.scraping.campaign_page_fetcher import (
    MIN_ACCEPTABLE_TEXT_LENGTH,
    extract_campaign_text,
)


def sharepoint_campaign_html() -> str:
    campaign_text = (
        "Halalbooking'den Happy Karta özel yüzde 15'e varan indirim "
        "sunulmaktadır. Happy Bonus kart sahipleri kampanya koşulları "
        "kapsamında turizm ve seyahat harcamalarında avantajdan "
        "yararlanabilir. Kampanyaya katılım ve kullanım şartları "
        "sayfada açıklanmaktadır. "
    ) * 3

    return f"""
    <html>
      <head>
        <title>
          Happy Bonus Kartınıza Halalbooking Ayrıcalığı
        </title>
      </head>
      <body>
        <form id="aspnetForm">
          <header>Happy Kart Menü</header>

          <div class="campaign-detail">
            <h2>
              Happy Bonus Kartınıza Halalbooking Ayrıcalığı
            </h2>

            <div class="campaign-info">
              01 Ocak - 31 Aralık
            </div>

            <div class="campaign-text">
              <div style="display:none">Sayfa İçeriği</div>
              <p>{campaign_text}</p>
            </div>
          </div>

          <footer>Site haritası ve iletişim</footer>
        </form>
      </body>
    </html>
    """


def test_sharepoint_form_children_are_preserved():
    title, raw_text, clean_text = extract_campaign_text(
        sharepoint_campaign_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert title == (
        "Happy Bonus Kartınıza Halalbooking Ayrıcalığı"
    )
    assert len(raw_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
    assert len(clean_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
    assert "Halalbooking" in clean_text


def test_specific_campaign_text_is_preferred():
    _, _, clean_text = extract_campaign_text(
        sharepoint_campaign_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert "01 Ocak - 31 Aralık" not in clean_text
    assert "Happy Kart Menü" not in clean_text
    assert "Site haritası ve iletişim" not in clean_text


def test_hidden_sharepoint_label_is_removed():
    _, _, clean_text = extract_campaign_text(
        sharepoint_campaign_html(),
        bank_name="Türkiye Finans",
        url=(
            "https://www.happycard.com.tr/kampanyalar/"
            "Sayfalar/Halalbooking.aspx"
        ),
    )

    assert not clean_text.startswith("Sayfa İçeriği")
    assert "Sayfa İçeriği" not in clean_text


def test_regular_form_based_campaign_still_works():
    html = """
    <html>
      <head><title>Örnek Kart Kampanyası</title></head>
      <body>
        <form>
          <main>
            <h1>Örnek Kart Kampanyası</h1>
            <p>
              Kampanya kapsamında 31 Aralık 2026 tarihine kadar
              alışverişlerde indirim ve taksit avantajı sunulur.
              Kampanyaya katılım koşulları sayfada açıklanmıştır.
            </p>
          </main>
        </form>
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

    assert title == "Örnek Kart Kampanyası"
    assert len(clean_text) >= MIN_ACCEPTABLE_TEXT_LENGTH
