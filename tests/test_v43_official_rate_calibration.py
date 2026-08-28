from decimal import Decimal

from src.finance_runtime_repository import get_standard_products
from src.finance_scenario_projection import project_row


def _rec(product_id: int, amount: int, maturity: int):
    frame = get_standard_products()
    row = frame[frame["id"].eq(product_id)].iloc[0]
    records = project_row(row, amount, maturity)
    assert records, f"no projection for product {product_id}"
    assert len(records) == 1
    rec = records[0]
    assert rec.mode == "official_calculator_snapshot_model"
    assert rec.source_kind == "official_calculator_snapshot"
    return rec


def test_v43_housing_official_calculator_snapshots_match_user_screens():
    cases = [
        # product_id, amount, maturity, rate, monthly, total
        (97, 500_000, 20, "3.04", "33765.42", "675308.89"),
        (33, 500_000, 120, "2.9900", "15398.82", "1847868.29"),
        (67, 500_000, 120, "2.88", "14893.49", "1787218.80"),
        (296, 100_000, 60, "2.99", "3605.56", "216333.48"),
    ]
    for product_id, amount, maturity, rate, monthly, total in cases:
        rec = _rec(product_id, amount, maturity)
        assert rec.profit_share_rate == Decimal(rate)
        assert rec.monthly_installment == Decimal(monthly)
        assert rec.installment_total == Decimal(total)


def test_v43_vehicle_official_calculator_snapshots_match_user_screens():
    cases = [
        (87, 267_500, 12, "3.55", "29572.47", "356407.19"),
        (23, 500_000, 48, "3.3900", "25216.76", "1210404.67"),
        (61, 100_000, 48, "3.42", "5074.96", "243598.08"),
        (286, 100_000, 24, "3.29", "6746.01", "161904.12"),
    ]
    for product_id, amount, maturity, rate, monthly, total in cases:
        rec = _rec(product_id, amount, maturity)
        assert rec.profit_share_rate == Decimal(rate)
        assert rec.monthly_installment == Decimal(monthly)
        assert rec.installment_total == Decimal(total)


def test_v43_need_official_calculator_snapshots_match_user_screens():
    cases = [
        (121, 150_000, 23, "4.00", "11349.76", "261044.84"),
        (70, 100_000, 36, "3.80", "5996.94", "215889.84"),
        (48, 500_000, 12, "4.0100", "57092.42", "685108.95"),
        (318, 100_000, 18, "3.99", "8680.05", "156240.94"),
    ]
    for product_id, amount, maturity, rate, monthly, total in cases:
        rec = _rec(product_id, amount, maturity)
        assert rec.profit_share_rate == Decimal(rate)
        assert rec.monthly_installment == Decimal(monthly)
        assert rec.installment_total == Decimal(total)


def test_v43_dashboard_and_chatbot_use_same_single_tf_housing_snapshot():
    rec = _rec(67, 120_000, 36)
    assert rec.profit_share_rate == Decimal("2.88")
    assert rec.variant == "Konut Finansmanı"
    assert rec.mode == "official_calculator_snapshot_model"
