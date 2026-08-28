"""
BANSA verified local deterministic finance models.

A provider in this module may return VERIFIED only when:

- the requested product mapping is explicit,
- the requested variant is explicit,
- the maturity has an official published price,
- the deterministic calculation model has been
  independently validated against an official
  calculator benchmark,
- no amount/maturity/rate interpolation is used.

TURKIYE_FINANS_VERIFIED_LOCAL_MODEL_V1
"""

from datetime import (
    datetime,
    timezone,
)
from decimal import (
    Decimal,
    ROUND_HALF_UP,
    localcontext,
)
import unicodedata

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)


_TF_PRODUCT_IDS = {
    70,
    72,
}

_TF_FAMILY = (
    "ihtiyac_finansmani"
)

_TF_BANK_NAMES = {
    "turkiye_finans",
}


_TF_SOURCE_URLS = {

    70: (
        "https://www.turkiyefinans.com.tr/"
        "tr-tr/bireysel/ihtiyac-finansmani/"
        "sayfalar/dijital-ihtiyac-finansmani.aspx"
    ),

    72: (
        "https://www.turkiyefinans.com.tr/"
        "tr-tr/bireysel/ihtiyac-finansmani/"
        "sayfalar/ihtiyac-finansmani.aspx"
    ),
}


# Official published pricing table captured on
# 25 August 2026.
#
# IMPORTANT:
# These are exact published maturity points only.
# No interpolation between maturity values is allowed.
_TF_RATE_TABLE = {

    "sigortali": {
        3: Decimal("4.20"),
        12: Decimal("4.15"),
        18: Decimal("4.10"),
        24: Decimal("4.05"),
        35: Decimal("4.00"),
        36: Decimal("3.80"),
    },

    "sigortasiz": {
        3: Decimal("6.10"),
        12: Decimal("6.05"),
        18: Decimal("6.00"),
        24: Decimal("5.95"),
        35: Decimal("5.90"),
        36: Decimal("5.70"),
    },
}


# T?rkiye Finans' official calculator documentation says
# BSMV and KKDF are each 15% of accrued profit for
# consumer financing.
_TF_BSMV = Decimal("0.15")
_TF_KKDF = Decimal("0.15")


_TF_CHECKED_AT = datetime(
    2026,
    8,
    25,
    tzinfo=timezone.utc,
)


def _normalized(
    value,
):

    text = str(
        value
        or ""
    ).strip()

    text = text.replace(
        "\u0131",
        "i",
    )

    text = text.replace(
        "\u0130",
        "I",
    )

    text = (
        unicodedata
        .normalize(
            "NFKD",
            text,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii",
        )
        .casefold()
    )

    return "_".join(
        text
        .replace("-", " ")
        .split()
    )


def _variant(
    value,
):

    normalized = (
        _normalized(
            value
        )
    )

    aliases = {

        "sigortali":
            "sigortali",

        "sigortasiz":
            "sigortasiz",
    }

    return aliases.get(
        normalized
    )


def _supports(
    request: LiveCalculationRequest,
) -> bool:

    try:

        product_id = int(
            request.product_id
        )

    except Exception:

        return False


    return (
        product_id
        in _TF_PRODUCT_IDS
        and
        _normalized(
            request.bank_name
        )
        in _TF_BANK_NAMES
        and
        _normalized(
            request.family_key
        )
        ==
        _TF_FAMILY
    )


