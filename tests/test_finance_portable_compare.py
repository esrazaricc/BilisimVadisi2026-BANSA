import os
from pathlib import Path


from src.finance_live_contract import (
    LiveCalculationStatus,
)

from src.finance_runtime_repository import (
    clear_finance_snapshot_cache,
    get_finance_runtime_info,
    get_standard_products,
)


def _postgres_off(
    monkeypatch,
):

    monkeypatch.delenv(
        "POSTGRES_DSN",
        raising=False,
    )

    clear_finance_snapshot_cache()


def test_snapshot_runtime_without_postgres(
    monkeypatch,
):

    _postgres_off(
        monkeypatch
    )

    frame = get_standard_products()

    info = get_finance_runtime_info()

    assert len(frame) == 274

    assert (
        info["backend"]
        == "sqlite_snapshot"
    )

    assert (
        info[
            "runtime_postgres_required"
        ]
        is False
    )

    assert (
        "POSTGRES_DSN"
        not in os.environ
    )


def test_general_needs_candidate_contract_without_postgres(
    monkeypatch,
):

    _postgres_off(
        monkeypatch
    )

    from src.finance_live_compare import (
        compare_financing,
    )

    results = compare_financing(
        family="ihtiyac_finansmani",
        amount=75000,
        maturity=24,
        purpose="genel_ihtiyac",
        scope="bireysel",
        bank_names=None,
        adapters={},
    )

    ids = {
        int(
            result.request.product_id
        )
        for result in results
    }

    assert ids == {
        4,
        70,
        72,
        121,
        318,
    }

    assert len(results) == 5


def test_dunya_bank_filter_unicode_safe_without_postgres(
    monkeypatch,
):

    _postgres_off(
        monkeypatch
    )

    from src.finance_live_compare import (
        compare_financing,
    )

    # ASCII-safe source representation.
    # Prevents PowerShell pipe encoding
    # from corrupting Turkish literals.
    dunya = (
        "D\u00fcnya "
        "Kat\u0131l\u0131m"
    )

    results = compare_financing(
        family="ihtiyac_finansmani",
        amount=75000,
        maturity=24,
        purpose="genel_ihtiyac",
        scope="bireysel",
        bank_names=[
            dunya
        ],
        adapters={},
    )

    assert len(results) == 1

    result = results[0]

    assert (
        result.request.product_id
        == 4
    )

    assert (
        result.request.bank_name
        == dunya
    )

    assert (
        result.status
        == LiveCalculationStatus.UNVERIFIED
    )

    assert (
        result.calculated_amount
        is None
    )

    assert (
        result.profit_share_rate
        is None
    )

    assert (
        result.monthly_installment
        is None
    )

    assert (
        result.total_repayment
        is None
    )


def test_bank_filter_does_not_change_financial_values(
    monkeypatch,
):

    _postgres_off(
        monkeypatch
    )

    from src.finance_live_compare import (
        compare_financing,
    )

    dunya = (
        "D\u00fcnya "
        "Kat\u0131l\u0131m"
    )

    all_results = compare_financing(
        family="ihtiyac_finansmani",
        amount=75000,
        maturity=24,
        purpose="genel_ihtiyac",
        scope="bireysel",
        bank_names=None,
        adapters={},
    )

    filtered = compare_financing(
        family="ihtiyac_finansmani",
        amount=75000,
        maturity=24,
        purpose="genel_ihtiyac",
        scope="bireysel",
        bank_names=[
            dunya
        ],
        adapters={},
    )

    original = [
        result
        for result in all_results
        if (
            result.request.product_id
            == 4
        )
    ]

    assert len(original) == 1
    assert len(filtered) == 1

    assert (
        original[0].request
        == filtered[0].request
    )

    assert (
        original[0].status
        == filtered[0].status
    )


def test_finance_live_compare_has_no_postgres_runtime_import():

    source = Path(
        "src/finance_live_compare.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "src.postgres_repository"
        not in source
    )

    assert (
        "src.finance_runtime_repository"
        in source
    )
