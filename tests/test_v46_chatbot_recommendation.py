import pandas as pd

from src.competition_natural_chat import _scenario_recommendation_block


def _row(bank):
    return pd.Series({"bank_name": bank, "product_name": "Konut Finansmanı"})


def _rec(bank, rate, monthly, total, mode="live_calculator"):
    return {
        "bank_name": bank,
        "variant": "standard",
        "rate": rate,
        "monthly": monthly,
        "total": total,
        "freshness_mode": mode,
    }


def test_recommendation_surfaces_metric_winners_for_user_wording():
    exact = [
        (_row("Albaraka Türk"), [_rec("Albaraka Türk", 2.90, 14999.16, 1799897.14)]),
        (_row("Türkiye Emlak Katılım"), [_rec("Türkiye Emlak Katılım", 3.39, 17266.06, 2071926.71)]),
        (_row("Vakıf Katılım"), [_rec("Vakıf Katılım", 2.99, 15398.83, 1847859.46)]),
    ]
    # Exact-labelled rows can also represent a verified non-live scenario.
    exact += [
        (_row("Kuveyt Türk"), [_rec("Kuveyt Türk", 2.99, 15398.82, 1847868.29, "current_official_table")]),
        (_row("Türkiye Finans"), [_rec("Türkiye Finans", 2.88, 14893.49, 1787218.80, "current_official_table")]),
    ]

    lines = _scenario_recommendation_block(
        "500 bin TL birikmişim var, 1 milyon TL'lik ev almak istiyorum. Bana en mantıklı seçeneği öner.",
        exact,
        [],
        500000,
        120,
    )
    text = "\n".join(lines)

    assert "### BANSA önerisi" in text
    assert "En düşük kâr payı" in text
    assert "En düşük aylık taksit" in text
    assert "En düşük toplam geri ödeme" in text
    assert "Türkiye Finans" in text
    assert "%2,88" in text
    assert "14.893,49 TL" in text
    assert "1.787.218,80 TL" in text
    assert "ilk tercihim" in text


def test_options_only_query_does_not_force_recommendation():
    exact = [
        (_row("Albaraka Türk"), [_rec("Albaraka Türk", 2.90, 14999.16, 1799897.14)]),
        (_row("Türkiye Finans"), [_rec("Türkiye Finans", 2.88, 14893.49, 1787218.80)]),
    ]
    lines = _scenario_recommendation_block(
        "500 bin TL konut finansmanı için seçenekleri göster",
        exact,
        [],
        500000,
        120,
    )
    assert lines == []
