from src.competition_response_service import ask_bansa
from src.competition_natural_chat import answer_natural
from src.chat_followup_context import resolve_followup_question
from src.competition_fast_router import _products, _structured_fee_value


def test_albaraka_housing_allocation_fee_is_percent_rule_not_fixed_example():
    result = ask_bansa("Albaraka Türk konut finansmanı tahsis ücreti")
    assert "%0,50" in result.text
    assert "finansman tutarının" in result.text
    assert "**Tahsis ücreti: 500,00 TL" not in result.text


def test_albaraka_housing_allocation_fee_calculates_only_when_amount_is_given():
    result = ask_bansa("Albaraka Türk 100.000 TL konut finansmanı tahsis ücreti ne kadar?")
    assert "%0,50" in result.text
    assert "bu tutarda 500,00 TL" in result.text


def test_structured_fee_rules_have_precedence_for_all_products_that_define_them():
    products = _products()
    checked = 0
    for _, row in products.iterrows():
        raw = row.get("finance_rules_json")
        if not isinstance(raw, str) or '"fee_rules"' not in raw:
            continue
        for attr in ("allocation_fee", "appraisal_fee", "mortgage_fee", "insurance_fee"):
            value, _ = _structured_fee_value(row, attr)
            if value:
                checked += 1
                assert len(value) < 500
                assert "Tüm Çerezleri" not in value
                assert "Ana Menü" not in value
    assert checked >= 40


def test_tf_housing_fee_summary_does_not_leak_scraped_navigation_text():
    result = ask_bansa("Türkiye Finans konut finansmanı masrafları neler?")
    assert "%0,50" in result.text
    assert "Tüm Çerezleri" not in result.text
    assert "Ana Menü" not in result.text
    assert "İnternet Şubesi" not in result.text


def test_numeric_maturity_compare_is_not_misrouted_as_max_maturity_fact():
    result = answer_natural("100 bin tl 36 ay vade için konut finansmanlarını kıyasla")
    assert result is not None
    assert result.route == "finance_compare"
    assert "100.000,00 TL / 36 ay" in result.text
    assert "Albaraka Türk" in result.text
    assert "Vakıf Katılım" in result.text
    assert "Ziraat Katılım" in result.text


def test_100k_36m_housing_compare_ranks_correct_verified_lowest_total():
    result = answer_natural("100 bin tl 36 ay vade için konut finansmanlarını kıyasla")
    assert "Albaraka Türk (166.205,69 TL)" in result.text
    assert "en düşük" in result.text
    assert "Ziraat Katılım**" not in result.text.split("**Yorum:**", 1)[-1].split(".", 1)[0]


def test_multi_bank_numeric_followup_keeps_both_banks_and_compare_intent():
    history = []
    first = resolve_followup_question(
        "Konut finansmanında Vakıf mı Türkiye Finans mı daha avantajlı?", history
    )
    history.append(first.resolved_question)
    second = resolve_followup_question("500.000 TL 36 ay", history)
    assert "Vakıf Katılım" in second.resolved_question
    assert "Türkiye Finans" in second.resolved_question
    assert "karşılaştır" in second.resolved_question
    result = ask_bansa(second.resolved_question)
    assert result.route == "finance_compare"
    assert "Vakıf Katılım" in result.text
    assert "Türkiye Finans" in result.text


def test_explicit_global_compare_clears_previous_bank_context():
    history = ["Albaraka Türk konut finansmanı tahsis ücreti ne kadar?"]
    q = "100 bin tl 36 ay vade için konut finansmanlarını kıyasla"
    resolved = resolve_followup_question(q, history)
    assert resolved.resolved_question == q
    assert resolved.used_context is False


def test_global_motorcycle_superlative_clears_previous_bank_context():
    history = ["Albaraka Türk konut finansmanı tahsis ücreti ne kadar?"]
    q = "en uzun vadeli motosiklet finansmanı hangi bankada?"
    resolved = resolve_followup_question(q, history)
    assert resolved.resolved_question == q
    result = ask_bansa(q)
    assert "Kuveyt Türk" in result.text
    assert "Türkiye Finans" in result.text
    assert "Vakıf Katılım" in result.text
