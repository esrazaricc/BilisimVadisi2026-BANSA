from src.finance_rule_engine import build_finance_rules
from src.extraction.standard_product_extractor import (
    extract_standard_product,
)


def test_global_18_month_summary_does_not_become_36():
    text = """
    Finansmanın maksimum vadesi 18 aydır.
    Finansman tutarının 125.000 TL’ye kadar olması
    durumunda en fazla 36 ay,
    125.000-250.000 TL arasında en fazla 24 ay,
    250.000 TL’den fazla olması durumunda
    en fazla 12 ay olarak belirlenmiştir.
    """

    result = extract_standard_product(
        f"<html><body>{text}</body></html>"
    )

    assert result.maximum_maturity_months == 18


def test_bilgisayar_does_not_inherit_global_18_month():
    text = """
    Bilgisayar alımları 12, tablet alımları 6 taksit
    ile sınırlandırılmıştır Finansmanın maksimum vadesi
    18 aydır.
    """

    rules = build_finance_rules(
        html=f"<html><body>{text}</body></html>",
        clean_text=text,
    )

    computer = [
        row
        for row in rules["category_rules"]
        if row["category_label"] == "Bilgisayar"
    ]

    assert not any(
        row["max_maturity_months"] == 18
        for row in computer
    )


def test_real_tablet_month_rule_is_preserved():
    text = """
    Tablet alışverişleriniz en fazla 6 ay
    vadelendirilmektedir.
    """

    rules = build_finance_rules(
        html=f"<html><body>{text}</body></html>",
        clean_text=text,
    )

    tablet = [
        row
        for row in rules["category_rules"]
        if row["category_label"] == "Tablet"
    ]

    assert any(
        row["max_maturity_months"] == 6
        for row in tablet
    )


def test_monthly_total_header_is_parsed():
    html = """
    <table>
      <tr>
        <th>Vade</th>
        <th>Oran</th>
        <th>Tahsis Ücreti</th>
        <th>Aylık Toplam</th>
        <th>Yıllık Toplam Maliyet</th>
      </tr>
      <tr>
        <td>6</td>
        <td>%4.25</td>
        <td>%0</td>
        <td>%5.53</td>
        <td>%90.66</td>
      </tr>
    </table>
    """

    rules = build_finance_rules(
        html=html,
        clean_text="",
    )

    assert len(rules["pricing_tiers"]) == 1
    row = rules["pricing_tiers"][0]

    assert row["monthly_total_cost_rate"] == 5.53
    assert row["annual_total_cost_rate"] == 90.66
