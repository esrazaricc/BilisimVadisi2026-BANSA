from types import SimpleNamespace

from src.chatbot_finance_renderer import (
    _scoped_unresolved_finance_items,
)


def _item(
    *,
    product_id,
    status,
    rankable=False,
):
    return SimpleNamespace(
        product_id=product_id,
        bank_name="Test Bank",
        product_name="Test Product",
        status=status,
        rankable=rankable,
    )


def _context(*items):
    return SimpleNamespace(
        finance_results=items,
    )


def test_verified_non_rankable_is_not_unresolved():

    verified = _item(
        product_id=10,
        status="verified",
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                verified
            )
        )
    )

    assert actual == ()


def test_enum_style_verified_is_not_unresolved():

    verified = _item(
        product_id=10,
        status=(
            "LiveCalculationStatus.VERIFIED"
        ),
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                verified
            )
        )
    )

    assert actual == ()


def test_true_unverified_remains_unresolved():

    unresolved = _item(
        product_id=11,
        status="unverified",
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                unresolved
            )
        )
    )

    assert actual == (
        unresolved,
    )


def test_ineligible_is_not_unresolved():

    ineligible = _item(
        product_id=12,
        status="ineligible",
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                ineligible
            )
        )
    )

    assert actual == ()


def test_rankable_item_is_not_unresolved():

    verified = _item(
        product_id=13,
        status="verified",
        rankable=True,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                verified
            )
        )
    )

    assert actual == ()


def test_verified_product_suppresses_generic_duplicate():

    verified_variant = _item(
        product_id=242,
        status="verified",
        rankable=False,
    )

    generic_unverified = _item(
        product_id=242,
        status="unverified",
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                verified_variant,
                generic_unverified,
            )
        )
    )

    assert actual == ()


def test_other_unverified_product_is_preserved():

    verified_variant = _item(
        product_id=242,
        status="verified",
        rankable=False,
    )

    another_product = _item(
        product_id=296,
        status="unverified",
        rankable=False,
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                verified_variant,
                another_product,
            )
        )
    )

    assert actual == (
        another_product,
    )



def test_grounded_verified_flag_excludes_condition_specific_item():

    # Mirrors the grounded shape used by the HV4 renderer:
    # condition-specific finance result is verified/exact but
    # does not need a textual status="verified" signal.
    item = SimpleNamespace(
        product_id=242,
        bank_name="T?rkiye Emlak Kat?l?m",
        product_name="Konut Finansman?",
        status="unverified",
        rankable=False,
        verified=True,
        exact_match=True,
        presentation_variants=(
            "yeni_konut",
        ),
    )

    actual = (
        _scoped_unresolved_finance_items(
            _context(
                item
            )
        )
    )

    assert actual == ()
