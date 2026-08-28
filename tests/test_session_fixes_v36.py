"""
Bu oturumda düzeltilen iki bug için regresyon testleri:

1. Banka belirtilip vade belirtilmediğinde (örn. "Ziraat Katılım 500 bin TL
   araba alacağım, finansman öner" -> "aylık ne kadar öderim") hesaplama
   motoru tıkanıp genel bir özet tekrarlıyordu; artık doğrulanmış bir vadeyi
   varsayılan alıp gerçek hesaplama üretiyor.
2. Kampanya bağlamı ("teknosa kampanyası var mı" -> "ne zamana kadar
   geçerli") tamamen kopup alakasız bir kampanyaya düşüyordu; artık doğru
   kampanyaya bağlı kalıyor.

Ayrıca bu oturumdaki düzeltmenin yol açtığı bir güvenlik regresyonu da
(Vakıf Katılım gibi kullanıcı-girişli oranlı bankalarda taksit uydurma)
burada test edilir.
"""

from src.conversation_state import ConversationState, resolve_followup_question
from src.competition_response_service import ask_bansa


def _run(turns):
    state = ConversationState()
    history = []
    answers = []
    for t in turns:
        r = resolve_followup_question(t, history, _current_state=state)
        state = r.state
        answers.append(ask_bansa(r.resolved_question).text)
        history.append(t)
    return answers


def test_bank_then_amount_then_monthly_payment_computes_real_number():
    answers = _run([
        "ziraat katılım 500 bin tl araç fatura değeri olan araba alacağım bana finansman öner",
        "aylık ne kadar öderim",
    ])
    assert "Ziraat Katılım" in answers[0]
    final = answers[1]
    assert "Ziraat Katılım" in final
    assert "kâr payı" in final.casefold()
    assert "aylık taksit" in final.casefold()
    # Gerçek bir sayı üretilmiş olmalı, "belirleniyor" gibi boş bir cevap değil.
    assert "hesaplama aracında belirleniyor" not in final


def test_campaign_context_stays_on_named_merchant():
    answers = _run([
        "teknosa kampanyası var mı",
        "ne zamana kadar geçerli",
    ])
    assert "Teknosa" in answers[0]
    final = answers[1]
    assert "Teknosa" in final
    assert "2026" in final  # gerçek tarih üretilmiş olmalı


def test_campaign_topic_prefix_never_leaks_finance_context():
    """"teknosa kampanyası" -> "hangi tarihe kadar geçerli" zincirinde, eski
    finansman context'i (banka+tutar+vade) kampanya sorusunun önüne
    yanlışlıkla eklenmemelidir.
    """
    answers = _run([
        "500 bin tl araç fatura değeri olan araba alacağım bana finansman öner",
        "zriaat katılım teknosa kampanyası kaç taksit",
        "hangi tarihe kadar geçerli",
    ])
    assert "Teknosa" in answers[1]
    final = answers[2]
    assert "Teknosa" in final
    assert "2026" in final  # gerçek tarih üretilmiş olmalı
    assert "aracın fatura/kasko değerini mi" not in final


def test_ziraat_vehicle_value_bands_produce_real_numbers():
    """Ziraat Katılım'da araç değeri bandı verisi olmalı; "aracın fatura
    değeri X TL" dendiğinde gerçek bir azami finansman oranı/tutarı/vade
    hesaplanmalıdır, boş bir genel özet değil.
    """
    answers = _run([
        "Ziraat Katılım 500 bin tl araç alacağım, finansman öner",
        "aracın fatura değeri 500 bin TL",
    ])
    final = answers[1]
    assert "%50" in final or "azami finansman oranı" in final.casefold()
    assert "250.000" in final or "36 ay" in final


def test_generic_campaign_question_does_not_inherit_stale_bank_and_family():
    """"Şu an aktif kart kampanyaları neler?" gibi genel bir soru, önceki
    turlardaki banka/finansman kategorisini miras almamalıdır.
    """
    answers = _run([
        "Ziraat Katılım ile Kuveyt Türk'ün taşıt finansmanlarını karşılaştır",
        "Konut finansmanında en uzun vadeyi hangi banka veriyor?",
        "Şu an aktif kart kampanyaları neler?",
    ])
    final = answers[2]
    assert "aktif kampanya" in final.casefold()
    assert "eşleşme bulunamadı" not in final


def test_bank_named_campaign_command_does_not_inherit_stale_merchant():
    """"Ziraat Katılım'ın kampanyalarını göster" gibi açık bir komut, önceki
    turdaki farklı bir marka/kampanya konusunu (örn. "a101") miras
    almamalı ve yanlış birleşim oluşturmamalıdır.
    """
    answers = _run([
        "A101 kampanyası var mı?",
        "hangi bankada?",
        "Ziraat Katılım'ın kampanyalarını göster",
    ])
    final = answers[2]
    assert "Ziraat Katılım güncel kampanyalar" in final or "Ziraat Katılım" in final
    assert "a101 kampanyası" not in final.casefold()


def test_bank_affirmation_still_keeps_full_scenario_after_stricter_guard():
    """_looks_like_affirmation_only fonksiyonuna komut fiili kontrolü
    eklenmesi, gerçek onay senaryolarını (örn. "Ziraat Katılım iyi")
    bozmamalıdır.
    """
    answers = _run([
        "100 bin TL 36 ay taşıt finansmanı için en uygun seçenek hangisi?",
        "Ziraat Katılım iyi",
        "vadesi kaç ay olabilir?",
    ])
    assert "48 ay" in answers[2]
    assert "Ziraat Katılım" in answers[2]


def test_vakif_user_controlled_rate_is_never_scaled_into_a_payment():
    """Güvenlik regresyon testi: Vakıf Katılım'ın hesaplama aracındaki oran
    kullanıcı tarafından girilebildiği için, doğrulanmış bir senaryo olsa
    bile bu oran farklı bir tutara ölçeklenip taksit üretilmemelidir.
    """
    text = ask_bansa("100 bin TL 36 ay Vakıf Katılım taşıt finansmanı aylık taksit ne kadar?").text
    assert "uydurmuyorum" in text
    assert "194.286" not in text
    assert "%3,19" not in text
