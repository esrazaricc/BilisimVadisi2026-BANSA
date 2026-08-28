from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa


def turn(q, h):
    r = resolve_followup_question(q, h)
    a = ask_bansa(r.resolved_question).text
    h.append(r.resolved_question)
    return r, a


def test_dunya_motorcycle_never_inherits_generic_vehicle_ratio():
    h=[]
    turn('Dünya Katılım motosiklet finansmanı var mı?', h)
    _, a=turn('600 bin TL motosiklet için ne kadar verir?', h)
    assert 'otomatik uygulamıyorum' in a
    assert '%50' not in a
    assert '300.000,00 TL' not in a


def test_vakif_calculator_rate_is_not_treated_as_bank_published_rate():
    a=ask_bansa('Vakıf Katılım taşıt finansmanı 36 ay oranı ne?').text
    assert '%3,40' not in a
    assert '%3,19' not in a
    assert 'kullanıcı tarafından belirlenebildiği' in a


def test_emlak_vehicle_band_is_eligibility_not_payment_price():
    h=[]
    _,a=turn('Türkiye Emlak Katılım taşıt finansmanı nasıl?', h)
    _,a=turn('600 bin TL araç değeri için kaç ay?', h)
    assert '%50' in a and '36 ay' in a
    _,a2=turn('100 bin TL 36 ay aylık taksit ne kadar?', h)
    assert 'uydurmuyorum' in a2


def test_campaign_hard_boundary_survives_previous_motorcycle_context():
    h=[]
    turn('Dünya Katılım motosiklet finansmanı var mı?', h)
    turn('600 bin TL motosiklet için ne kadar verir?', h)
    r,a=turn('Ziraat Katılım Teknosa kampanyasında kaç taksit var?', h)
    assert r.resolved_question == 'Ziraat Katılım Teknosa kampanyasında kaç taksit var?'
    assert 'Teknosa' in a and '**3 taksit**' in a
    _,a2=turn('Ne zamana kadar geçerli?',h)
    assert '2026-08-31' in a2 and 'Teknosa' in a2


def test_vatan_title_number_beats_related_card_number():
    a=ask_bansa('Ziraat Katılım Vatan kampanyasında kaç taksit var?').text
    assert '**3 taksit**' in a
    assert '**5 taksit**' not in a


def test_old_dynamic_snapshots_do_not_decide_current_winner():
    a=ask_bansa('100 bin TL 36 ay araç finansmanlarını karşılaştır').text
    assert 'Vakıf Katılım · 194.286,46 TL' not in a
    assert '%3,19' not in a
