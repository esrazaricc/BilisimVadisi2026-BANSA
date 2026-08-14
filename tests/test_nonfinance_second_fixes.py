import sqlite3

from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)
from scripts.audit_kuveyt_nonfinance_extraction import (
    audit_campaign,
    detect_signals,
)


def benefit_types(items):
    return {item.benefit_type for item in items}


def row(values):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    columns = ", ".join(
        f'? AS "{key}"'
        for key in values
    )
    return connection.execute(
        f"SELECT {columns}",
        tuple(values.values()),
    ).fetchone()


def test_fixed_amount_discount_is_not_reward():
    benefits = extract_benefits(
        "Adore Mobilya'da 4.000 TL İndirim",
        (
            "20.000 TL ve üzeri taksitli alışverişlerde "
            "4.000 TL indirim kazanılır."
        ),
    )

    assert "discount" in benefit_types(benefits)
    assert "reward" not in benefit_types(benefits)

    discount = next(
        item
        for item in benefits
        if item.benefit_type == "discount"
    )
    assert discount.amount == 4000


def test_percent_to_discount_and_cashback_rate():
    benefits = extract_benefits(
        "KOBİ Avantajları",
        (
            "Kargo gönderilerinde %75'e varan indirim sunulur. "
            "İlk işleme özel %1 nakit iade kazanılır."
        ),
    )

    discounts = [
        item
        for item in benefits
        if item.benefit_type == "discount"
    ]
    cashback = next(
        item
        for item in benefits
        if item.benefit_type == "cashback"
    )

    assert any(item.rate == 75 for item in discounts)
    assert cashback.rate == 1
    assert "reward" not in benefit_types(benefits)


def test_package_value_is_reward_and_free_service():
    benefits = extract_benefits(
        "16.000 TL Değerinde Finansal Ürün Paketi Hediye",
        (
            "16.000 TL değerindeki finansal ürün paketimizden "
            "ücretsiz faydalanın."
        ),
    )

    assert "reward" in benefit_types(benefits)
    assert "free_service" in benefit_types(benefits)
    reward = next(
        item
        for item in benefits
        if item.benefit_type == "reward"
    )
    assert reward.amount == 16000


def test_qualitative_altin_puan_is_extracted():
    benefits = extract_benefits(
        "Yurt Dışı Çıkış Harcı Hediye",
        (
            "Harç tutarının tamamı altın puan olarak "
            "iade verilecektir."
        ),
    )

    assert "shopping_points" in benefit_types(benefits)


def test_new_customer_and_card_audiences():
    audiences = extract_audiences(
        "Fatura Talimatlarınıza Hediye",
        (
            "Kuveyt Türk Mobil'den müşterimiz olanlar ve "
            "bireysel kredi kartı olan müşteriler faydalanabilir."
        ),
    )
    types = {
        item.audience_type
        for item in audiences
    }

    assert "new_customer" in types
    assert "digital_customer" in types
    assert "individual_customer" in types
    assert "card_holder" in types


def test_hgs_is_not_discount_signal():
    signals = detect_signals(
        (
            "Araç finansmanı onaylanan KOBİ müşterilerine "
            "ücretsiz HGS etiketi avantajı sunulur."
        )
    )

    assert "free_service" in signals
    assert "discount" not in signals


def test_miles_gift_does_not_require_separate_reward():
    campaign = row(
        {
            "id": 1,
            "title": "10.000 Mil Avantajı",
            "source_url": "https://example.com/miles",
            "source_group": "Bireysel Kart Kampanyaları",
            "clean_text": (
                "İlk 1.000 TL ve üzeri harcamada "
                "10.000 Mil'e varan hediye kazanabilirsiniz."
            ),
            "campaign_category": "points_campaign",
            "current_status": "active",
        }
    )
    benefit = row(
        {
            "benefit_type": "miles",
            "amount": None,
            "rate": None,
            "points": 10000,
            "minimum_spending": 1000,
            "maximum_benefit": None,
            "description": "10.000 Mil'e kadar",
            "evidence": "10.000 Mil hediye.",
        }
    )
    audience = row(
        {
            "audience_type": "card_holder",
            "audience_label": "Kart Sahipleri",
            "details": None,
        }
    )

    result = audit_campaign(
        campaign,
        benefits=[benefit],
        audiences=[audience],
    )

    assert not any(
        "reward" in reason
        for reason in result["high_reasons"]
    )


def test_bireysel_card_source_only_requires_card_holder():
    campaign = row(
        {
            "id": 2,
            "title": "Vade Farksız 5 Taksit",
            "source_url": "https://example.com/installment",
            "source_group": "Kuveyt Türk Bireysel Kart Kampanyaları",
            "clean_text": (
                "Kuveyt Türk kredi kartları ile "
                "5 aya varan taksit imkanı."
            ),
            "campaign_category": "card_campaign",
            "current_status": "active",
        }
    )
    benefit = row(
        {
            "benefit_type": "installment",
            "amount": None,
            "rate": None,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "5 taksit",
            "evidence": "5 aya varan taksit imkanı.",
        }
    )
    audience = row(
        {
            "audience_type": "card_holder",
            "audience_label": "Kart Sahipleri",
            "details": None,
        }
    )

    result = audit_campaign(
        campaign,
        benefits=[benefit],
        audiences=[audience],
    )

    assert result["severity"] == "ok"
