from decimal import Decimal
from pathlib import Path

from src.finance_live_contract import (
    LiveCalculationRequest,
)

from src.finance_live_adapters.albaraka import (
    AlbarakaLiveAdapter,
)

from src.finance_live_adapters.albaraka_konut import (
    AlbarakaKonutLiveAdapter,
)

from src.finance_live_adapters.dunya_katilim import (
    DunyaKatilimLiveAdapter,
)

from src.finance_live_compare import (
    default_live_adapters,
)


def request(
    product_id,
    bank,
    product,
    variant=None,
):

    return LiveCalculationRequest(
        product_id=product_id,

        bank_name=bank,

        product_name=product,

        family_key=(
            "konut_finansmani"
        ),

        amount=Decimal(
            "100000"
        ),

        maturity_months=36,

        variant=variant,
    )


def test_albaraka_housing_adapter_handles_97():

    adapter = (
        AlbarakaKonutLiveAdapter()
    )

    for variant in (
        None,
        "standard",
        "ilk_ev",
        "mevcut_konut",
    ):

        assert adapter.can_handle(
            request(
                97,
                "Albaraka T\u00fcrk",
                "Konut Finansman\u0131",
                variant,
            )
        )


def test_legacy_albaraka_does_not_overlap_product_97():

    adapter = (
        AlbarakaLiveAdapter()
    )

    assert not adapter.can_handle(
        request(
            97,
            "Albaraka T\u00fcrk",
            "Konut Finansman\u0131",
        )
    )


def test_albaraka_housing_reuses_existing_decimal_parser():

    adapter = (
        AlbarakaKonutLiveAdapter()
    )

    assert (
        adapter._decimal(
            "4.612,28 TL"
        )
        ==
        Decimal(
            "4612.28"
        )
    )

    assert (
        adapter._decimal(
            "166.042,68 TL"
        )
        ==
        Decimal(
            "166042.68"
        )
    )

    assert (
        adapter._decimal(
            "% 88,56"
        )
        ==
        Decimal(
            "88.56"
        )
    )


def test_dunya_housing_adapter_handles_product_3():

    adapter = (
        DunyaKatilimLiveAdapter()
    )

    for variant in (
        None,
        "standard",
        "yeni_konut",
        "2el_konut",
    ):

        assert adapter.can_handle(
            request(
                3,
                "D\u00fcnya Kat\u0131l\u0131m",
                "Konut Finansman\u0131",
                variant,
            )
        )


def test_registry_has_each_new_adapter_once():

    names = [
        type(adapter).__name__

        for adapter
        in default_live_adapters()
    ]

    assert (
        names.count(
            "AlbarakaKonutLiveAdapter"
        )
        ==
        1
    )

    assert (
        names.count(
            "DunyaKatilimLiveAdapter"
        )
        ==
        1
    )


def test_product_97_has_exactly_one_live_adapter():

    req = request(
        97,
        "Albaraka T\u00fcrk",
        "Konut Finansman\u0131",
    )

    matches = [
        adapter

        for adapter
        in default_live_adapters()

        if adapter.can_handle(
            req
        )
    ]

    assert len(matches) == 1

    assert (
        type(matches[0]).__name__
        ==
        "AlbarakaKonutLiveAdapter"
    )


def test_stale_albaraka_portable_guard_remains():

    source = Path(
        "src/finance_live_compare.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "ALBARAKA_KONUT_PORTABLE_PROVENANCE_GUARD_V2"
        in source
    )
