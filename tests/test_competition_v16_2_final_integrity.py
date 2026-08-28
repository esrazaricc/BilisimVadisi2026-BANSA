from src.competition_response_service import ask_bansa
from src.chat_followup_context import resolve_followup_question


def turn(q, h):
    r = resolve_followup_question(q, h)
    a = ask_bansa(r.resolved_question).text
    h.append(r.resolved_question)
    return r, a


def test_dunya_600k_vehicle_limit_question_uses_value_band_not_generic_48m():
    a = ask_bansa("Dünya Katılım'da 600 bin TL araç için en fazla ne kadar finansman kullanabilirim ve kaç ay vade olur?").text
    assert '**%50**' in a
    assert '**300.000,00 TL**' in a
    assert '**36 ay**' in a
    assert '**Azami vade: 48 ay.**' not in a


def test_emlak_600k_vehicle_limit_question_uses_value_band_not_generic_48m():
    a = ask_bansa("Türkiye Emlak Katılım'da 600 bin TL araç için en fazla ne kadar finansman ve kaç ay vade var?").text
    assert '**%50**' in a
    assert '**300.000,00 TL**' in a
    assert '**36 ay**' in a
    assert '**Azami vade: 48 ay.**' not in a


def test_financing_amount_wording_is_not_silently_recast_as_vehicle_value():
    a = ask_bansa("Dünya Katılım'dan 600 bin TL araç finansmanı kullanmak istiyorum").text
    # The safe response may discuss the product, but must not assert that 600k
    # itself is the vehicle value and therefore only 300k can be financed.
    assert '600.000,00 TL araç değeri için azami finansman oranı **%50**' not in a


def test_single_verified_bank_is_not_declared_comparison_winner():
    h=[]
    turn('100 bin TL 36 ay araç finansmanlarını karşılaştır', h)
    _, a = turn('En düşük toplam geri ödeme hangisinde?', h)
    assert 'yalnız **bir bankanın**' in a
    assert 'kazanan ilan etmiyorum' in a


def test_single_verified_bank_is_not_declared_monthly_winner():
    h=[]
    turn('100 bin TL 36 ay araç finansmanlarını karşılaştır', h)
    _, a = turn('En düşük aylık taksit hangisinde?', h)
    assert 'yalnız **bir bankanın**' in a
    assert 'kazanan ilan etmiyorum' in a
