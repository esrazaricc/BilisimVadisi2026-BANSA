from __future__ import annotations

import argparse
from decimal import Decimal

import requests
from bs4 import BeautifulSoup


try:
    from .common import (
        assert_canonical_unchanged,
        assert_latest_scenario,
        assert_product_identity,
        backup_scenarios,
        canonical_snapshot,
        connect_postgres,
        insert_scenario,
        normalize_text,
        to_decimal,
        utc_now,
    )
except ImportError:
    from common import (
        assert_canonical_unchanged,
        assert_latest_scenario,
        assert_product_identity,
        backup_scenarios,
        canonical_snapshot,
        connect_postgres,
        insert_scenario,
        normalize_text,
        to_decimal,
        utc_now,
    )


# ============================================================
# TURKIYE EMLAK KATILIM
# Official live finance calculator integration
# ============================================================

BANK_NAME = "T\u00fcrkiye Emlak Kat\u0131l\u0131m"

BASE_URL = (
    "https://www.emlakkatilim.com.tr"
)

CALCULATOR_PAGE = (
    BASE_URL + "/tr"
)

PROPERTY_ENDPOINT = (
    BASE_URL
    + "/Plugins/SelectLoansProperty"
)

CALCULATOR_ENDPOINT = (
    BASE_URL
    + "/Plugins/CalculateLoansProduct"
)


SCENARIO_KEY = (
    "benchmark_100000_24"
)

SCENARIO_TYPE = (
    "live_calculator_snapshot"
)

SCENARIO_STATUS = (
    "verified_live_calculator_direct_mapping"
)

SOURCE_KIND = (
    "official_live_calculator_endpoint"
)


AMOUNT = Decimal("100000")
MONTHS = 24

PLAN_TOLERANCE = Decimal("0.50")
BALANCE_TOLERANCE = Decimal("0.01")
FEE_TOLERANCE = Decimal("0.01")


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language":
        "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
}

AJAX_HEADERS = {
    **HEADERS,
    "Accept":
        "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With":
        "XMLHttpRequest",
    "Referer":
        CALCULATOR_PAGE,
}


# Exact mappings verified against:
# - official calculator catalog
# - official product source pages
# - current BANSA PostgreSQL identities
MAPPINGS = [
    {
        "calculator_code":
            "ARACBINEK2EL",

        "calculator_title":
            "2. El Ta\u015f\u0131t Finansman\u0131",

        "segment_id":
            "1",

        "product_id":
            230,

        "product_name":
            "Ta\u015f\u0131t Finansman\u0131",

        "family_key":
            "arac_finansmani",

        "scope":
            "bireysel",

        "variant":
            "2el",

        "source_checks": [
            "Ta\u015f\u0131t Finansman\u0131",
            "s\u0131f\u0131r",
            "ikinci el",
        ],
    },

    {
        "calculator_code":
            "ARACBINEKYENI",

        "calculator_title":
            "0 Km Ta\u015f\u0131t Finansman\u0131",

        "segment_id":
            "1",

        "product_id":
            230,

        "product_name":
            "Ta\u015f\u0131t Finansman\u0131",

        "family_key":
            "arac_finansmani",

        "scope":
            "bireysel",

        "variant":
            "0km",

        "source_checks": [
            "Ta\u015f\u0131t Finansman\u0131",
            "s\u0131f\u0131r",
            "ikinci el",
        ],
    },

    {
        "calculator_code":
            "EVOFISGERECLERI",

        "calculator_title":
            "\u0130htiya\u00e7 Finansman\u0131",

        "segment_id":
            "2",

        "product_id":
            273,

        "product_name":
            "Ev/Ofis Gere\u00e7leri T\u00fcketici Finansman\u0131",

        "family_key":
            "ihtiyac_finansmani",

        "scope":
            "bireysel",

        "variant":
            "standard",

        "source_checks": [
            "Ev/Ofis Gere\u00e7leri T\u00fcketici Finansman\u0131",
        ],
    },

    {
        "calculator_code":
            "GMENKULKONUTYENI",

        "calculator_title":
            "Yeni Konut Finansman\u0131",

        "segment_id":
            "2",

        "product_id":
            242,

        "product_name":
            "Konut Finansman\u0131",

        "family_key":
            "konut_finansmani",

        "scope":
            "bireysel",

        "variant":
            "yeni_konut",

        "source_checks": [
            "Konut Finansman\u0131",
        ],
    },
]


