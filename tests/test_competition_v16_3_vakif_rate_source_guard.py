from src.competition_response_service import ask_bansa
from src.competition_fast_router import clear_fast_router_cache


def _ask(q: str) -> str:
    clear_fast_router_cache()
    return ask_bansa(q).text


def test_vakif_vehicle_rate_question_does_not_publish_calculator_rate():
    text = _ask("Vakıf Katılım taşıt finansmanında 36 ay kâr payı ne?")
    assert "%3,40" not in text and "%3.40" not in text
    assert "%3,19" not in text
    assert "kullanıcı tarafından belirlenebildiği" in text
    assert "güncel oranı olarak sunmuyorum" in text


def test_vakif_motorcycle_product_does_not_say_rate_is_scenario_determined_by_bank():
    text = _ask("Vakıf Katılım motosiklet finansmanı nasıl?")
    assert "oran senaryoya göre belirleniyor" not in text
    assert "kullanıcı tarafından belirlenebildiği" in text
    assert "bankanın güncel oranı olarak kabul etmiyorum" in text


def test_vakif_vehicle_payment_is_not_derived_from_rate_input_or_old_snapshot():
    text = _ask("100 bin TL 36 ay Vakıf Katılım taşıt finansmanı aylık taksit ne kadar?")
    assert "uydurmuyorum" in text
    assert "%3,40" not in text and "%3.40" not in text
    assert "%3,19" not in text
    assert "194.286,46" not in text


def test_vakif_remains_in_vehicle_compare_without_unverified_profit_rate():
    text = _ask("100 bin TL 36 ay araç finansmanlarını karşılaştır")
    assert "**Vakıf Katılım:**" in text
    assert "kullanıcı tarafından belirlenebildiği" in text
    assert "%3,40" not in text and "%3.40" not in text
    assert "%3,19" not in text
