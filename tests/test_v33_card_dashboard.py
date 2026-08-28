from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "curated_dashboard"

EXPECTED_BANKS = {
    "Adil Katılım","Albaraka Türk","Dünya Katılım","Hayat Finans","Kuveyt Türk",
    "T.O.M. Katılım","Türkiye Emlak Katılım","Türkiye Finans","Vakıf Katılım","Ziraat Katılım"
}

def load():
    return pd.read_csv(DATA / "cards_dashboard_static.csv", dtype=str, keep_default_na=False)

def test_v33_card_dashboard_bank_universe_and_no_blanks():
    df = load()
    assert set(df["Banka"]) == EXPECTED_BANKS
    assert not (df.apply(lambda col: col.astype(str).str.strip().eq("")).any().any())

def test_v33_critical_fee_facts():
    df = load()
    def get(bank, card):
        return df[(df["Banka"] == bank) & (df["Kart Adı"] == card)].iloc[0]
    assert "0 TL" in get("Albaraka Türk","World Klasik Kart")["Yıllık Kart Ücreti"]
    assert "0 TL" in get("Dünya Katılım","DKart Kredi Kartı")["Yıllık Kart Ücreti"]
    assert "0 TL" in get("Kuveyt Türk","Sağlam Kart")["Yıllık Kart Ücreti"]
    assert "1.000 TL" in get("T.O.M. Katılım","Hadi Black Kredi Kartı")["Yıllık Kart Ücreti"]
    assert "300,30 TL" in get("Türkiye Finans","Happy Kart Silver")["Yıllık Kart Ücreti"]
    assert "0 TL" in get("Ziraat Katılım","Bankkart Ücretsiz")["Yıllık Kart Ücreti"]

def test_v33_adil_does_not_invent_card():
    df = load()
    row = df[df["Banka"] == "Adil Katılım"].iloc[0]
    assert row["Kart Türü"] == "Ürün yayımlanmamış"
    assert "doğrulanmış kart ürünü bulunamadı" in row["Kart Adı"].lower()

def test_v33_ui_files_exist_and_nav_has_cards():
    assert (ROOT / "pages" / "4_Kart_Karsilastirmasi.py").exists()
    ui = (ROOT / "src" / "ui_theme.py").read_text(encoding="utf-8")
    assert '"cards"' in ui
    assert "pages/4_Kart_Karsilastirmasi.py" in ui
    assert 'def render_sidebar_navigation(active: str = "")' in ui

def test_v33_existing_dashboard_nav_calls_are_valid():
    finance = (ROOT / "pages" / "2_Finansman_Karsilastirmasi.py").read_text(encoding="utf-8")
    campaign = (ROOT / "pages" / "3_Kampanya_Karsilastirmasi.py").read_text(encoding="utf-8")
    assert 'render_sidebar_navigation("finance")' in finance
    assert 'render_sidebar_navigation("campaign")' in campaign
