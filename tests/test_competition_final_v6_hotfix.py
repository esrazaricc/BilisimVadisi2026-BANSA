from src.chat_followup_context import resolve_followup_question
from src.competition_natural_chat import answer_natural


def text(q: str) -> str:
    r = answer_natural(q)
    assert r is not None
    return r.text


def test_tf_housing_current_official_table_beats_stale_snapshot():
    out = text("Türkiye Finans ilk konut sigortalı 36 ay kar payı oranı ne")
    assert "%3,35" in out
    assert "%3,58" not in out
    assert "resmî vade/fiyatlama tablosundan" in out


def test_tf_500k_36_uses_current_335_rate():
    out = text("500.000 TL 36 ay konut finansmanında Vakıf Katılım ile Türkiye Finans karşılaştır")
    assert "Türkiye Finans" in out and "Vakıf Katılım" in out
    assert "%3,35" in out
    assert "24.113,47 TL" in out
    assert "24.926,27 TL" not in out


def test_sigortali_vehicle_rate_is_not_insurance_fee_intent():
    out = text("türkiye finansta sigortalı tasıt finansmanı kar payı oranı ne")
    assert "Sigortalı" in out
    assert "36 ay %3,48" in out
    assert "Sigorta masrafı" not in out


def test_explicit_vehicle_family_overrides_old_housing_context():
    hist = [
        "Konut finansmanında Vakıf Katılım mı Türkiye Finans mı daha avantajlı?",
        "Vakıf Katılım ve Türkiye Finans konut finansmanı 500000 TL 36 ay karşılaştır",
    ]
    r = resolve_followup_question("araç finansmanında 100 bin tl 36 ay vade", hist)
    assert r.used_context is False
    assert "konut" not in r.resolved_question.casefold()
    out = text(r.resolved_question)
    assert "taşıt/araç finansmanı" in out
    assert "İlk konut" not in out


def test_tf_vehicle_official_table_can_calculate_requested_scenario():
    out = text("araç finansmanında 100 bin tl 36 ay vade")
    assert "Türkiye Finans" in out
    assert "%3,48" in out
    assert "güncel resmî fiyatlama tablosundan BANSA hesabı" in out


def test_ziraat_teknosa_current_campaign_is_found():
    out = text("ziraat katılımın Teknosa'da 3 Taksit kampanyasında kaç taksit imkanı var")
    assert "Ziraat Katılım · Teknosa'da 3 Taksit" in out
    assert "**3 taksit**" in out
    assert "teknosada-3-taksit" in out


def test_wrong_bank_schafer_never_falls_back_to_petlas():
    out = text("ziraat katılım da Paraf ile Schafer’de Peşin Fiyatına 9 Taksit! özellikleri nedir")
    assert "alakasız bir kampanyayı" in out
    assert "PETLAS" not in out
    assert "Türkiye Emlak Katılım · Paraf ile Schafer" in out


def test_campaign_scrape_menu_noise_is_removed():
    out = text("PETLAS kampanyasının özellikleri nedir")
    assert "PETLAS'ta Peşin Fiyatına 6 Taksit" in out
    assert "Tüm Kampanyalar" not in out
    assert "Kuyum, Optik ve Saat" not in out


def test_family_only_query_does_not_dump_raw_catalog():
    out = text("ilk konut için")
    assert "Konut Finansmanı seçenekleri" in out
    assert "Aynı filtrede" not in out
    # Fresh TF table exists; don't repeat its stale 3.58 snapshot as reference.
    tf_part = out.split("Türkiye Finans", 1)[1].split("Albaraka Türk", 1)[0]
    assert "%3,58" not in tf_part


def test_schafer_without_wrong_bank_resolves_to_emlak_campaign():
    out = text("Schafer'da 9 Taksit kampanyası özellikleri nedir")
    assert "Türkiye Emlak Katılım" in out
    assert "**9 taksit**" in out
