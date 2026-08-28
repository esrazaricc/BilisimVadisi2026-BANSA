from datetime import date

from src.processing.campaign_classifier import classify_campaign_record
from src.extraction.comparison_field_extractor import extract_finance_fields
from src.scraping.campaign_status import evaluate_campaign_status


SOURCE = "T.O.M. Katılım / TOM Bank Hadi Kampanyaları"


def test_tom_merchant_credit_is_finance_not_footer_discount():
    title = "TOM Bank Hadi'den Alfemo Kampanyası! | TOM Bank Hadi"
    body = (
        "TOM Bank Hadi'den Alfemo Kampanyası! "
        "31.12.2026'ya kadar Hadi Taksitli Alışveriş Kredisi ile "
        "anlaşmalı Alfemo mağazalarında vade farkı iade avantajı. "
        "1.000 TL – 150.000 TL arasındaki kredi kullandırımları için "
        "geçerlidir. 12 ay vadedeki kredilerde geçerlidir. "
        "İlginizi Çekebilir Hadi Black Kredi Kartı ile Restoderm'de "
        "%30 indirim!"
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.record_kind == "campaign"
    assert result.campaign_category == "finance_campaign"


def test_tom_card_installment_stays_card_campaign():
    title = "TOM Bank Hadi'den Eczane Kampanyası!! | TOM Bank Hadi"
    body = (
        "TOM Bank Hadi'den Eczane Kampanyası!! "
        "Hadi Kredi Kartlarınla 5.000 TL'ye kadar eczane "
        "harcamalarını %0 vade farkı ile 3 aya kadar sonradan "
        "taksitlendir. Kampanya 31 Aralık 2026 tarihine kadar geçerlidir."
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.campaign_category == "card_campaign"


def test_tom_finance_extraction_vade_farki_and_amount_range():
    title = "TOM Bank Hadi'den Alfemo Kampanyası! | TOM Bank Hadi"
    body = (
        "TOM Bank Hadi'den Alfemo Kampanyası! "
        "Hadi Taksitli Alışveriş Kredisi ile vade farkı iade avantajı. "
        "1.000 TL – 150.000 TL arasındaki kredi kullandırımları için "
        "geçerlidir. 12 ay vadedeki kredilerde geçerlidir."
    )
    result = extract_finance_fields(title, body)
    assert result.finance_type == "Alışveriş Finansmanı"
    assert result.financing_amount_min == 1000
    assert result.financing_amount_max == 150000
    assert result.maturity_max_months == 12


def test_tom_health_credit_vade_rate_4_99():
    title = (
        "Hadi Taksitli Sağlık Kredisi sağlık harcamalarında da yanında! "
        "| TOM Bank Hadi"
    )
    body = (
        "Hadi Taksitli Sağlık Kredisi sağlık harcamalarında da yanında! "
        "Eczane harcamalarında 4.99 Vade Farkıyla 3 Taksit, "
        "diğer sağlık sektörü harcamalarında 4.99 Vade Farkıyla "
        "3-6-9-12 Taksit."
    )
    result = extract_finance_fields(title, body)
    assert result.finance_type == "Sağlık Finansmanı"
    assert result.profit_share_rate_min == 4.99
    assert result.profit_share_rate_max == 4.99


def test_tom_partial_named_range_expires():
    result = evaluate_campaign_status(
        text=(
            "Kampanya 1 Temmuz - 31 Temmuz 2026 tarihleri "
            "arasında geçerlidir."
        ),
        reference_date=date(2026, 8, 10),
    )
    assert result.status == "expired"
    assert result.end_date == "2026-07-31"


def test_tom_suffix_kadar_parses_end_date():
    result = evaluate_campaign_status(
        text="31.12.2026'ya kadar kampanya devam eder.",
        reference_date=date(2026, 8, 10),
    )
    assert result.status == "active"
    assert result.end_date == "2026-12-31"
