from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def test_ala_footer_does_not_force_new_customer():
    result = classify_campaign_record(
        title=(
            "Âlâ Kart ile Sinema ve Tiyatro Biletlerinizi "
            "%50 İndirimli Alın!"
        ),
        clean_text=(
            "Sinema ve tiyatro biletlerinde %50 indirim. "
            "Ortak site alanı: müşterimiz olan kullanıcılar. "
            "Footer bağlantısı: müşterimiz olun."
        ),
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
    )

    assert result.campaign_category == "discount_campaign"


def test_insurance_footer_does_not_force_insurance():
    result = classify_campaign_record(
        title=(
            "Katılım Hesabınızı Şimdi Açın, Daha Yüksek "
            "Getiri Oranlarından Yararlanın!"
        ),
        clean_text=(
            "Katılım hesabı kampanyası avantajları. "
            "Footer bağlantıları: sigorta, kasko ve DASK."
        ),
        source_group=(
            "Türkiye Finans Birikim / Fon Kampanyaları"
        ),
    )

    assert result.campaign_category != "insurance_campaign"


def test_bes_title_is_insurance_campaign():
    result = classify_campaign_record(
        title=(
            "BES ile Hem Yarınınıza Değer Katın, "
            "Hem de 650 TL Bonus Kazanın!"
        ),
        clean_text="Kampanya kapsamında 650 TL bonus sunulur.",
        source_group="Türkiye Finans Sigorta Kampanyaları",
    )

    assert result.campaign_category == "insurance_campaign"


def test_explicit_new_customer_title_is_preserved():
    result = classify_campaign_record(
        title=(
            "Mobil’den Müşteri Olan KOBİ’lerimize "
            "Avantaj Paketi"
        ),
        clean_text="Yeni müşterilere özel avantaj paketi.",
        source_group="Türkiye Finans Ticari Kampanyalar",
    )

    assert result.campaign_category == "new_customer_campaign"


def test_explicit_first_time_customer_body_is_preserved():
    result = classify_campaign_record(
        title="Dijital Avantaj Paketi",
        clean_text=(
            "İlk kez müşteri olanlara özel 500 TL avantaj."
        ),
        source_group=(
            "Türkiye Finans Dijital Bankacılık Kampanyaları"
        ),
    )

    assert result.campaign_category == "new_customer_campaign"
