from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa


def turn(q, h):
    r = resolve_followup_question(q, h)
    a = ask_bansa(r.resolved_question).text
    h.append(r.resolved_question)
    return r, a


def test_vakif_maximum_amount_followup_keeps_motorcycle_asset_value():
    h=[]
    turn('Vakıf Katılım motosiklet finansmanı nasıl?', h)
    turn('600 bin için?', h)
    r,a=turn('En fazla ne kadar finansman kullanabilirim?', h)
    assert '600000 TL motosiklet değeri' in r.resolved_question
    assert '**%50**' in a
    assert '**300.000,00 TL**' in a
    assert '**36 ay**' in a
    assert 'sayısal limit yayımlanmamış' not in a


def test_comparison_followups_rebase_to_original_scenario_not_previous_intent():
    h=[]
    turn('100 bin TL 36 ay araç finansmanlarını karşılaştır', h)
    r1,a1=turn('İkinci en düşük hangisi?', h)
    assert 'ikinci sıra' in a1.casefold() or 'ikinci en düşük' in a1.casefold()
    r2,a2=turn('İlk üçü sırala', h)
    assert r2.resolved_question.endswith(' - İlk üçü sırala')
    assert 'İkinci en düşük hangisi?' not in r2.resolved_question
    assert 'ikinci sıra' not in a2.casefold()
    assert 'güncel doğrulanmış sıralama' in a2


def test_pairwise_difference_does_not_inherit_previous_rank_intent():
    h=[]
    turn('100 bin TL 36 ay araç finansmanlarını karşılaştır', h)
    turn('İkinci en düşük hangisi?', h)
    r,a=turn('Türkiye Finans ile Vakıf Katılım arasındaki fark ne kadar?', h)
    assert 'İkinci en düşük hangisi?' not in r.resolved_question
    # Vakıf currently has no fresh numeric monthly/total result in this runtime,
    # so a safe abstention is allowed; the crucial regression is that the old
    # second-place response must not leak into this new intent.
    assert 'ikinci sıra' not in a.casefold()


def test_explicit_education_financing_advantages_do_not_route_to_campaign():
    a=ask_bansa('Albaraka Türk eğitim finansmanının avantajları?').text
    assert 'Eğitim Finansmanı' in a
    assert 'Vade Farksız 6 Taksit Kampanyası' not in a


def test_top3_and_pairwise_difference_are_concise_when_fresh_numeric_coverage_is_partial():
    h=[]
    turn('100 bin TL 36 ay araç finansmanlarını karşılaştır', h)
    _,a1=turn('İlk üçü sırala', h)
    assert 'güncel doğrulanmış sıralama' in a1
    assert 'eski snapshot' in a1
    _,a2=turn('Türkiye Finans ile Vakıf Katılım arasındaki fark ne kadar?', h)
    assert 'güvenilir biçimde hesaplayabilmek' in a2
    assert 'Eski snapshot kullanarak fark üretmiyorum' in a2
    assert 'Taşıt finansmanı karşılaştırması' not in a2
