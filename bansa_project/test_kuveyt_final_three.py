from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)


def types(items):
    return {item.audience_type for item in items}


def benefit_types(items):
    return {item.benefit_type for item in items}


def test_ticari_musteri_ol_source_adds_new_customer():
    audiences = extract_audiences(
        "Esnaf Kampanyası",
        "Mobil'den müşterimiz olan esnaflar faydalanabilir.",
        source_group=(
            "Kuveyt Türk Ticari Müşteri Ol Kampanyaları"
        ),
        campaign_category="discount_campaign",
    )

    assert "business_customer" in types(audiences)
    assert "new_customer" in types(audiences)


def test_bireysel_musteri_ol_source_adds_new_customer():
    audiences = extract_audiences(
        "Davet Kampanyası",
        (
            "Mobil'den veya Self Noktadan müşteri olan "
            "yakınlarınız için ödül kazanın."
        ),
        source_group=(
            "Kuveyt Türk Bireysel Müşteri Ol Kampanyaları"
        ),
        campaign_category="discount_campaign",
    )

    assert "individual_customer" in types(audiences)
    assert "new_customer" in types(audiences)


def test_atm_limits_are_not_reward():
    benefits = extract_benefits(
        "Kuveyt Türk ve TESK Esnafın Yanında!",
        (
            "Yapı Kredi Bankası ATM’lerinden günlük "
            "10.000 TL’ye kadar ücretsiz para çekme ve "
            "50.000 TL’ye kadar ücretsiz para yatırma "
            "hakkından faydalanabilirsiniz."
        ),
    )

    assert "reward" not in benefit_types(benefits)


def test_real_cash_reward_is_preserved():
    benefits = extract_benefits(
        "Toplamda 5.000 TL Hediye Kazan!",
        (
            "Müşteri olan her yakınınız için 500 TL, "
            "toplamda 5.000 TL'ye kadar hediye kazanın."
        ),
    )

    assert "reward" in benefit_types(benefits)
