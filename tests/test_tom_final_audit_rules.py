from datetime import date

from src.processing.campaign_classifier import classify_campaign_record
from src.scraping.campaign_status import evaluate_campaign_status


SOURCE = "T.O.M. Katılım / TOM Bank Hadi Kampanyaları"


def classify(title: str, body: str):
    return classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )


def test_numeric_date_range_06_aug_to_31_aug():
    result = evaluate_campaign_status(
        text=(
            "Kampanya 06/08/2026 - 31/08/2026 "
            "tarihleri arasında geçerlidir."
        ),
        reference_date=date(2026, 8, 10),
    )
    assert result.start_date == "2026-08-06"
    assert result.end_date == "2026-08-31"
    assert result.status == "active"


def test_credit_card_later_installment_is_card_campaign():
    result = classify(
        "Hadi Kredi Kartı ile sonradan taksitlendir! | TOM Bank Hadi",
        (
            "Hadi Kredi Kartı'n ile eğitim, sağlık ve sigorta "
            "harcamalarını 12 aya kadar sonradan taksitlendirebilirsin."
        ),
    )
    assert result.campaign_category == "card_campaign"


def test_mtv_credit_card_installment_is_card_campaign():
    result = classify(
        (
            "Hadi Black Kredi Kartı ile MTV Ödemelerinde "
            "Vade Farksız 3 taksit fırsatını kaçırma! | TOM Bank Hadi"
        ),
        (
            "Hadi Black Kredi Kartı ile vergi ödemelerinde "
            "vade farksız 3 taksit."
        ),
    )
    assert result.campaign_category == "card_campaign"


def test_veresiye_cash_reward_is_not_finance():
    result = classify(
        (
            "Hadi Veresiye ile 1.000 TL harca 100 TL kazan! "
            "(GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        (
            "Hadi Veresiye ile 1.000 TL harca 100 TL kazan. "
            "Kampanya ödülü hesaba yüklenir."
        ),
    )
    assert result.campaign_category != "finance_campaign"


def test_veresiye_large_reward_is_not_finance():
    result = classify(
        (
            "Hadi Veresiye ile toplam 10.000 TL harca ek 250 TL kazan! "
            "(GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        "Hadi Veresiye harcamalarında 250 TL ödül kazan.",
    )
    assert result.campaign_category != "finance_campaign"


def test_real_taksitli_alisveris_credit_stays_finance():
    result = classify(
        (
            "Hadi Taksitli Alışveriş Kredisi ile Mondi "
            "Mağazalarında 36 Aya Varan Taksit! | TOM Bank Hadi"
        ),
        (
            "Hadi Taksitli Alışveriş Kredisi ile anlaşmalı Mondi "
            "mağazalarında 36 aya varan taksit fırsatı."
        ),
    )
    assert result.campaign_category == "finance_campaign"


def test_vade_farksiz_veresiye_offer_can_stay_finance():
    result = classify(
        (
            "TOM Bank Çok Kazananlar Kulübüne Özel "
            "Vade Farksız Veresiye! | TOM Bank Hadi"
        ),
        "Veresiye alışverişlerinde vade farksız finansman avantajı.",
    )
    assert result.campaign_category == "finance_campaign"


def test_veresiye_vade_farki_refund_is_campaign_not_finance():
    result = classify(
        (
            "Hadi Veresiye ile A101'lerde Yapacağın İlk Alışverişe "
            "Vade Farkın Bizden! (GEÇMİŞ KAMPANYA) | TOM Bank Hadi"
        ),
        (
            "Hadi Veresiye ile yapılan harcamalarda vade farkı "
            "ödendikten sonra iade edilir."
        ),
    )
    assert result.campaign_category != "finance_campaign"
