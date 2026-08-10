from src.scraping.campaign_page_fetcher import (
    extract_campaign_text,
    strip_site_title_suffix,
)


def test_kuveyt_pipe_suffix_removed():
    value = strip_site_title_suffix(
        (
            "Akaryakıt Harcamalarınıza Her Ay Ekstra "
            "2.000 Mil'e Varan Fırsat! | "
            "Kuveyt Türk Katılım Bankası"
        ),
        bank_name="Kuveyt Türk",
    )

    assert value == (
        "Akaryakıt Harcamalarınıza Her Ay Ekstra "
        "2.000 Mil'e Varan Fırsat!"
    )


def test_dash_suffix_removed():
    value = strip_site_title_suffix(
        (
            "E-Ticaret Pazaryeri Satıcılarına Özel "
            "Vade Farksız 3 Taksit! - Kuveyt Türk"
        ),
        bank_name="Kuveyt Türk",
    )

    assert value == (
        "E-Ticaret Pazaryeri Satıcılarına Özel "
        "Vade Farksız 3 Taksit!"
    )


def test_internal_hyphen_is_preserved():
    value = strip_site_title_suffix(
        "E-Ticaret Harcamalarınıza Ekstra Mil Fırsatı",
        bank_name="Kuveyt Türk",
    )

    assert value == (
        "E-Ticaret Harcamalarınıza Ekstra Mil Fırsatı"
    )


def test_extract_campaign_text_returns_clean_title():
    html = """
    <html>
      <head>
        <meta
          property="og:title"
          content="Eğitim Harcamalarınızda 5 Taksit Fırsatı! | Kuveyt Türk Katılım Bankası"
        />
      </head>
      <body>
        <main>
          <p>
            Kampanya kapsamında eğitim harcamalarınıza
            vade farksız beş taksit fırsatı sunulmaktadır.
            Kampanya koşulları ve katılım bilgileri açıklanır.
          </p>
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
            "egitim-harcamalarinizda-5-taksit-firsati"
        ),
    )

    assert title == (
        "Eğitim Harcamalarınızda 5 Taksit Fırsatı!"
    )


def test_non_bank_subtitle_is_not_removed():
    value = strip_site_title_suffix(
        "Kart Kampanyası | Temmuz Fırsatları",
        bank_name="Kuveyt Türk",
    )

    assert value == "Kart Kampanyası | Temmuz Fırsatları"
