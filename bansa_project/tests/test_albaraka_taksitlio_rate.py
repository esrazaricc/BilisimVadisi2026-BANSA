from src.extraction.comparison_field_extractor import (
    extract_finance_fields,
)


def test_albaraka_taksitlio_current_rate_is_extracted_as_2_99():
    title = "Taksitlio.com Alışveriş Finansmanı"
    text = (
        "150.000 TL'ye kadar 6 ay vade ile "
        "%2,99 kar oranı ile kullanım sağlayabilirsiniz. "
        "Finansman tahsis ücreti, toplam finansman tutarının "
        "%0,5’i oranında tahsil edilecektir."
    )

    result = extract_finance_fields(title, text)

    assert result.finance_type == "Alışveriş Finansmanı"
    assert result.profit_share_rate_min == 2.99
    assert result.profit_share_rate_max == 2.99
    assert result.profit_share_rate_text == "%2,99"
    assert result.maturity_max_months == 6
    assert result.allocation_fee_rate == 0.5