def create_session():
    return requests.Session()


def discover_official_catalog(
    session,
):
    """
    Read the official calculator form and verify that
    bank-rate mode still disables CustomRate.
    """

    response = session.get(
        CALCULATOR_PAGE,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    form = soup.find(
        "form",
        id="CalculationTypeld",
    )

    if form is None:
        raise RuntimeError(
            "Official calculator form bulunamadi."
        )

    select = form.find(
        "select",
        id="js-productType",
    )

    if select is None:
        raise RuntimeError(
            "Official calculator product catalog bulunamadi."
        )

    rate_input = form.find(
        "input",
        attrs={
            "name":
                "CustomRate"
        },
    )

    if (
        rate_input is None
        or not rate_input.has_attr(
            "disabled"
        )
    ):
        raise RuntimeError(
            "CustomRate bank-rate semantigi degisti."
        )

    catalog = {}

    for option in select.find_all(
        "option"
    ):

        code = str(
            option.get("value")
            or ""
        ).strip()

        if not code:
            continue

        catalog[code] = {
            "title":
                " ".join(
                    option.stripped_strings
                ),

            "segment_id":
                str(
                    option.get(
                        "data-custom-properties"
                    )
                    or ""
                ).strip(),
        }

    for mapping in MAPPINGS:

        code = mapping[
            "calculator_code"
        ]

        actual = catalog.get(
            code
        )

        if actual is None:
            raise RuntimeError(
                f"Calculator product kayboldu: {code}"
            )

        if normalize_text(
            actual["title"]
        ) != normalize_text(
            mapping[
                "calculator_title"
            ]
        ):
            raise RuntimeError(
                "Calculator product title degisti | "
                f"{code} | "
                f"{actual['title']}"
            )

        if (
            actual["segment_id"]
            != mapping["segment_id"]
        ):
            raise RuntimeError(
                "Calculator segment degisti | "
                f"{code}"
            )

    return catalog


def verify_product_source(
    session,
    *,
    source_url,
    phrases,
):
    """
    Verify that canonical BANSA mapping is still
    supported by the official product page.
    """

    response = session.get(
        source_url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    text = normalize_text(
        BeautifulSoup(
            response.text,
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )
    )

    checks = {
        phrase:
            normalize_text(phrase)
            in text
        for phrase in phrases
    }

    if not all(
        checks.values()
    ):
        raise RuntimeError(
            "Official product source semantic check failed | "
            f"{source_url} | "
            f"{checks}"
        )

    return checks


def fetch_product_property(
    session,
    calculator_code,
):
    """
    Read official maturity limits.
    """

    response = session.get(
        PROPERTY_ENDPOINT,
        params={
            "ProductTypeId":
                calculator_code,
        },
        headers=AJAX_HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if (
        not isinstance(
            payload,
            dict,
        )
        or not payload.get(
            "Success"
        )
    ):
        raise RuntimeError(
            "Property endpoint failed | "
            f"{calculator_code}"
        )

    data = (
        payload.get("Data")
        or {}
    )

    try:
        maturity_min = int(
            data.get(
                "MaturityMin"
            )
        )
    except Exception:
        maturity_min = None

    try:
        maturity_max = int(
            data.get(
                "MaturityMax"
            )
        )
    except Exception:
        maturity_max = None

    if (
        maturity_max is None
        or MONTHS > maturity_max
    ):
        raise RuntimeError(
            "Benchmark maturity unsupported | "
            f"{calculator_code}"
        )

    if (
        maturity_min is not None
        and MONTHS
        < maturity_min + 1
    ):
        raise RuntimeError(
            "Benchmark maturity below minimum | "
            f"{calculator_code}"
        )

    return {
        "maturity_min":
            maturity_min,

        "maturity_max":
            maturity_max,
    }


def fetch_live_calculation(
    session,
    mapping,
):
    """
    Fetch one official bank-rate calculation.

    IMPORTANT:
    CustomRate is deliberately omitted.

    The official calculator form disables CustomRate
    while using the bank's own rate.
    """

    property_data = (
        fetch_product_property(
            session,
            mapping[
                "calculator_code"
            ],
        )
    )

    params = {
        "CalculationTypeId":
            "1",

        "ProductTypeId":
            mapping[
                "calculator_code"
            ],

        "LoanAmount":
            str(
                int(AMOUNT)
            ),

        "LoanMaturity":
            str(MONTHS),

        "LoanSegmentId":
            mapping[
                "segment_id"
            ],
    }

    response = session.get(
        CALCULATOR_ENDPOINT,
        params=params,
        headers=AJAX_HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if (
        not isinstance(
            payload,
            dict,
        )
        or not payload.get(
            "Success"
        )
        or not isinstance(
            payload.get("Data"),
            dict,
        )
        or not payload.get(
            "Data"
        )
    ):
        raise RuntimeError(
            "Live calculator data failed | "
            f"{mapping['calculator_code']}"
        )

    data = payload["Data"]

    rate = to_decimal(
        data.get(
            "ProfitRate"
        )
    )

    funding = to_decimal(
        data.get(
            "FundingAmount"
        )
    )

    total = to_decimal(
        data.get(
            "TotalInstallmentAmount"
        )
    )

    commission = to_decimal(
        data.get(
            "CommissionAmount"
        )
    )

    mortgage = to_decimal(
        data.get(
            "HypothecAmount"
        )
    )

    appraisal = to_decimal(
        data.get(
            "ExpertiseAmount"
        )
    )

    total_fees = to_decimal(
        data.get(
            "TotalExpense"
        )
    )

    plan = (
        data.get(
            "InstallmentContractList"
        )
        or []
    )

    monthly = (
        to_decimal(
            plan[0].get(
                "Amount"
            )
        )
        if plan
        else None
    )

    last_installment = (
        to_decimal(
            plan[-1].get(
                "Amount"
            )
        )
        if plan
        else None
    )

    final_balance = (
        to_decimal(
            plan[-1].get(
                "RemainingPrincipalAmount"
            )
        )
        if plan
        else None
    )

    plan_values = [
        to_decimal(
            row.get(
                "Amount"
            )
        )
        for row in plan
    ]

    if any(
        value is None
        for value in plan_values
    ):
        raise RuntimeError(
            "Payment plan contains null amount | "
            f"{mapping['calculator_code']}"
        )

    plan_sum = sum(
        plan_values,
        Decimal("0"),
    )

    plan_delta = (
        abs(
            plan_sum
            - total
        )
        if total is not None
        else None
    )

    fee_component_sum = (
        (commission or Decimal("0"))
        +
        (mortgage or Decimal("0"))
        +
        (appraisal or Decimal("0"))
    )

    fee_delta = (
        abs(
            fee_component_sum
            - total_fees
        )
        if total_fees is not None
        else None
    )

    checks = {
        "RATE":
            rate is not None
            and rate > 0,

        "FUNDING":
            funding == AMOUNT,

        "INSTALLMENT_COUNT":
            data.get(
                "InstallmentCount"
            )
            == MONTHS,

        "PLAN_ROWS":
            len(plan)
            == MONTHS,

        "MONTHLY":
            monthly is not None
            and monthly > 0,

        "TOTAL":
            total is not None
            and total > 0,

        "PLAN_SUM":
            plan_delta is not None
            and plan_delta
            <= PLAN_TOLERANCE,

        "FINAL_BALANCE":
            final_balance is not None
            and abs(
                final_balance
            )
            <= BALANCE_TOLERANCE,

        "ALLOCATION_FEE":
            commission is not None
            and commission >= 0,

        "MORTGAGE_FEE":
            mortgage is not None
            and mortgage >= 0,

        "APPRAISAL_FEE":
            appraisal is not None
            and appraisal >= 0,

        "TOTAL_FEES":
            total_fees is not None
            and total_fees >= 0,
    }

    if not all(
        checks.values()
    ):
        raise RuntimeError(
            "Live calculator validation failed | "
            f"{mapping['calculator_code']} | "
            f"{checks}"
        )

    fee_warning = (
        fee_delta is not None
        and fee_delta
        > FEE_TOLERANCE
    )

    # Only the verified housing response currently
    # contains an official component/TotalExpense delta.
    if (
        mapping[
            "calculator_code"
        ]
        != "GMENKULKONUTYENI"
        and fee_warning
    ):
        raise RuntimeError(
            "Unexpected calculator fee mismatch | "
            f"{mapping['calculator_code']} | "
            f"delta={fee_delta}"
        )

    return {
        **mapping,

        **property_data,

        "rate":
            rate,

        "funding":
            funding,

        "monthly":
            monthly,

        "last_installment":
            last_installment,

        "total":
            total,

        "commission":
            commission,

        "mortgage":
            mortgage,

        "appraisal":
            appraisal,

        "total_fees":
            total_fees,

        "fee_component_sum":
            fee_component_sum,

        "fee_delta":
            fee_delta,

        "fee_warning":
            fee_warning,

        "plan_count":
            len(plan),

        "plan_sum":
            plan_sum,

        "plan_delta":
            plan_delta,

        "final_balance":
            final_balance,

        # Kept for evidence only.
        # Semantics are not normalized without
        # independent proof.
        "total_cost_raw":
            data.get(
                "TotalCost"
            ),

        "monthly_const_rate_raw":
            data.get(
                "MonthlyConstRate"
            ),
    }


def build_source_note(
    result,
):
    note = (
        "Turkiye Emlak Katilim official calculator "
        "live snapshot for 100,000 TL / 24 months "
        "using bank-rate mode. "
        "CustomRate was omitted because the official "
        "form disables this field while the bank rate "
        "is active. "
        "profit_share_rate=ProfitRate; "
        "monthly_installment=first payment-plan Amount; "
        "total_repayment=TotalInstallmentAmount; "
        "allocation_fee=CommissionAmount; "
        "mortgage_fee=HypothecAmount; "
        "appraisal_fee=ExpertiseAmount; "
        "total_fees=TotalExpense. "
        "TotalCost and MonthlyConstRate are retained "
        "only as raw evidence and are not normalized."
    )

    if result[
        "fee_warning"
    ]:
        note += (
            " Official calculator fee components "
            "do not arithmetically equal TotalExpense. "
            "BANSA preserves the official fields "
            "without recalculation. "
            f"component_sum="
            f"{result['fee_component_sum']}; "
            f"TotalExpense="
            f"{result['total_fees']}; "
            f"delta="
            f"{result['fee_delta']}."
        )

    return note


def build_input_metadata(
    result,
    canonical_source_url,
):
    return {
        "bank":
            BANK_NAME,

        "calculator_product_code":
            result[
                "calculator_code"
            ],

        "calculator_product_title":
            result[
                "calculator_title"
            ],

        "loan_segment_id":
            result[
                "segment_id"
            ],

        "calculator_maturity_min":
            result[
                "maturity_min"
            ],

        "calculator_maturity_max":
            result[
                "maturity_max"
            ],

        "bank_rate_mode":
            True,

        "custom_rate_sent":
            False,

        "mapping":
            "verified_direct_product_mapping",

        "canonical_product_source_url":
            canonical_source_url,

        "fee_consistency_warning":
            result[
                "fee_warning"
            ],

        "fee_component_sum":
            str(
                result[
                    "fee_component_sum"
                ]
            ),

        "official_total_expense":
            str(
                result[
                    "total_fees"
                ]
            ),

        "fee_difference":
            str(
                result[
                    "fee_delta"
                ]
            ),
    }


def build_raw_output(
    result,
):
    return {
        "summary": {
            "FundingAmount":
                str(
                    result[
                        "funding"
                    ]
                ),

            "InstallmentCount":
                MONTHS,

            "ProfitRate":
                str(
                    result[
                        "rate"
                    ]
                ),

            "FirstInstallmentAmount":
                str(
                    result[
                        "monthly"
                    ]
                ),

            "LastInstallmentAmount":
                str(
                    result[
                        "last_installment"
                    ]
                ),

            "TotalInstallmentAmount":
                str(
                    result[
                        "total"
                    ]
                ),

            "CommissionAmount":
                str(
                    result[
                        "commission"
                    ]
                ),

            "HypothecAmount":
                str(
                    result[
                        "mortgage"
                    ]
                ),

            "ExpertiseAmount":
                str(
                    result[
                        "appraisal"
                    ]
                ),

            "TotalExpense":
                str(
                    result[
                        "total_fees"
                    ]
                ),

            "TotalCost_raw":
                result[
                    "total_cost_raw"
                ],

            "MonthlyConstRate_raw":
                result[
                    "monthly_const_rate_raw"
                ],
        },

        "validation": {
            "payment_plan_rows":
                result[
                    "plan_count"
                ],

            "payment_plan_sum":
                str(
                    result[
                        "plan_sum"
                    ]
                ),

            "payment_plan_total_delta":
                str(
                    result[
                        "plan_delta"
                    ]
                ),

            "final_remaining_principal":
                str(
                    result[
                        "final_balance"
                    ]
                ),

            "fee_component_sum":
                str(
                    result[
                        "fee_component_sum"
                    ]
                ),

            "fee_total_delta":
                str(
                    result[
                        "fee_delta"
                    ]
                ),

            "fee_consistency_warning":
                result[
                    "fee_warning"
                ],
        },
    }


def print_result(
    result,
):
    print(
        f"{result['calculator_code']:<20} | "
        f"ID={result['product_id']:<4} | "
        f"VARIANT={result['variant']:<10} | "
        f"RATE={result['rate']} | "
        f"MONTHLY={result['monthly']} | "
        f"TOTAL={result['total']} | "
        f"TAHSIS={result['commission']} | "
        f"IPOTEK={result['mortgage']} | "
        f"EKSPERTIZ={result['appraisal']} | "
        f"MASRAF={result['total_fees']} | "
        f"FEE_WARNING={result['fee_warning']}"
    )


def run(
    *,
    write=False,
):
    """
    Refresh and validate all four verified Emlak
    calculator scenarios.

    Default behavior is READ ONLY.

    Database writes require explicit --write.
    """

    print("=" * 150)

    print(
        "TURKIYE EMLAK KATILIM - "
        "LIVE FINANCE SCENARIO SYNC"
    )

    print("=" * 150)

    print(
        "MODE =",
        (
            "WRITE"
            if write
            else "READ ONLY"
        ),
    )

    session = create_session()

    discover_official_catalog(
        session
    )

    print(
        "OFFICIAL CALCULATOR CATALOG = PASS"
    )

    print(
        "BANK RATE MODE = CustomRate OMIT"
    )

    conn = connect_postgres()

    try:

        product_ids = sorted(
            {
                mapping[
                    "product_id"
                ]
                for mapping
                in MAPPINGS
            }
        )

        canonical_before = (
            canonical_snapshot(
                conn,
                product_ids,
            )
        )

        source_urls = {}

        checked_sources = set()

        for mapping in MAPPINGS:

            product = (
                assert_product_identity(
                    conn,

                    product_id=
                        mapping[
                            "product_id"
                        ],

                    bank_name=
                        BANK_NAME,

                    product_name=
                        mapping[
                            "product_name"
                        ],

                    family_key=
                        mapping[
                            "family_key"
                        ],

                    scope=
                        mapping[
                            "scope"
                        ],
                )
            )

            source_url = (
                product[
                    "source_url"
                ]
            )

            source_urls[
                mapping[
                    "product_id"
                ]
            ] = source_url

            source_key = (
                source_url,
                tuple(
                    mapping[
                        "source_checks"
                    ]
                ),
            )

            if (
                source_key
                not in checked_sources
            ):

                verify_product_source(
                    session,

                    source_url=
                        source_url,

                    phrases=
                        mapping[
                            "source_checks"
                        ],
                )

                checked_sources.add(
                    source_key
                )

        print(
            "DATABASE PRODUCT IDENTITY = PASS"
        )

        print(
            "OFFICIAL PRODUCT SOURCE SEMANTICS = PASS"
        )

        results = []

        for mapping in MAPPINGS:

            result = (
                fetch_live_calculation(
                    session,
                    mapping,
                )
            )

            results.append(
                result
            )

            print_result(
                result
            )

        if len(results) != 4:
            raise RuntimeError(
                "Expected four calculator scenarios."
            )

        print()
        print(
            "LIVE CALCULATOR VALIDATION = PASS (4/4)"
        )

        if not write:

            canonical_after = (
                canonical_snapshot(
                    conn,
                    product_ids,
                )
            )

            assert_canonical_unchanged(
                canonical_before,
                canonical_after,
            )

            conn.rollback()

            print()
            print(
                "READ ONLY PASS"
            )

            print(
                "POSTGRESQL DEGISTIRILMEDI"
            )

            print(
                "SCENARIO EKLENMEDI"
            )

            print(
                "CANONICAL STANDARD_PRODUCTS DEGISTIRILMEDI"
            )

            return results


        backup_path = (
            backup_scenarios(
                conn,

                bank_slug=
                    "emlak_katilim",

                product_ids=
                    product_ids,
            )
        )

        print()
        print(
            "BACKUP =",
            backup_path,
        )

        checked_at = utc_now()

        inserted_ids = []

        for result in results:

            scenario_id = (
                insert_scenario(
                    conn,

                    product_id=
                        result[
                            "product_id"
                        ],

                    scenario_key=
                        SCENARIO_KEY,

                    scenario_type=
                        SCENARIO_TYPE,

                    input_amount=
                        AMOUNT,

                    input_maturity_months=
                        MONTHS,

                    input_variant=
                        result[
                            "variant"
                        ],

                    input_metadata=
                        build_input_metadata(
                            result,

                            source_urls[
                                result[
                                    "product_id"
                                ]
                            ],
                        ),

                    profit_share_rate=
                        result[
                            "rate"
                        ],

                    monthly_installment=
                        result[
                            "monthly"
                        ],

                    total_repayment=
                        result[
                            "total"
                        ],

                    monthly_cost_rate=
                        None,

                    annual_cost_rate=
                        None,

                    effective_annual_profit_rate=
                        None,

                    allocation_fee=
                        result[
                            "commission"
                        ],

                    mortgage_fee=
                        result[
                            "mortgage"
                        ],

                    appraisal_fee=
                        result[
                            "appraisal"
                        ],

                    total_fees=
                        result[
                            "total_fees"
                        ],

                    scenario_status=
                        SCENARIO_STATUS,

                    source_kind=
                        SOURCE_KIND,

                    source_url=
                        CALCULATOR_PAGE,

                    source_note=
                        build_source_note(
                            result
                        ),

                    raw_output=
                        build_raw_output(
                            result
                        ),

                    checked_at=
                        checked_at,
                )
            )

            inserted_ids.append(
                scenario_id
            )

        for result in results:

            assert_latest_scenario(
                conn,

                product_id=
                    result[
                        "product_id"
                    ],

                scenario_key=
                    SCENARIO_KEY,

                input_variant=
                    result[
                        "variant"
                    ],

                expected={
                    "input_amount":
                        AMOUNT,

                    "input_maturity_months":
                        MONTHS,

                    "profit_share_rate":
                        result[
                            "rate"
                        ],

                    "monthly_installment":
                        result[
                            "monthly"
                        ],

                    "total_repayment":
                        result[
                            "total"
                        ],

                    "allocation_fee":
                        result[
                            "commission"
                        ],

                    "mortgage_fee":
                        result[
                            "mortgage"
                        ],

                    "appraisal_fee":
                        result[
                            "appraisal"
                        ],

                    "total_fees":
                        result[
                            "total_fees"
                        ],

                    "monthly_cost_rate":
                        None,

                    "annual_cost_rate":
                        None,

                    "effective_annual_profit_rate":
                        None,

                    "scenario_status":
                        SCENARIO_STATUS,

                    "source_kind":
                        SOURCE_KIND,

                    "source_url":
                        CALCULATOR_PAGE,
                },
            )

        canonical_after = (
            canonical_snapshot(
                conn,
                product_ids,
            )
        )

        assert_canonical_unchanged(
            canonical_before,
            canonical_after,
        )

        conn.commit()

        print()
        print(
            "WRITE PASS"
        )

        print(
            "INSERTED =",
            len(
                inserted_ids
            ),
        )

        print(
            "LATEST VIEW VERIFIED = 4/4"
        )

        print(
            "CANONICAL STANDARD_PRODUCTS = UNCHANGED"
        )

        return results

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


def main():

    parser = argparse.ArgumentParser(
        description=(
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m resmi canl? "
            "finansman hesaplama senaryolar?n? "
            "do?rular ve iste?e ba?l? olarak "
            "PostgreSQL'e yazar."
        )
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Do?rulanm?? canl? senaryolar? "
            "product_finance_scenarios tablosuna yaz."
        ),
    )

    args = parser.parse_args()

    run(
        write=args.write
    )


if __name__ == "__main__":
    main()
