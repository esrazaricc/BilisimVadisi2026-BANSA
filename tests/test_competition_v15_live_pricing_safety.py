from src.chat_followup_context import resolve_followup_question
from src.competition_natural_chat import answer_natural


def _text(q: str) -> str:
    out = answer_natural(q)
    assert out is not None
    return out.text


def _conversation(questions):
    history=[]
    outputs=[]
    resolutions=[]
    for q in questions:
        r=resolve_followup_question(q, history)
        resolutions.append(r.resolved_question)
        out=answer_natural(r.resolved_question)
        assert out is not None
        outputs.append(out.text)
        history.append(r.resolved_question)
    return resolutions, outputs


def test_dunya_vehicle_table_is_eligibility_not_payment_pricing():
    text=_text("Dünya Katılım araç finansmanı nasıl?")
    assert "Araç değerine göre azami finansman/vade sınırları" in text
    assert "hesaplama aracında" in text.casefold()


def test_dunya_generic_vehicle_rules_are_not_transplanted_to_motorcycle():
    resolutions, outputs=_conversation([
        "Dünya Katılım motosiklet finansmanı var mı?",
        "600 bin TL motosiklet için ne kadar verir?",
    ])
    assert "motosiklet finansmanı" in outputs[-1].casefold() and "ürünü/kapsamı bulamadım" in outputs[-1].casefold()
    assert "300.000,00 TL" not in outputs[-1]
    assert "%50" not in outputs[-1]


def test_dunya_exact_two_million_boundary_fails_closed():
    text=_text("Dünya Katılım 2 milyon TL araç değeri için en fazla kaç ay?")
    assert "iki satırı" in text.casefold() or "çakış" in text.casefold()
    assert "komşu banttan tahmin" in text


def test_vakif_calculator_rate_is_not_promoted_to_current_bank_rate():
    text=_text("Vakıf Katılım taşıt finansmanı nasıl?")
    assert "48 ay" in text
    assert "60 ay" not in text
    assert "kullanıcı tarafından belirlenebildiği" in text
    scenario=_text("Vakıf Katılım taşıt finansmanı 100000 TL 36 ay aylık taksiti ve toplam geri ödemeyi hesapla")
    assert "%3,40" not in scenario and "%3.40" not in scenario
    assert "%3,19" not in scenario
    assert "uydurmuyorum" in scenario
    assert "194.286,46" not in scenario


def test_vehicle_compare_does_not_rank_vakif_calculator_rate_or_stale_snapshot():
    text=_text("100 bin TL 36 ay araç finansmanlarını karşılaştır")
    assert "%3,40" not in text and "%3.40" not in text
    assert "%3,19" not in text
    assert "%3.48" in text or "%3,48" in text
    assert "194.286,46" not in text
    assert "kullanıcı tarafından belirlenebildiği" in text


def test_comparison_ranking_followup_fails_closed_without_fresh_exact_set():
    resolutions, outputs=_conversation([
        "100 bin TL 36 ay araç finansmanlarını karşılaştır",
        "En düşük geri ödeme hangisinde?",
        "İkinci en düşük hangisi?",
        "İlk üçü sırala",
    ])
    for text in outputs[1:]:
        assert "güncel sıralama" in text.casefold()
        assert "güvenilir olmaz" in text.casefold()
        assert "194.286,46" not in text


def test_campaign_explicit_question_resets_previous_finance_context():
    resolutions, outputs=_conversation([
        "Vakıf Katılım motosiklet finansmanı nasıl?",
        "600 bin için?",
        "Ziraat Katılım Teknosa kampanyasında kaç taksit var?",
        "Ne zamana kadar geçerli?",
        "Şartı ne?",
    ])
    assert resolutions[2] == "Ziraat Katılım Teknosa kampanyasında kaç taksit var?"
    assert "Teknosa'da 3 Taksit" in outputs[2]
    assert "2026-08-31" in outputs[3]
    assert "Bankkart" in outputs[4]


def test_campaign_title_installment_count_beats_contaminated_neighbor_number():
    text=_text("Ziraat Katılım Vatan kampanyasında kaç taksit var?")
    assert "Vatan’da 3 Taksit" in text
    assert "**3 taksit**" in text
    assert "5 taksit" not in text


def test_campaign_merchant_switch_preserves_only_bank():
    resolutions, outputs=_conversation([
        "Ziraat Katılım MediaMarkt kampanyasında kaç taksit var?",
        "Peki Vatan Bilgisayar kampanyası var mı?",
    ])
    assert resolutions[-1].startswith("Ziraat Katılım -")
    assert "Ziraat Katılım · Vatan" in outputs[-1]
    assert "Kuveyt Türk" not in outputs[-1]


def test_vakif_motorcycle_max_financing_followup_keeps_asset_value():
    resolutions, outputs=_conversation([
        "Vakıf motosiklet finansmanı nasıl?",
        "600 bin için?",
        "24 ay olur mu?",
        "En fazla ne kadar finansman kullanabilirim?",
    ])
    assert "600000 TL motosiklet değeri" in resolutions[-1]
    assert "300.000,00 TL" in outputs[-1]


def test_albaraka_motorcycle_cc_scope_is_preserved_in_followup():
    resolutions, outputs=_conversation([
        "Albaraka Türk motosiklet finansmanı nasıl?",
        "150 cc motosiklet için?",
        "100 cc motosiklet için?",
    ])
    assert "150 cc" in resolutions[1]
    assert "125 cc ve üzeri" in outputs[1]
    assert "100 cc" in resolutions[2]
    assert "ihtiyaç finansmanı" in outputs[2].casefold()


def test_tf_current_rate_can_be_shown_without_inventing_monthly_payment():
    resolutions, outputs=_conversation([
        "Türkiye Finans'ta sigortalı taşıt finansmanı kar payı ne?",
        "36 ay",
        "100 bin TL için aylık taksit ne olur?",
    ])
    assert "%3.48" in outputs[-1] or "%3,48" in outputs[-1]
    assert "genel annüite" in outputs[-1].casefold()
    assert "4.914,26" not in outputs[-1]
