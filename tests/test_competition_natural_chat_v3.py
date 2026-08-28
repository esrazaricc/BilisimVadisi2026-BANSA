from src.competition_natural_chat import answer_natural
from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa


def test_needs_options_answer_is_scenario_aware_not_campaign_dump():
    result = answer_natural("75.000 TL 24 ay ihtiyaç finansmanı için hangi seçenekler var?")
    assert result is not None
    assert result.route == "finance_options"
    assert "75.000,00 TL" in result.text
    assert "24 ay" in result.text
    assert "Türkiye Finans" in result.text
    assert "5.576,28 TL" in result.text
    assert "Monster" not in result.text
    assert "Tablet Finansmanı" not in result.text


def test_vakif_motorcycle_info_is_conversational_and_rule_aware():
    result = answer_natural("Vakıf Katılım motosiklet finansmanı hakkında bilgi ver.")
    assert result is not None
    assert result.route == "finance_product_conversation"
    assert "sıfır motosikletler" in result.text
    assert "%70" in result.text
    assert "%50" in result.text
    assert "48 ay" in result.text
    assert "36 ay" in result.text
    assert "hesaplama aracı" in result.text


def test_vakif_600k_explains_invoice_value_rule_instead_of_guessing_installment():
    result = answer_natural("Vakıf Katılım'dan 600.000 TL motosiklet finansmanı 24 ay kullanabilir miyim?")
    assert result is not None
    assert "fatura/kasko değerine" in result.text
    assert "%50" in result.text
    assert "300.000,00 TL" in result.text
    assert "36 ay" in result.text
    assert "24 ay vade" in result.text


def test_named_two_bank_winner_question_asks_for_scenario():
    result = answer_natural("Konut finansmanında Vakıf Katılım mı Türkiye Finans mı daha avantajlı?")
    assert result is not None
    assert result.route == "finance_compare_clarify"
    assert "tutar ve vade" in result.text
    assert "Vakıf Katılım" in result.text
    assert "Türkiye Finans" in result.text
    assert "UNVERIFIED" not in result.text


def test_explicit_new_banks_override_old_compare_context():
    history = [
        "Konut finansmanında Vakıf Katılım mı Türkiye Finans mı daha avantajlı?",
        "Vakıf Katılım Türkiye Finans konut finansmanı 500000 TL 36 ay",
    ]
    q = "Albaraka Türk ve Dünya Katılım için 200.000 TL 36 ay konut finansmanını karşılaştır."
    resolved = resolve_followup_question(q, history)
    assert not resolved.used_context
    assert resolved.resolved_question == q
    result = ask_bansa(resolved.resolved_question)
    assert "Albaraka Türk" in result.text
    assert "Dünya Katılım" in result.text
    assert "Türkiye Finans" not in result.text
    assert "Vakıf Katılım" not in result.text


def test_typo_explicit_motorcycle_query_is_not_contaminated_by_old_context():
    history = ["Albaraka Türk konut finansmanında tahsis ücreti ne kadar?"]
    q = "vakf katlm motosklet finansmani maksimum kac ay vade"
    resolved = resolve_followup_question(q, history)
    assert not resolved.used_context
    result = ask_bansa(resolved.resolved_question)
    assert "Vakıf Katılım" in result.text
    assert "48 ay" in result.text
    assert "Albaraka Türk" not in result.text


def test_numeric_followup_chain_keeps_motorcycle_amount():
    history = []
    first = resolve_followup_question("Vakıf Katılım motosiklet finansmanı hakkında bilgi ver.", history)
    history.append(first.resolved_question)
    second = resolve_followup_question("Peki 600 bin TL için?", history)
    history.append(second.resolved_question)
    third = resolve_followup_question("24 ay olur mu?", history)
    assert "Vakıf Katılım" in third.resolved_question
    assert "motosiklet" in third.resolved_question.casefold()
    assert "600000 TL" in third.resolved_question
    assert "24 ay" in third.resolved_question
    result = ask_bansa(third.resolved_question)
    assert "%50" in result.text
    assert "300.000,00 TL" in result.text
    assert "24 ay vade" in result.text


def test_plain_current_kuveyt_campaign_request_lists_campaigns():
    result = answer_natural("Kuveyt Türk güncel kampanyalarını ver.")
    assert result is not None
    assert result.route == "campaign_search"
    assert "aktif kampanya" in result.text
    assert "Gree" in result.text
    assert "Finansman Kataloğu" not in result.text


def test_campaign_typo_albaraka_routes_to_campaigns_not_finance_rag():
    result = answer_natural("albaraka kampnya avantajlari neler")
    assert result is not None
    assert result.route == "campaign_search"
    assert "Albaraka Türk" in result.text
    assert "aktif kampanya" in result.text
    assert "Bayide Finansman" not in result.text


def test_gree_without_campaign_word_is_natural_campaign_detail():
    result = answer_natural("gree klimada kac taksit imkanı var")
    assert result is not None
    assert result.route == "campaign_detail"
    assert "12 taksit" in result.text
    assert "Gree" in result.text
    assert "Finansman Kataloğu" not in result.text


def test_shipentegra_returns_only_relevant_campaign_detail():
    result = answer_natural("Kuveyt Türk E-İhracatçılara Özel ShipEntegra kampanyasının avantajları nedir?")
    assert result is not None
    assert result.route == "campaign_detail"
    assert "ShipEntegra" in result.text
    assert "3 taksit" in result.text
    assert "Monster Notebook" not in result.text


def test_longest_motorcycle_maturity_compares_all_matching_banks():
    result = answer_natural("en uzun vadeli motosiklet finansmanı hangi bankada?")
    assert result is not None
    assert result.route == "finance_superlative"
    assert "48 ay" in result.text
    assert "Kuveyt Türk" in result.text
    assert "Türkiye Finans" in result.text
    assert "Vakıf Katılım" in result.text


def test_tf_exact_calculation_is_conversational():
    result = answer_natural("Türkiye Finans 75.000 TL 24 ay ihtiyaç finansmanı hesapla.")
    assert result is not None
    assert result.route == "finance_calculate"
    assert "%4,05" in result.text
    assert "5.576,28 TL" in result.text
    assert "%5,95" in result.text
    assert "6.966,60 TL" in result.text
    assert "hesaplama sonuçları" in result.text


def test_response_service_prefers_natural_layer_without_qwen():
    result = ask_bansa("Vakıf Katılım motosiklet finansmanı hakkında bilgi ver.")
    assert result.qwen_used is False
    assert "Tutar yükseldikçe" in result.text
    assert "48 ay" in result.text
