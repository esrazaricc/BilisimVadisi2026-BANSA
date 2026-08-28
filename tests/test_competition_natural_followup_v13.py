import json

from src.chat_followup_context import resolve_followup_question
from src.competition_fast_router import _products, clear_fast_router_cache
from src.competition_natural_chat import answer_natural


def _text(query: str) -> str:
    result = answer_natural(query)
    assert result is not None
    return result.text


def test_tf_rate_followup_preserves_sigortali_intent_and_collapses_identical_vehicle_statuses():
    first = "Türkiye Finans'ta sigortalı taşıt finansmanı kar payı ne?"
    resolution = resolve_followup_question("36 ay", [first])

    assert resolution.used_context is True
    assert "sigortalı" in resolution.resolved_question.casefold()
    assert "kar payı" in resolution.resolved_question.casefold()
    assert "36 ay" in resolution.resolved_question.casefold()

    out = _text(resolution.resolved_question)
    assert "**Sigortalı · 36 ay:**" in out
    assert "**%3,48**" in out
    assert "Sigortalı · 0 km" not in out
    assert "Sigortalı · 2. El" not in out
    assert "Ürünleri Nelerdir" not in out


def test_vakif_short_name_motorcycle_numeric_followup_keeps_whole_semantic_turn():
    first = "Vakıf motosiklet finansmanı nasıl?"
    second = resolve_followup_question("600 bin için?", [first])
    assert second.used_context is True
    assert "Vakıf" in second.resolved_question
    assert "motosiklet" in second.resolved_question.casefold()
    assert "600000 TL" in second.resolved_question

    out = _text(second.resolved_question)
    assert "**%50**" in out
    assert "**300.000,00 TL**" in out
    assert "**36 ay**" in out

    third = resolve_followup_question("24 ay olur mu?", [first, second.resolved_question])
    assert third.used_context is True
    assert "motosiklet" in third.resolved_question.casefold()
    assert "600000 TL" in third.resolved_question
    assert "24 ay" in third.resolved_question

    out3 = _text(third.resolved_question)
    assert "**24 ay vade**" in out3
    assert "**36 aylık** üst sınırın içinde" in out3


def test_explicit_vehicle_compare_overrides_previous_motorcycle_context():
    history = [
        "Vakıf motosiklet finansmanı nasıl?",
        "Vakıf motosiklet finansmanı nasıl 600000 TL",
        "Vakıf motosiklet finansmanı nasıl 600000 TL 24 ay",
    ]
    current = "100 bin TL 36 ay araç finansmanlarını karşılaştır"
    resolution = resolve_followup_question(current, history)
    assert resolution.used_context is False
    assert resolution.resolved_question == current
    assert "motosiklet" not in resolution.resolved_question.casefold()


def test_dunya_motorcycle_query_uses_full_verified_vehicle_rule_table_not_last_band_only():
    out = _text("Dünya Katılım motosiklet finansmanı nasıl?")
    assert "### Dünya Katılım · Araç Finansmanı" in out
    assert "%70 finansman, 48 ay" in out
    assert "%50 finansman, 36 ay" in out
    assert "%30 finansman, 24 ay" in out
    assert "%20 finansman, 12 ay" in out


def test_emlak_vehicle_current_overlay_has_official_48_36_24_12_rules():
    clear_fast_router_cache()
    frame = _products()
    row = frame[
        frame["bank_name"].astype(str).eq("Türkiye Emlak Katılım")
        & frame["product_name"].astype(str).eq("Taşıt Finansmanı")
    ].iloc[0]

    assert int(float(row["maximum_maturity_months"])) == 48
    rules = json.loads(str(row["finance_rules_json"]))
    bands = rules["display_metadata"]["vehicle_value_rules"]
    assert [(int(x["max_financing_ratio"]), int(x["max_maturity_months"])) for x in bands] == [
        (70, 48), (50, 36), (30, 24), (20, 12)
    ]


def test_vehicle_compare_reports_dunya_and_emlak_verified_rules_without_fake_installment():
    out = _text("100 bin TL 36 ay araç finansmanlarını karşılaştır")

    assert "**Dünya Katılım:** resmî araç değeri tablosundaki sınırlar" in out
    assert "**Türkiye Emlak Katılım:** resmî araç değeri tablosundaki sınırlar" in out
    assert "400.000,00 TL'ye kadar %70/48 ay" in out
    assert "800.000,00 TL–1.200.000,00 TL %30/24 ay" in out
    assert "birebir kâr payı/taksit doğrulanmadığı için bankayı geri ödeme sıralamasına eklemiyorum" in out
    assert "sayısal vade yayımlanmamış" not in out
