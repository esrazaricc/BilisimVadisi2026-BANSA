from src.scraping.campaign_page_fetcher import (
    extract_campaign_text,
)


def test_body_fallback_reads_campaign_bullets_outside_main():
    html = """
    <html>
      <head>
        <title>
          Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!
          | Miles&Smiles Kuveyt Türk
        </title>
      </head>
      <body>
        <main>
          <h1>
            Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!
          </h1>
        </main>

        <section class="campaign-information">
          <ul>
            <li>
              Kuveyt Türk Bireysel Kredi Kartları ile
              31 Aralık 2026 tarihine kadar Konfor Grubu
              mağazalarında peşin fiyatına 9 aya varan
              taksit imkanı sunulmaktadır.
            </li>
            <li>
              İşlemlerin taksitli olabilmesi için ödeme
              anında taksitli seçimin yapılması gerekmektedir.
            </li>
            <li>
              Kampanyaya tüm Kuveyt Türk Bireysel Kredi
              Kartları ve ek kartları dahildir.
            </li>
          </ul>
        </section>
      </body>
    </html>
    """

    title, raw_text, clean_text = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://milesandsmiles.kuveytturk.com.tr/"
            "kampanyalar/"
            "konforda-pesin-fiyatina-9-aya-varan-"
            "taksit-imkani-1876"
        ),
    )

    assert title.startswith("Konfor")
    assert len(clean_text) >= 120
    assert "31 Aralık 2026" in clean_text
    assert "9 aya varan taksit" in clean_text
    assert "tüm Kuveyt Türk Bireysel" in clean_text
    assert len(raw_text) >= len(clean_text)


def test_normal_main_content_is_not_replaced():
    html = """
    <html>
      <body>
        <main>
          <h1>Eğitim Harcamalarında Taksit Fırsatı</h1>
          <p>
            Kampanya kapsamında eğitim harcamalarınıza
            beş taksit fırsatı sunulmaktadır. Kampanya
            31 Aralık 2026 tarihine kadar geçerlidir.
            Katılım ve kullanım koşulları sayfada açıklanır.
          </p>
        </main>
        <section>
          Bu bölüm kampanyayla ilgisiz kısa bir açıklamadır.
        </section>
      </body>
    </html>
    """

    title, _, clean_text = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url="https://example.com/egitim-kampanyasi",
    )

    assert title == "Eğitim Harcamalarında Taksit Fırsatı"
    assert "beş taksit fırsatı" in clean_text
    assert "ilgisiz kısa" not in clean_text


def test_short_non_campaign_body_stays_short():
    html = """
    <html>
      <body>
        <main><h1>Test Başlığı</h1></main>
        <section>Çok kısa bilgi.</section>
      </body>
    </html>
    """

    _, _, clean_text = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url="https://example.com/test-basligi",
    )

    assert len(clean_text) < 120
