from src.processing.campaign_classifier import classify_campaign_record


SOURCE = "T.O.M. Katılım / TOM Bank Hadi Kampanyaları"


def classify(title: str, body: str):
    return classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )


def test_a101_100tl_veresiye_reward_is_discount():
    result = classify(
        "A101'de 100TL kazan (GEÇMİŞ KAMPANYA) | TOM Bank Hadi",
        (
            "Hadi Veresiye ile A101’lerde tek seferlik 500 TL ve üzeri "
            "alışverişinde toplamda 100 TL kazan. "
            "Ödül nakit iade olarak hesaba yüklenir."
        ),
    )
    assert result.campaign_category == "discount_campaign"


def test_veresiye_1000_100_reward_is_discount():
    result = classify(
        (
            "Hadi Veresiye ile 1.000 TL harca 100 TL kazan! "
            "(GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        "Hadi Veresiye harcamasına 100 TL ödül kazan.",
    )
    assert result.campaign_category == "discount_campaign"


def test_veresiye_10000_250_reward_is_discount():
    result = classify(
        (
            "Hadi Veresiye ile toplam 10.000 TL harca ek 250 TL kazan! "
            "(GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        "Toplam 10.000 TL Veresiye harcamasına 250 TL ödül kazan.",
    )
    assert result.campaign_category == "discount_campaign"


def test_vade_farkin_bizden_is_campaign_not_finance():
    result = classify(
        (
            "Hadi Veresiye ile A101'lerde Yapacağın İlk Alışverişe "
            "Vade Farkın Bizden! (GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        (
            "Hadi Veresiye ile ilk alışverişte oluşan vade farkı "
            "kampanya kapsamında iade edilir."
        ),
    )
    assert result.campaign_category == "discount_campaign"


def test_explicit_taksitli_kredi_reward_stays_finance():
    result = classify(
        (
            "Hadi Taksitli Kredi ile 2.500 TL ve üzeri harcamalarında "
            "250 TL nakit iade! (GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        (
            "Hadi Taksitli Kredi kullanılarak yapılan uygun harcamalarda "
            "250 TL nakit iade avantajı."
        ),
    )
    assert result.campaign_category == "finance_campaign"


def test_vade_farksiz_veresiye_offer_stays_finance():
    result = classify(
        (
            "TOM Bank Çok Kazananlar Kulübüne Özel Vade Farksız Veresiye! "
            "| TOM Bank Hadi"
        ),
        "Veresiye alışverişlerinde vade farksız finansman avantajı.",
    )
    assert result.campaign_category == "finance_campaign"
