from src.chat_followup_context import resolve_followup_question
from src.competition_fast_router import detect_banks
from src.competition_natural_chat import answer_natural
from src.finance_runtime_repository import get_standard_products
from src.finance_scenario_projection import project_row


def _row(product_id: int):
    frame = get_standard_products()
    return frame[frame["id"].eq(product_id)].iloc[0]


def test_tf_housing_500k_120_uses_v43_official_calculator_snapshot():
    records = project_row(_row(67), 500_000, 120)
    assert records
    assert all(r.mode == "official_calculator_snapshot_model" for r in records)
    rec = records[0]
    assert rec.profit_share_rate == rec.profit_share_rate.__class__("2.88")
    assert rec.monthly_installment == rec.monthly_installment.__class__("14893.49")
    assert rec.installment_total == rec.installment_total.__class__("1787218.80")


def test_vakif_housing_100k_60_uses_v43_official_calculator_snapshot():
    records = project_row(_row(296), 100_000, 60)
    assert records
    assert all(r.mode == "official_calculator_snapshot_model" for r in records)
    rec = records[0]
    assert rec.profit_share_rate == rec.profit_share_rate.__class__("2.99")
    assert rec.monthly_installment == rec.monthly_installment.__class__("3605.56")
    assert rec.installment_total == rec.installment_total.__class__("216333.48")


def test_vehicle_projection_blocks_out_of_scope_albaraka_need_amount():
    # Albaraka motorcycle/ATV/bicycle needs are fatura/proforma based; 600k is
    # not projected from the small user snapshot.
    assert project_row(_row(118), 600_000, 24) == tuple()


def test_two_bank_housing_compare_calculates_requested_500k_scenario_with_v43_rates():
    result = answer_natural(
        "500.000 TL 36 ay konut finansmanında Vakıf Katılım ile Türkiye Finans karşılaştır"
    )
    assert result is not None
    assert result.route == "finance_compare"
    assert "500.000,00 TL / 36 ay" in result.text
    assert "Vakıf Katılım" in result.text
    assert "Türkiye Finans" in result.text
    assert "%2,88" in result.text
    assert "%2,99" in result.text
    assert "22.493,68 TL" in result.text
    assert "22.867,74 TL" in result.text
    assert "resmî hesaplama ekranı snapshotı" in result.text
    assert "UNVERIFIED" not in result.text


def test_followup_compare_keeps_two_banks_and_uses_v43_projection():
    history = ["Konut finansmanında Vakıf mı Türkiye Finans mı daha avantajlı?"]
    resolution = resolve_followup_question("500.000 TL 36 ay", history)
    assert resolution.used_context
    assert "Vakıf Katılım" in resolution.resolved_question
    assert "Türkiye Finans" in resolution.resolved_question
    result = answer_natural(resolution.resolved_question)
    assert result.route == "finance_compare"
    assert "22.493,68 TL" in result.text
    assert "22.867,74 TL" in result.text


def test_single_bank_tf_projection_answers_actual_amount_not_reference_only():
    result = answer_natural("Türkiye Finans 500.000 TL 36 ay konut finansmanı hesapla")
    assert result.route == "finance_scenario_projection"
    assert "500.000,00 TL / 36 ay" in result.text
    assert "22.493,68 TL" in result.text
    assert "resmî hesaplama ekranı snapshotı" in result.text


def test_single_bank_vakif_projection_answers_actual_amount_not_reference_only():
    result = answer_natural("Vakıf Katılım 500.000 TL 36 ay konut finansmanı hesapla")
    assert result.route == "finance_scenario_projection"
    assert "22.867,74 TL" in result.text
    assert "resmî hesaplama ekranı snapshotı" in result.text


def test_exact_100k_36_housing_compare_uses_v43_snapshot_rates():
    result = answer_natural("100 bin TL 36 ay vade için konut finansmanlarını kıyasla")
    assert result.route == "finance_compare"
    assert "resmî hesaplama ekranı snapshotı" in result.text
    assert "Albaraka Türk" in result.text
    assert "%3,04" in result.text
    assert "161.954,64 TL" in result.text


def test_turkiye_finansi_inflected_alias_is_detected():
    assert "Türkiye Finans" in detect_banks("Vakıf Katılım ile Türkiye Finansı kıyasla")
