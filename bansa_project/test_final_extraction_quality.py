from src.extraction.comparison_field_extractor import (
    detect_finance_type,
    extract_allocation_fee,
    extract_finance_fields,
)


def test_payini_sen_sec_type():
    assert detect_finance_type(
        "Payını Sen Seç Finansmanı",
        "Ödemelerinizi kendi planınıza göre şekillendirin.",
    ) == "Esnek Ödeme Finansmanı"


def test_allocation_fee_sentence():
    amount, rate, status = extract_allocation_fee(
        (
            "Finansman tahsis ücreti, toplam finansman "
            "tutarının %0,5’i oranında tahsil edilecektir."
        )
    )
    assert amount is None
    assert rate == 0.5
    assert status == "Tahsis ücreti oranı belirtilmiş"


def test_zero_profit_display():
    result = extract_finance_fields(
        "Vade Farksız Destek",
        (
            "%0 kâr payı ile 40.000 TL’ye kadar "
            "Pratik Finansman Kart kullanabilirsiniz."
        ),
    )
    assert result.profit_share_rate_text == "%0"
    assert result.financing_amount_text == "40.000 TL'ye kadar"


def test_amount_display_uses_maximum():
    result = extract_finance_fields(
        "Dijital Müşterilere Özel Pratik Finansman Kart",
        (
            "40.000 TL altındaki başvurular ve "
            "150.000 TL'ye kadar finansman imkânı."
        ),
    )
    assert result.financing_amount_text == "150.000 TL'ye kadar"


def test_maturity_display_is_normalized():
    result = extract_finance_fields(
        "Pratik Finansman Kart",
        "6 ay, 12 ay ve 36 ay vade seçenekleri.",
    )
    assert result.maturity_text == "6-36 ay"


def test_advantage_prefers_offer_over_fee():
    result = extract_finance_fields(
        "Taksitlio.com Alışveriş Finansmanı",
        (
            "Avantajlı alışveriş finansmanı fırsatı sunulmaktadır. "
            "Finansman tahsis ücreti, toplam finansman tutarının "
            "%0,5’i oranında tahsil edilecektir."
        ),
    )
    assert result.campaign_advantage is not None
    assert "avantajlı alışveriş finansmanı" in (
        result.campaign_advantage.casefold()
    )
