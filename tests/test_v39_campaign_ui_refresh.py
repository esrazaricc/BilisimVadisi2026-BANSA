from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v39_campaign_table_is_collapsed_and_scenario_driven():
    page = (ROOT / "pages" / "3_Kampanya_Karsilastirmasi.py").read_text(encoding="utf-8")
    assert "Detaylı kampanya karşılaştırma tablosunu göster" in page
    assert "Tahmini harcama / işlem tutarı" in page
    assert "Kullanım tipi" in page
    assert "BANSA kampanya önerisi" in page
    assert "Bilgi yok" not in page


def test_v39_shared_ui_components_exist():
    theme = (ROOT / "src" / "ui_theme.py").read_text(encoding="utf-8")
    assert "def render_insight_card" in theme
    assert "def render_recommendation_box" in theme
    assert "bansa-recommendation" in theme


def test_v39_finance_and_chatbot_core_calls_are_preserved():
    finance = (ROOT / "pages" / "2_Finansman_Karsilastirmasi.py").read_text(encoding="utf-8")
    chatbot = (ROOT / "pages" / "4_Chatbot.py").read_text(encoding="utf-8")
    assert "Detaylı ürün karşılaştırma tablosunu göster" in finance
    assert "ask_bansa" in chatbot
    assert "resolve_followup_question" in chatbot
