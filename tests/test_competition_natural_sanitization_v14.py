from src.competition_response_service import ask_bansa


def _text(question: str) -> str:
    return ask_bansa(question).text


def test_product_overviews_do_not_render_scraped_faq_or_navigation_as_copy():
    emlak = _text("Türkiye Emlak Katılım taşıt finansmanı nasıl?")
    dunya = _text("Dünya Katılım araç finansmanı nasıl?")
    vakif = _text("Vakıf Katılım konut finansmanı nasıl?")
    ziraat = _text("Ziraat Katılım taşıt finansmanı nasıl?")

    assert "Çevreci Araç Finansmanı kullandırılır" not in emlak
    assert "Sıkça Sorulan Sorular" not in dunya
    assert "Kasko Değerinin Tamamını Finansman Olarak Kullanabilir Miyim" not in dunya
    assert "Kredi Notu Önemli mi?" not in vakif
    assert "Diğer Finansman Türleri" not in vakif
    assert "Taşıt Finansmanı Kullanmalıyım?" not in ziraat


def test_vehicle_compare_collapses_financially_identical_status_variants():
    out = _text("100 bin TL 36 ay araç finansmanlarını karşılaştır")

    assert out.count("| **Türkiye Finans** | Sigortalı |") == 1
    assert out.count("| **Türkiye Finans** | Sigortasız |") == 1
    assert "0Km Sigortali" not in out
    assert "2El Sigortali" not in out
    assert "Yeni Binek" not in out or "2. el / 0 km" in out or "0 km / 2. el" in out
    assert "exact kâr payı/taksit" not in out
    assert "birebir kâr payı/taksit" in out
