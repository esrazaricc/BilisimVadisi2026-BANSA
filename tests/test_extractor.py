from src.classification.campaign_detector import classify_page
from src.extraction.rule_extractor import extract_campaign


def test_numeric_date_and_installment_are_extracted():
    title = "Eğitim Harcamalarınıza Vade Farksız 6 Taksit Kampanyası"
    text = """
    Kampanya Başlangıç ve Bitiş
    01.07.2026 - 30.09.2026
    30.000 TL ve üzeri eğitim harcamalarınıza vade farksız 6 taksit fırsatı.
    Kampanyadan bireysel Worldcard sahipleri yararlanabilir.
    """

    classification = classify_page(title, text)
    extraction = extract_campaign(title, text)

    assert classification["page_type"] == "campaign"
    assert extraction["campaign_start_date"] == "2026-07-01"
    assert extraction["campaign_end_date"] == "2026-09-30"
    assert extraction["installment_count"] == 6
    assert extraction["minimum_spending"] == 30000
    assert extraction["expense_status"] == "Vade Farksız"
