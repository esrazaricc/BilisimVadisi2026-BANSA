from src.scraping.campaign_page_fetcher import extract_campaign_text


def test_nested_nodes_under_removed_parent_do_not_raise_attribute_error():
    html = """
    <html>
      <body>
        <div class="cookie-banner">
          <div class="cookie-content">
            <span class="cookie-title">Çerez bildirimi</span>
          </div>
        </div>

        <main class="campaign-detail">
          <h1>World Kampanyası</h1>
          <p>
            Kampanya kapsamında seçili harcamalara
            vade farksız 6 taksit uygulanır.
          </p>
          <p>Kampanya 31 Aralık 2026 tarihine kadar geçerlidir.</p>
        </main>
      </body>
    </html>
    """

    title, raw_text, clean_text = extract_campaign_text(html)

    assert title == "World Kampanyası"
    assert "vade farksız 6 taksit" in raw_text
    assert "vade farksız 6 taksit" in clean_text
    assert "Çerez bildirimi" not in clean_text


def test_nested_header_nodes_do_not_break_cleanup():
    html = """
    <html>
      <body>
        <header class="site-header">
          <div class="header-inner">
            <a class="header-link">Ana Sayfa</a>
          </div>
        </header>
        <article>
          <h1>Akaryakıt Kampanyası</h1>
          <p>Akaryakıt harcamalarına 500 TL Worldpuan fırsatı.</p>
          <p>Kampanya koşulları geçerlidir.</p>
        </article>
      </body>
    </html>
    """

    title, _, clean_text = extract_campaign_text(html)

    assert title == "Akaryakıt Kampanyası"
    assert "500 TL Worldpuan" in clean_text
    assert "Ana Sayfa" not in clean_text

