from __future__ import annotations

from src.chat_followup_context import resolve_followup_question
from src.competition_natural_chat import answer_natural
from src.competition_surface_naturalizer import maybe_naturalize_fast_answer


def test_bare_maturity_keeps_rate_context():
    r = resolve_followup_question(
        "36 ay",
        ["Türkiye Finans'ta sigortalı taşıt finansmanı kar payı ne?"],
    )
    q = r.resolved_question.casefold()
    assert "türkiye finans" in q
    assert "sigortal" in q
    assert "36 ay" in q
    assert "kar pay" in q


def test_numeric_turn_keeps_two_bank_housing_comparison():
    r = resolve_followup_question(
        "500 bin TL 36 ay",
        ["Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır"],
    )
    q = r.resolved_question.casefold()
    assert "albaraka" in q
    assert "türkiye finans" in q
    assert "konut" in q
    assert "500000" in q
    assert "36 ay" in q
    assert "karşılaştır" in q


def test_explicit_bank_and_new_product_clears_old_compare_state():
    r = resolve_followup_question(
        "Albaraka Türk eğitim finansmanının avantajları neler?",
        [
            "Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır",
            "Albaraka Türk ve Türkiye Finans konut finansmanı 500000 TL 36 ay karşılaştır",
        ],
    )
    assert r.resolved_question == "Albaraka Türk eğitim finansmanının avantajları neler?"
    assert not r.used_context
    assert "konut" not in r.resolved_question.casefold()
    assert "500000" not in r.resolved_question

    answer = answer_natural(r.resolved_question)
    assert answer is not None
    assert "Eğitim Finansmanı" in answer.text
    assert "Konut Finansmanı" not in answer.text


def test_explicit_product_without_bank_inherits_only_one_recent_bank():
    r = resolve_followup_question(
        "Peki eğitim finansmanının avantajları neler?",
        ["Albaraka Türk konut finansmanı 500000 TL 36 ay"],
    )
    q = r.resolved_question.casefold()
    assert "albaraka" in q
    assert "eğitim finansman" in q
    assert "konut" not in q
    assert "500000" not in q
    assert "36 ay" not in q


def test_fast_surface_naturalizer_keeps_deterministic_sources_and_numbers(monkeypatch):
    answer = answer_natural("Albaraka Türk konut finansmanı özellikleri nelerdir?")
    assert answer is not None
    assert answer.route == "finance_product_conversation"

    def fake_generate(question, facts):
        return (
            "Albaraka Türk'ün konut finansmanı, ev sahibi olmak isteyenler için "
            "120 aya kadar vade imkânı içeriyor. Kâr payı sabit değil; tutar ve "
            "vadeye göre hesaplama aracında belirleniyor."
        )

    monkeypatch.setattr("src.competition_surface_naturalizer._generate", fake_generate)
    polished, used = maybe_naturalize_fast_answer(
        "Albaraka Türk konut finansmanı özellikleri nelerdir?",
        answer,
    )
    assert used is True
    assert polished.backend == "competition_fast_qwen_surface"
    assert "120 aya kadar" in polished.text
    assert "Resmî ürün kaynağı" in polished.text
    assert "100.000,00" not in polished.text  # model may omit irrelevant reference example


def test_surface_naturalizer_rejects_invented_number(monkeypatch):
    answer = answer_natural("Albaraka Türk konut finansmanı özellikleri nelerdir?")
    assert answer is not None

    monkeypatch.setattr(
        "src.competition_surface_naturalizer._generate",
        lambda question, facts: "Bu üründe 240 aya kadar vade bulunuyor.",
    )
    polished, used = maybe_naturalize_fast_answer(
        "Albaraka Türk konut finansmanı özellikleri nelerdir?",
        answer,
    )
    assert used is False
    assert "240" not in polished.text
    assert "120 ay" in polished.text
    assert "Resmî ürün kaynağı" in polished.text


def test_explicit_global_vehicle_compare_does_not_inherit_previous_bank():
    r = resolve_followup_question(
        "100 bin TL 36 ay araç finansmanlarını karşılaştır",
        [
            "Vakıf Katılım motosiklet finansmanı nasıl?",
            "Vakıf Katılım motosiklet finansmanı 600000 TL motosiklet değeri",
        ],
    )
    assert r.used_context is False
    assert r.resolved_question == "100 bin TL 36 ay araç finansmanlarını karşılaştır"


def test_campaign_merchant_switch_inherits_only_campaign_bank():
    r = resolve_followup_question(
        "Peki Vatan Bilgisayar kampanyası var mı?",
        ["Ziraat Katılım MediaMarkt kampanyasında kaç taksit var?"],
    )
    assert r.used_context is True
    assert r.resolved_question.startswith("Ziraat Katılım -")
    assert "taşıt" not in r.resolved_question.casefold()
    assert "motosiklet" not in r.resolved_question.casefold()
