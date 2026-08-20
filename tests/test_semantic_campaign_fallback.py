from src.scraping.campaign_page_fetcher import (
    determine_fetch_status,
    extract_campaign_text,
    semantic_campaign_blocks,
)
from bs4 import BeautifulSoup


def test_semantic_blocks_survive_removed_parent():
    html = """
    <html>
      <head>
        <title>
          Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!
        </title>
      </head>
      <body>
        <main>
          <h1>
            Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!
          </h1>
        </main>

        <div class="campaign-header-detail">
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
            <li>
              Kuveyt Türk ve Konfor kampanya koşullarını
              değiştirme hakkına sahiptir.
            </li>
          </ul>
        </div>
      </body>
    </html>
    """

    title, _, clean_text = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url=(
            "https://milesandsmiles.kuveytturk.com.tr/"
            "kampanyalar/konforda-pesin-fiyatina-"
            "9-aya-varan-taksit-imkani-1876"
        ),
    )

    assert title.startswith("Konfor")
    assert "31 Aralık 2026" in clean_text
    assert "9 aya varan" in clean_text
    assert len(clean_text) >= 120
    assert determine_fetch_status(
        title,
        clean_text,
    ) == "ok"


def test_navigation_items_are_not_semantic_blocks():
    html = """
    <html>
      <body>
        <nav>
          <ul>
            <li>Kampanyalar</li>
            <li>Kredi Kartları</li>
          </ul>
        </nav>
        <section>
          <p>
            Kampanya 31 Aralık 2026 tarihine kadar
            geçerlidir ve 9 taksit fırsatı sunar.
          </p>
        </section>
      </body>
    </html>
    """

    soup = BeautifulSoup(html, "html.parser")
    blocks = semantic_campaign_blocks(
        soup,
        title="Test Kampanyası",
    )

    assert len(blocks) == 1
    assert blocks[0].startswith("Kampanya 31")


def test_short_unrelated_page_stays_short():
    html = """
    <html>
      <body>
        <main><h1>Test Sayfası</h1></main>
        <p>Kısa açıklama.</p>
      </body>
    </html>
    """

    title, _, clean_text = extract_campaign_text(
        html,
        bank_name="Kuveyt Türk",
        url="https://example.com/test-sayfasi",
    )

    assert determine_fetch_status(
        title,
        clean_text,
    ) == "short_content"