def _monthly_payment(
    *,
    amount: Decimal,
    maturity: int,
    profit_share_rate: Decimal,
) -> Decimal:
    """
    Equal-payment consumer finance model.

    Official T?rkiye Finans documentation states that
    BSMV and KKDF are charged on accrued profit.

    Historical official calculator validation:

      100,000 TL / 36 / sigortali / 3.80
          -> 5,996.94 monthly

      100,000 TL / 36 / sigortasiz / 5.70
          -> 8,021.88 monthly

    Both are reproduced exactly to kuru? by this model.
    """

    principal = Decimal(
        str(amount)
    )

    months = int(
        maturity
    )

    published_rate = (
        Decimal(
            str(
                profit_share_rate
            )
        )
        /
        Decimal("100")
    )

    effective_rate = (
        published_rate
        *
        (
            Decimal("1")
            +
            _TF_BSMV
            +
            _TF_KKDF
        )
    )


    with localcontext() as ctx:

        ctx.prec = 50

        factor = (
            Decimal("1")
            +
            effective_rate
        ) ** months

        payment = (
            principal
            *
            (
                effective_rate
                *
                factor
            )
            /
            (
                factor
                -
                Decimal("1")
            )
        )


    return payment.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _turkiye_finans_needs(
    request: LiveCalculationRequest,
):

    if not _supports(
        request
    ):

        return None


    selected_variant = (
        _variant(
            request.variant
        )
    )


    # Fail closed.
    #
    # Generic requests may not silently choose between
    # insured and uninsured pricing.
    if selected_variant is None:

        return None


    rates = (
        _TF_RATE_TABLE.get(
            selected_variant
        )
    )

    if rates is None:

        return None


    maturity = int(
        request.maturity_months
    )


    # Exact official published maturity points only.
    # Never interpolate/extrapolate rates.
    rate = rates.get(
        maturity
    )

    if rate is None:

        return None


    amount = Decimal(
        str(
            request.amount
        )
    )


    monthly = _monthly_payment(
        amount=amount,
        maturity=maturity,
        profit_share_rate=rate,
    )


    total = (
        monthly
        *
        Decimal(
            maturity
        )
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


    source_url = (
        _TF_SOURCE_URLS[
            int(
                request.product_id
            )
        ]
    )


    result = LiveCalculationResult(
        request=request,

        status=(
            LiveCalculationStatus
            .VERIFIED
        ),

        calculated_amount=amount,

        calculated_maturity_months=
            maturity,

        profit_share_rate=rate,

        monthly_installment=monthly,

        total_repayment=total,

        # Fee coverage deliberately remains incomplete.
        # Do not infer fee totals into ranking.
        allocation_fee=None,
        mortgage_fee=None,
        appraisal_fee=None,
        total_fees=None,

        source_kind=(
            "official_published_pricing_"
            "verified_local_model"
        ),

        source_url=source_url,

        source_note=(
            "T?rkiye Finans official published "
            "needs-financing pricing table, combined "
            "with the bank's documented consumer "
            "finance tax treatment. The deterministic "
            "equal-payment implementation was validated "
            "against official calculator benchmarks. "
            "Only exact published maturity points are "
            "accepted; no rate interpolation is used."
        ),

        checked_at=(
            _TF_CHECKED_AT
        ),

        raw_output={
            "provider":
                "turkiye_finans_needs_v1",

            "variant":
                selected_variant,

            "published_rate":
                str(rate),

            "published_maturity":
                maturity,

            "bsmv":
                str(_TF_BSMV),

            "kkdf":
                str(_TF_KKDF),

            "rate_interpolation":
                False,

            "benchmark_validated":
                True,
        },
    )


    return validate_live_result(
        result
    )


def resolve_verified_local_model(
    request: LiveCalculationRequest,
):
    """
    Central verified-local-model provider registry.

    Add future bank models here only after their product
    mapping and deterministic pricing behavior have been
    independently verified.
    """

    providers = (
        _turkiye_finans_needs,
    )


    matches = []


    for provider in providers:

        result = provider(
            request
        )

        if result is not None:

            matches.append(
                result
            )


    if len(matches) > 1:

        raise RuntimeError(
            "Multiple verified local pricing models "
            "matched the same finance request."
        )


    if not matches:

        return None


    return matches[0]


# ============================================================
# FINANCE_CONDITIONAL_VERIFIED_VARIANTS_V1
#
# Registry for condition-specific verified local pricing
# results. This is intentionally separate from the single
# result resolver:
#
#   resolve_verified_local_model()
#
# A generic request is NEVER silently converted into one of
# these variants. They are presentation/evidence alternatives
# until the user explicitly selects a condition.
# ============================================================


def _turkiye_finans_needs_variants(
    request: LiveCalculationRequest,
):

    if request.variant is not None:
        return tuple()

    if not _supports(
        request
    ):
        return tuple()

    results = []

    for variant in (
        "sigortali",
        "sigortasiz",
    ):

        variant_request = (
            LiveCalculationRequest(
                product_id=(
                    request.product_id
                ),
                bank_name=(
                    request.bank_name
                ),
                product_name=(
                    request.product_name
                ),
                family_key=(
                    request.family_key
                ),
                amount=(
                    request.amount
                ),
                maturity_months=(
                    request.maturity_months
                ),
                variant=variant,
                metadata=(
                    request.metadata
                ),
            )
        )

        result = (
            resolve_verified_local_model(
                variant_request
            )
        )

        if result is None:
            continue

        result.validate()

        if (
            result.status
            !=
            LiveCalculationStatus.VERIFIED
            or
            not result.is_exact_match
            or
            not result.is_rankable
        ):
            raise RuntimeError(
                "Conditional verified local model "
                "returned an unsafe result."
            )

        results.append(
            result
        )

    return tuple(
        results
    )


def resolve_verified_local_variants(
    request: LiveCalculationRequest,
):
    """
    Return independently verified condition-specific results
    for one generic exact finance request.

    An empty tuple means no conditional verified capability.
    """

    providers = (
        _turkiye_finans_needs_variants,
    )

    matches = []

    for provider in providers:

        values = tuple(
            provider(
                request
            )
            or ()
        )

        if values:
            matches.append(
                values
            )

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple conditional verified local model "
            "providers matched one finance request."
        )

    if not matches:
        return tuple()

    return matches[0]

