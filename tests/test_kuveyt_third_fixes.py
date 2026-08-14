import json

from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_finance_fields,
    normalize_text,
)
from src.extraction.finance_extraction_override import (
    apply_finance_override,
)
from src.processing.campaign_classifier import (
    classify_campaign_record,
)
from scripts.audit_kuveyt_nonfinance_extraction import (
    audit_campaign,
)
import sqlite3


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


def test_split_money_text_is_repaired():
    assert "50.000 TL" in normalize_text(
        "5 0.000 TL'ye kadar"
    )


def test_source_metadata_adds_audiences():
    audiences = extract_audiences(
        "Ticari Kart Mil Kampanyası",
        "2.000 Mil kazanın.",
        source_group="Kuveyt Türk Ticari Kart Kampanyaları",
        campaign_category="card_campaign",
    )
    types = {item.audience_type for item in audiences}

    assert "business_customer" in types
    assert "card_holder" in types


def test_new_customer_category_adds_target():
    audiences = extract_audiences(
        "Akademisyenlere Özel Avantaj Paketi",
        "Müşteri olduktan en az 1 gün sonra geçerlidir.",
        source_group=(
            "Kuveyt Türk Bireysel Müşteri Ol Kampanyaları"
        ),
        campaign_category="new_customer_campaign",
    )
    types = {item.audience_type for item in audiences}

    assert "new_customer" in types
    assert "individual_customer" in types


def test_discount_kazan_is_not_reward_audit_error():
    campaign = row(
        {
            "id": 1,
            "title": "3.000 TL'ye Varan İndirim",
            "source_url": "https://example.com/discount",
            "source_group": (
                "Kuveyt Türk Bireysel Kart Kampanyaları"
            ),
            "clean_text": (
                "Toplamda 3.000 TL'ye varan indirim "
                "kazanabilirsiniz."
            ),
            "campaign_category": "discount_campaign",
            "current_status": "active",
        }
    )
    benefit = row(
        {
            "benefit_type": "discount",
            "amount": 3000.0,
            "rate": None,
            "points": None,
            "minimum_spending": 1000.0,
            "maximum_benefit": 3000.0,
            "description": "3.000 TL indirim",
            "evidence": "3.000 TL indirim kazanabilirsiniz.",
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


def test_finance_classifier_recognizes_ihtiyac_card():
    result = classify_campaign_record(
        title=(
            "Yeni Müşterilere Özel İhtiyaç Kart'ta "
            "%1,99 Oran Fırsatı"
        ),
        clean_text=(
            "100.000 TL'ye kadar %1,99 oranla "
            "12 aya varan taksit ve 2 ay erteleme."
        ),
    )
    assert result.campaign_category == "finance_campaign"




def test_hepsiburada_override(tmp_path):
    path = tmp_path / "finance.json"
    path.write_text(
        json.dumps(
            [
                {
                    "bank_name": "Kuveyt Türk",
                    "source_url_contains": "hepsiburada-test",
                    "fields": {
                        "financing_amount_max": 50000.0,
                        "profit_share_rate_text": "%0",
                        "installment_count": 9,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    extraction = extract_finance_fields(
        "Hepsiburada Alışveriş Finansmanı",
        "50.000 TL'ye kadar vade farksız 9 taksit.",
    )
    changed, applied = apply_finance_override(
        extraction,
        bank_name="Kuveyt Türk",
        source_url="https://example.com/hepsiburada-test",
        path=path,
    )

    assert applied is True
    assert changed.financing_amount_max == 50000
    assert changed.profit_share_rate_text == "%0"
    assert changed.installment_count == 9
