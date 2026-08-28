from src.competition_natural_chat import answer_natural, _extract_purchase_scenario
from src.conversation_state import ConversationState, resolve_followup_question
from src.card_query_service import answer_card_query


def test_vehicle_purchase_scenario_parses_asset_cash_and_monthly_cap():
    q = "900 bin TL'lik araba alacağım, 400 bin TL nakitim var ve aylık 25 bin TL'den fazla ödemek istemiyorum. Bana en uygun seçeneği öner."
    s = _extract_purchase_scenario(q, "tasit_finansmani")
    assert s["asset_value"] == 900000
    assert s["cash"] == 400000
    assert s["financing_need"] == 500000
    assert s["monthly_cap"] == 25000


def test_vehicle_900k_400k_cash_fails_verified_value_band_before_bank_ranking():
    q = "900 bin TL'lik araba alacağım, 400 bin TL nakitim var ve aylık 25 bin TL'den fazla ödemek istemiyorum. Bana en uygun seçeneği öner."
    result = answer_natural(q)
    assert result is not None
    text = result.text
    assert "500.000,00 TL" in text
    assert "270.000,00 TL" in text
    assert "24 ay" in text
    assert "630.000,00 TL" in text
    assert "uygun banka" not in text.casefold() or "önce" in text.casefold()


def test_vehicle_invoice_value_is_not_misread_as_financing_principal():
    q = "500 bin TL araç fatura değeri olan araba alacağım bana finansman öner"
    result = answer_natural(q)
    assert result is not None
    text = result.text
    assert "araç değeri" in text.casefold()
    assert "250.000,00 TL" in text
    assert "36 ay" in text
    assert "nakit" in text.casefold() or "peşinat" in text.casefold()


def test_generic_finance_request_does_not_inherit_previous_housing_family():
    state = ConversationState()
    history = []
    first = resolve_followup_question(
        "500 bin TL birikmişim var, 1 milyon TL'lik ev almak istiyorum. Bana en mantıklı seçeneği öner.",
        history,
        _current_state=state,
    )
    state = first.state
    history.append("500 bin TL birikmişim var, 1 milyon TL'lik ev almak istiyorum. Bana en mantıklı seçeneği öner.")
    second = resolve_followup_question(
        "100 bin TL, 36 ay vadeyle bir finansman istiyorum ama aylık ödemem mümkün olduğunca düşük olsun. Bana en mantıklı seçeneği öner.",
        history,
        _current_state=state,
    )
    assert "konut" not in second.resolved_question.casefold()
    answer = answer_natural(second.resolved_question)
    assert answer is not None
    assert "finansman türünü" in answer.text.casefold()


def test_gree_campaign_followup_stays_on_gree_and_does_not_list_all_campaigns():
    state = ConversationState()
    history = []
    first_q = "gree klima kampanyasında kaç taksit imkanı var"
    first = resolve_followup_question(first_q, history, _current_state=state)
    state = first.state
    first_answer = answer_natural(first.resolved_question)
    assert first_answer is not None
    assert "12 taksit" in first_answer.text
    assert "2026-08-31" in first_answer.text
    history.append(first_q)

    follow = resolve_followup_question("ne zamana kadar geçerli", history, _current_state=state)
    second_answer = answer_natural(follow.resolved_question)
    assert second_answer is not None
    assert "Gree" in second_answer.text
    assert "2026-08-31" in second_answer.text
    assert "434 aktif kampanya" not in second_answer.text


def test_dkart_fee_routes_to_card_catalog_not_campaign():
    result = answer_card_query("dkart debit kart ücreti ne kadar")
    assert result is not None
    assert result.route == "card_product_fact"
    assert "0 TL" in result.text
    assert "Jack & Jones" not in result.text


def test_paraf_platinum_contactless_routes_to_card_catalog_and_is_clean():
    result = answer_natural("paraf platinum kredi kartı temassız özelliği var mı")
    assert result is not None
    assert result.route == "card_product_fact"
    assert "temassız özelliği var" in result.text.casefold()
    assert "2.500 TL" in result.text
    assert "var. Var" not in result.text
    assert "ihtiyaç finansmanı" not in result.text.casefold()


def test_commercial_machine_recommendation_is_product_fit_not_fake_cheapest():
    result = answer_natural("İşletmem için 300 bin TL'lik makine alacağım, 24 ay vadeyle. Bana en uygun ticari finansmanı öner.")
    assert result is not None
    text = result.text
    assert "makine" in text.casefold()
    assert "Kuveyt Türk" in text
    assert "Türkiye Emlak Katılım" in text
    assert "Ziraat Katılım" in text
    assert "sahte bir sıralama yapmıyorum" in text.casefold()
    assert "maliyet" in text.casefold() or "fiyat" in text.casefold()
