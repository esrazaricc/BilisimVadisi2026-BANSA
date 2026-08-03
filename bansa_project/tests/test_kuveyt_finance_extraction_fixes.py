import json

from src.extraction.comparison_field_extractor import (
    extract_benefits,
    extract_finance_fields,
)
from src.extraction.finance_extraction_override import (
    apply_finance_override,
)


def test_vade_farksiz_means_zero_rate_and_three_months():
    result = extract_finance_fields(
        "Diyanet Umre Finansmanı",
        (
            "Toplam umre tutarının en fazla yüzde altmışı için "
            "vade farksız 3 taksit imkanı sunulur."
        ),
    )
    assert result.profit_share_rate_text == "%0"
    assert result.maturity_max_months == 3
    assert result.installment_count == 3


def test_grace_and_business_installments():
    result = extract_finance_fields(
        "Sağlam Business Kart",
        (
            "3 ay ertelemeyle harcamalarınızı %3,49 kâr payıyla "
            "toplamda 9 taksite bölebilirsiniz."
        ),
    )
    assert result.finance_type == "Ticari Kart Taksitlendirme"
    assert result.grace_period_months == 3
    assert result.installment_count == 9


def test_taksitlio_campaign_term_beats_example_plan():
    result = extract_finance_fields(
        "Taksitlio Alışveriş Finansmanı",
        (
            "100.000 TL’ye kadar alışveriş ödemelerinizi "
            "6 taksite kadar %2,99 avantajlı kar payı oranı ile "
            "yapabilirsiniz. 3 ay vadeli 10.000 TL başvuru için "
            "örnek ödeme planı."
        ),
    )
    assert result.finance_type == "Alışveriş Finansmanı"
    assert result.financing_amount_max == 100000
    assert result.maturity_max_months == 6
    assert result.installment_count == 6


def test_disclaimer_is_not_selected_as_advantage():
    result = extract_finance_fields(
        "KFK Destekli Yatırım Finansmanı",
        (
            "6 aya kadar ödemesiz dönem ve 60 aya varan vade "
            "imkânı sunulur. Finansman koşulları başvuru "
            "sahibinin değerlendirme sonucuna göre değişebilir."
        ),
    )
    assert "6 aya kadar" in result.campaign_advantage
    assert "değişebilir" not in result.campaign_advantage


def test_free_hgs_is_structured_benefit():
    benefits = extract_benefits(
        "Araç Finansmanı Onaylanan KOBİ’lere HGS Kampanyası",
        (
            "Araç finansmanı onaylanan KOBİ müşterilerine "
            "ücretsiz HGS etiketi avantajı sunulmaktadır."
        ),
    )
    assert any(
        item.benefit_type == "free_service"
        and item.description == "Ücretsiz HGS etiketi"
        for item in benefits
    )


def test_override_only_matches_configured_url_fragment(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            [
                {
                    "bank_name": "Kuveyt Türk",
                    "source_url_contains": "old-campaign",
                    "fields": {
                        "financing_amount_text": "100.000 TL"
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    extraction = extract_finance_fields(
        "Yeni Finansman Kampanyası",
        "24 aya kadar vade sunulur.",
    )

    unchanged, applied = apply_finance_override(
        extraction,
        bank_name="Kuveyt Türk",
        source_url="https://example.com/new-campaign",
        path=path,
    )
    changed, old_applied = apply_finance_override(
        extraction,
        bank_name="Kuveyt Türk",
        source_url="https://example.com/old-campaign",
        path=path,
    )

    assert applied is False
    assert unchanged == extraction
    assert old_applied is True
    assert changed.financing_amount_text == "100.000 TL"
