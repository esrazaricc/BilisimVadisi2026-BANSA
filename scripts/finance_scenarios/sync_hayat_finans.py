from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )


from common import (
    assert_canonical_unchanged,
    assert_product_identity,
    backup_scenarios,
    canonical_snapshot,
    connect_postgres,
    get_latest_scenario,
    insert_scenario,
    utc_now,
)


BANK_NAME = "Hayat Finans"

BANK_SLUG = "hayat_finans"

PRODUCT_ID = 54

PRODUCT_NAME = "Bana Bunu Al"

FAMILY_KEY = "alisveris_finansmani"

SCOPE = "bireysel"


HOME_URL = (
    "https://hayatfinans.com.tr/"
)

PRODUCT_URL = (
    "https://hayatfinans.com.tr/"
    "krediler/bana-bunu-al"
)

CALCULATE_URL = (
    "https://hayatfinans.com.tr/"
    "api/integration/calculateloansproduct"
)


SCENARIO_KEY = (
    "benchmark_50000_18"
)

SCENARIO_TYPE = (
    "live_calculator_snapshot"
)

INPUT_VARIANT = "standard"

BENCHMARK_AMOUNT = Decimal(
    "50000"
)

BENCHMARK_MONTHS = 18


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": (
        "tr-TR,tr;q=0.9,"
        "en-US;q=0.8,en;q=0.7"
    ),
    "Culture": "tr-TR",
}


def banner(
    title: str,
) -> None:

    print(
        "=" * 150
    )

    print(
        title
    )

    print(
        "=" * 150
    )


def normalize_source_text(
    value: str,
) -> str:

    value = (
        value
        .replace(
            "\u0131",
            "i",
        )
        .replace(
            "\u0130",
            "I",
        )
    )

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        ch
        for ch in value
        if not unicodedata.combining(
            ch
        )
    )

    value = value.casefold()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def decimal_value(
    value: Any,
) -> Decimal:

    if value is None:
        raise RuntimeError(
            "Expected numeric value, got None."
        )

    return Decimal(
        str(value)
    )


def parse_rate(
    value: str,
) -> Decimal:

    return Decimal(
        value.replace(
            ",",
            ".",
        )
    )


def parse_tl_integer(
    value: str,
) -> int:

    digits = re.sub(
        r"[^0-9]",
        "",
        value,
    )

    if not digits:
        raise RuntimeError(
            "TL amount could not be parsed."
        )

    return int(
        digits
    )


def fetch_text(
    session: requests.Session,
    url: str,
) -> str:

    response = session.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    try:

        return response.content.decode(
            "utf-8"
        )

    except UnicodeDecodeError:

        if response.apparent_encoding:
            response.encoding = (
                response.apparent_encoding
            )

        return response.text


def extract_product_page_semantics(
    session: requests.Session,
) -> dict[str, Any]:

    html = fetch_text(
        session,
        PRODUCT_URL,
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = normalize_source_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )


    if (
        "bana bunu al"
        not in text
    ):

        raise RuntimeError(
            "Official product page identity "
            "check failed."
        )


    maximum_match = re.search(
        (
            r"maksimum kredi\s*"
            r"\(finansman\)\s*"
            r"limiti\s*"
            r"([0-9][0-9.]*)\s*tl"
        ),
        text,
    )

    if maximum_match is None:

        raise RuntimeError(
            "Official maximum financing "
            "limit could not be parsed."
        )


    minimum_match = re.search(
        (
            r"minimum tutar\s*"
            r"([0-9][0-9.]*)\s*tl"
        ),
        text,
    )

    if minimum_match is None:

        raise RuntimeError(
            "Official minimum financing "
            "amount could not be parsed."
        )


    product_maximum = parse_tl_integer(
        maximum_match.group(1)
    )

    product_minimum = parse_tl_integer(
        minimum_match.group(1)
    )


    if (
        "18 aya kadar"
        not in text
        and
        "maksimum vadesi 18 aydir"
        not in text
    ):

        raise RuntimeError(
            "Official 18-month maturity "
            "semantic check failed."
        )


    pricing_match = re.search(
        (
            r"\b18\s+"
            r"%?\s*"
            r"([0-9]+(?:[.,][0-9]+)?)"
            r"\s+%?\s*"
            r"([0-9]+(?:[.,][0-9]+)?)"
            r"\s+%?\s*"
            r"([0-9]+(?:[.,][0-9]+)?)"
            r"\s+%?\s*"
            r"([0-9]+(?:[.,][0-9]+)?)"
        ),
        text,
    )

    if pricing_match is None:

        raise RuntimeError(
            "Official 18-month pricing row "
            "could not be parsed."
        )


    published_profit_rate = parse_rate(
        pricing_match.group(1)
    )

    published_allocation_fee_rate = (
        parse_rate(
            pricing_match.group(2)
        )
    )

    published_monthly_cost_rate = (
        parse_rate(
            pricing_match.group(3)
        )
    )

    published_annual_cost_rate = (
        parse_rate(
            pricing_match.group(4)
        )
    )


    if (
        product_minimum
        > int(
            BENCHMARK_AMOUNT
        )
        or
        product_maximum
        < int(
            BENCHMARK_AMOUNT
        )
    ):

        raise RuntimeError(
            "50000 TL benchmark is outside "
            "the official product limit."
        )


    if (
        published_allocation_fee_rate
        != Decimal("0")
    ):

        raise RuntimeError(
            "Allocation fee rate is no longer "
            "zero. Fee amount semantics require "
            "manual review before sync."
        )


    return {
        "product_minimum":
            product_minimum,

        "product_maximum":
            product_maximum,

        "published_profit_rate":
            published_profit_rate,

        "published_allocation_fee_rate":
            published_allocation_fee_rate,

        "published_monthly_cost_rate":
            published_monthly_cost_rate,

        "published_annual_cost_rate":
            published_annual_cost_rate,

        "source_url":
            PRODUCT_URL,
    }


def find_calculation_section(
    root: Any,
) -> dict[str, Any]:

    found: list[dict[str, Any]] = []


    def walk(
        value: Any,
    ) -> None:

        if isinstance(
            value,
            dict,
        ):

            if (
                value.get(
                    "className"
                )
                == "HF.CalculationSection"
            ):

                found.append(
                    value
                )

            for child in value.values():
                walk(
                    child
                )

        elif isinstance(
            value,
            list,
        ):

            for child in value:
                walk(
                    child
                )


    walk(
        root
    )


    if len(found) != 1:

        raise RuntimeError(
            "Expected exactly one "
            "HF.CalculationSection; "
            f"found={len(found)}"
        )


    return found[0]


def extract_calculator_contract(
    session: requests.Session,
) -> dict[str, Any]:

    html = fetch_text(
        session,
        HOME_URL,
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    next_data_tag = soup.find(
        "script",
        id="__NEXT_DATA__",
    )

    if next_data_tag is None:

        raise RuntimeError(
            "__NEXT_DATA__ not found."
        )


    root = json.loads(
        next_data_tag.string
    )

    section = find_calculation_section(
        root
    )


    matches: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ] = []


    def walk_groups(
        value: Any,
    ) -> None:

        if isinstance(
            value,
            dict,
        ):

            accounts = value.get(
                "accountType"
            )

            if isinstance(
                accounts,
                list,
            ):

                for account in accounts:

                    if (
                        isinstance(
                            account,
                            dict,
                        )
                        and
                        account.get(
                            "label"
                        )
                        == PRODUCT_NAME
                    ):

                        matches.append(
                            (
                                value,
                                account,
                            )
                        )

            for child in value.values():
                walk_groups(
                    child
                )

        elif isinstance(
            value,
            list,
        ):

            for child in value:
                walk_groups(
                    child
                )


    walk_groups(
        section
    )


    if len(matches) != 1:

        raise RuntimeError(
            "Expected exactly one "
            "Bana Bunu Al calculator entry; "
            f"found={len(matches)}"
        )


    group, product = matches[0]


    group_label = normalize_source_text(
        str(
            group.get(
                "label"
            )
            or ""
        )
    )

    if (
        "kredi turu seciniz"
        not in group_label
    ):

        raise RuntimeError(
            "Calculator group semantic "
            "check failed."
        )


    product_type_id = product.get(
        "productTypeId"
    )

    calculation_type_id = product.get(
        "value"
    )


    if (
        product_type_id is None
        or calculation_type_id is None
    ):

        raise RuntimeError(
            "Calculator product identifiers "
            "are missing."
        )


    amount_settings: list[
        dict[str, Any]
    ] = []

    maturity_settings: list[
        dict[str, Any]
    ] = []


    def scan_settings(
        value: Any,
    ) -> None:

        if isinstance(
            value,
            dict,
        ):

            class_name = value.get(
                "className"
            )

            if (
                class_name
                == "HF.DepositAmountItem"
            ):

                amount_settings.append(
                    value
                )

            if (
                class_name
                == "HF.InputMaturityTypeItem"
            ):

                maturity_settings.append(
                    value
                )

            for child in value.values():
                scan_settings(
                    child
                )

        elif isinstance(
            value,
            list,
        ):

            for child in value:
                scan_settings(
                    child
                )


    scan_settings(
        product
    )


    if len(amount_settings) != 1:

        raise RuntimeError(
            "Expected one calculator amount "
            "setting."
        )


    if len(maturity_settings) != 1:

        raise RuntimeError(
            "Expected one calculator maturity "
            "setting."
        )


    amount_setting = amount_settings[0]

    maturity_setting = (
        maturity_settings[0]
    )


    calculator_minimum = int(
        amount_setting.get(
            "min"
        )
    )

    calculator_maximum = int(
        amount_setting.get(
            "max"
        )
    )


    if not (
        calculator_minimum
        <= int(
            BENCHMARK_AMOUNT
        )
        <= calculator_maximum
    ):

        raise RuntimeError(
            "50000 TL benchmark is outside "
            "the live calculator range."
        )


    valid_months: list[int] = []


    for maturity_type in (
        maturity_setting.get(
            "maturityType"
        )
        or []
    ):

        if not isinstance(
            maturity_type,
            dict,
        ):

            continue


        children = maturity_type.get(
            "child"
        )


        if isinstance(
            children,
            list,
        ):

            for child in children:

                if not isinstance(
                    child,
                    dict,
                ):

                    continue

                try:

                    valid_months.append(
                        int(
                            child.get(
                                "value"
                            )
                        )
                    )

                except Exception:

                    pass

        else:

            try:

                minimum = int(
                    maturity_type.get(
                        "min"
                    )
                )

                maximum = int(
                    maturity_type.get(
                        "max"
                    )
                )

                valid_months.extend(
                    range(
                        minimum,
                        maximum + 1,
                    )
                )

            except Exception:

                pass


    valid_months = sorted(
        set(
            valid_months
        )
    )


    if (
        BENCHMARK_MONTHS
        not in valid_months
    ):

        raise RuntimeError(
            "18-month benchmark is not "
            "exposed by official calculator."
        )


    return {
        "product_type_id":
            str(
                product_type_id
            ),

        "calculation_type_id":
            str(
                calculation_type_id
            ),

        "calculator_minimum":
            calculator_minimum,

        "calculator_maximum":
            calculator_maximum,

        "valid_months":
            valid_months,

        "button_url":
            product.get(
                "buttonUrl"
            ),

        "button_text":
            product.get(
                "buttonText"
            ),

        "note":
            product.get(
                "note"
            ),
    }


def call_live_calculator(
    session: requests.Session,
    *,
    contract: dict[str, Any],
    published_profit_rate: Decimal,
) -> dict[str, Any]:

    request_body = {
        "productTypeId":
            contract[
                "product_type_id"
            ],

        "loanMaturity":
            str(
                BENCHMARK_MONTHS
            ),

        "calculationTypeId":
            contract[
                "calculation_type_id"
            ],

        "loanAmount":
            int(
                BENCHMARK_AMOUNT
            ),

        "customRate":
            0,
    }


    response = session.post(
        CALCULATE_URL,
        json=request_body,
        headers={
            **HEADERS,
            "Accept":
                "application/json",
            "Content-Type":
                "application/json",
            "Origin":
                HOME_URL.rstrip(
                    "/"
                ),
            "Referer":
                HOME_URL,
        },
        timeout=30,
    )


    if response.status_code != 200:

        raise RuntimeError(
            "Hayat Finans calculator HTTP "
            f"{response.status_code}: "
            f"{response.text[:1000]}"
        )


    payload = response.json()


    if (
        payload.get(
            "isSuccessful"
        )
        is not True
    ):

        raise RuntimeError(
            "Hayat Finans calculator returned "
            "isSuccessful != true."
        )


    data = payload.get(
        "data"
    )


    if not isinstance(
        data,
        dict,
    ):

        raise RuntimeError(
            "Calculator data object missing."
        )


    monthly_installment = (
        decimal_value(
            data.get(
                "amount"
            )
        )
    )

    total_repayment = (
        decimal_value(
            data.get(
                "totalInstallmentAmount"
            )
        )
    )

    monthly_profit_rate = (
        decimal_value(
            data.get(
                "monthlyProfitRate"
            )
        )
    )

    annual_simple_profit_rate = (
        decimal_value(
            data.get(
                "annualSimpleProfitRate"
            )
        )
    )


    installments = (
        data.get(
            "installmentList"
        )
        or []
    )


    if (
        len(
            installments
        )
        != BENCHMARK_MONTHS
    ):

        raise RuntimeError(
            "Installment count mismatch: "
            f"{len(installments)} != "
            f"{BENCHMARK_MONTHS}"
        )


    row_sum = sum(
        (
            decimal_value(
                row.get(
                    "amount"
                )
            )
            for row in installments
        ),
        Decimal("0"),
    )


    row_sum_delta = abs(
        row_sum
        - total_repayment
    )


    if (
        row_sum_delta
        > Decimal("1.00")
    ):

        raise RuntimeError(
            "Installment row sum does not "
            "match official total."
        )


    first_amount = decimal_value(
        installments[0].get(
            "amount"
        )
    )


    if (
        abs(
            first_amount
            - monthly_installment
        )
        > Decimal("0.01")
    ):

        raise RuntimeError(
            "First installment does not "
            "match calculator amount field."
        )


    final_remaining = decimal_value(
        installments[-1].get(
            "remainingPrincipalAmount"
        )
    )


    if (
        abs(
            final_remaining
        )
        > Decimal("0.01")
    ):

        raise RuntimeError(
            "Final remaining principal "
            "is not zero."
        )


    principal_sum = sum(
        (
            decimal_value(
                row.get(
                    "principalAmount"
                )
            )
            for row in installments
        ),
        Decimal("0"),
    )


    if (
        abs(
            principal_sum
            - BENCHMARK_AMOUNT
        )
        > Decimal("1.00")
    ):

        raise RuntimeError(
            "Principal row sum does not "
            "match benchmark amount."
        )


    if (
        abs(
            monthly_profit_rate
            - published_profit_rate
        )
        > Decimal("0.0001")
    ):

        raise RuntimeError(
            "Live calculator profit rate "
            "does not match official "
            "18-month pricing table."
        )


    expected_annual_simple = (
        monthly_profit_rate
        * Decimal("12")
    )


    if (
        abs(
            annual_simple_profit_rate
            - expected_annual_simple
        )
        > Decimal("0.01")
    ):

        raise RuntimeError(
            "annualSimpleProfitRate semantic "
            "check failed."
        )


    return {
        "request_body":
            request_body,

        "response_payload":
            payload,

        "monthly_installment":
            monthly_installment,

        "total_repayment":
            total_repayment,

        "monthly_profit_rate":
            monthly_profit_rate,

        "annual_simple_profit_rate":
            annual_simple_profit_rate,

        "row_sum":
            row_sum,

        "row_sum_delta":
            row_sum_delta,

        "principal_sum":
            principal_sum,
    }


def verify_canonical_limits(
    conn,
) -> dict[str, Any]:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                minimum_financing_amount,
                maximum_financing_amount,
                maximum_maturity_months
            FROM bansa.standard_products
            WHERE id = %s
              AND is_current = TRUE
            """,
            (
                PRODUCT_ID,
            ),
        )

        row = cur.fetchone()


    if row is None:

        raise RuntimeError(
            "Canonical product 54 not found."
        )


    minimum_amount = decimal_value(
        row[0]
    )

    maximum_amount = decimal_value(
        row[1]
    )

    maximum_maturity = int(
        row[2]
    )


    if (
        minimum_amount
        != Decimal("500")
    ):

        raise RuntimeError(
            "Canonical minimum amount "
            "changed from 500 TL."
        )


    if (
        maximum_amount
        != BENCHMARK_AMOUNT
    ):

        raise RuntimeError(
            "Canonical maximum financing "
            "amount is no longer 50000 TL."
        )


    if (
        maximum_maturity
        != BENCHMARK_MONTHS
    ):

        raise RuntimeError(
            "Canonical maximum maturity "
            "is no longer 18 months."
        )


    return {
        "minimum_financing_amount":
            minimum_amount,

        "maximum_financing_amount":
            maximum_amount,

        "maximum_maturity_months":
            maximum_maturity,
    }


def verify_latest_after_write(
    conn,
    *,
    expected_rate: Decimal,
    expected_installment: Decimal,
    expected_total: Decimal,
) -> dict[str, Any]:

    latest = get_latest_scenario(
        conn,
        product_id=PRODUCT_ID,
        scenario_key=SCENARIO_KEY,
        input_variant=INPUT_VARIANT,
    )


    if latest is None:

        raise RuntimeError(
            "Latest scenario not found "
            "after insert."
        )


    checks = {
        "product_id":
            PRODUCT_ID,

        "input_maturity_months":
            BENCHMARK_MONTHS,

        "scenario_status":
            "verified",

        "source_kind":
            "official_live_calculator",
    }


    for key, expected in checks.items():

        if latest.get(
            key
        ) != expected:

            raise RuntimeError(
                f"Latest scenario mismatch "
                f"for {key}: "
                f"{latest.get(key)!r} != "
                f"{expected!r}"
            )


    decimal_checks = {
        "input_amount":
            BENCHMARK_AMOUNT,

        "profit_share_rate":
            expected_rate,

        "monthly_installment":
            expected_installment,

        "total_repayment":
            expected_total,

        "allocation_fee":
            Decimal("0"),

        "total_fees":
            Decimal("0"),
    }


    for key, expected in (
        decimal_checks.items()
    ):

        actual = latest.get(
            key
        )

        if actual is None:

            raise RuntimeError(
                f"Latest scenario missing {key}."
            )

        if (
            decimal_value(
                actual
            )
            != expected
        ):

            raise RuntimeError(
                f"Latest scenario mismatch "
                f"for {key}: "
                f"{actual!r} != "
                f"{expected!r}"
            )


    for key in (
        "monthly_cost_rate",
        "annual_cost_rate",
        "effective_annual_profit_rate",
    ):

        if (
            latest.get(
                key
            )
            is not None
        ):

            raise RuntimeError(
                f"{key} must remain NULL."
            )


    return latest


def run(
    *,
    write: bool,
) -> None:

    banner(
        "HAYAT FINANS - LIVE FINANCE SCENARIO SYNC"
    )

    print(
        "MODE =",
        (
            "WRITE"
            if write
            else "READ ONLY"
        ),
    )


    session = requests.Session()

    session.headers.update(
        HEADERS
    )


    product_semantics = (
        extract_product_page_semantics(
            session
        )
    )


    print(
        "OFFICIAL PRODUCT SOURCE SEMANTICS = PASS"
    )

    print(
        "PRODUCT LIMIT =",
        product_semantics[
            "product_minimum"
        ],
        "-",
        product_semantics[
            "product_maximum"
        ],
        "TL",
    )

    print(
        "PUBLISHED 18M PROFIT RATE =",
        product_semantics[
            "published_profit_rate"
        ],
    )

    print(
        "PUBLISHED ALLOCATION FEE RATE =",
        product_semantics[
            "published_allocation_fee_rate"
        ],
    )


    contract = (
        extract_calculator_contract(
            session
        )
    )


    print(
        "OFFICIAL CALCULATOR CONTRACT = PASS"
    )

    print(
        "PRODUCT TYPE ID =",
        contract[
            "product_type_id"
        ],
    )

    print(
        "CALCULATION TYPE ID =",
        contract[
            "calculation_type_id"
        ],
    )

    print(
        "CALCULATOR RANGE =",
        contract[
            "calculator_minimum"
        ],
        "-",
        contract[
            "calculator_maximum"
        ],
        "TL",
    )

    print(
        "BENCHMARK =",
        int(
            BENCHMARK_AMOUNT
        ),
        "TL /",
        BENCHMARK_MONTHS,
        "ay",
    )


    live = call_live_calculator(
        session,
        contract=contract,
        published_profit_rate=(
            product_semantics[
                "published_profit_rate"
            ]
        ),
    )


    print(
        "LIVE CALCULATOR VALIDATION = PASS"
    )

    print(
        "MONTHLY PROFIT RATE =",
        live[
            "monthly_profit_rate"
        ],
    )

    print(
        "MONTHLY INSTALLMENT =",
        live[
            "monthly_installment"
        ],
    )

    print(
        "TOTAL REPAYMENT =",
        live[
            "total_repayment"
        ],
    )

    print(
        "INSTALLMENT ROW SUM =",
        live[
            "row_sum"
        ],
    )

    print(
        "ANNUAL SIMPLE PROFIT RATE RAW =",
        live[
            "annual_simple_profit_rate"
        ],
    )


    conn = connect_postgres()


    try:

        before = canonical_snapshot(
            conn,
            [
                PRODUCT_ID,
            ],
        )


        identity = assert_product_identity(
            conn,
            product_id=PRODUCT_ID,
            bank_name=BANK_NAME,
            product_name=PRODUCT_NAME,
            family_key=FAMILY_KEY,
            scope=SCOPE,
        )


        print(
            "DATABASE PRODUCT IDENTITY = PASS"
        )

        print(
            "PRODUCT ID =",
            PRODUCT_ID,
        )


        canonical_limits = (
            verify_canonical_limits(
                conn
            )
        )


        print(
            "CANONICAL PRODUCT LIMITS = PASS"
        )


        input_metadata = {
            "benchmark_policy":
                "product_safe_maximum",

            "product_page_url":
                PRODUCT_URL,

            "calculator_page_url":
                HOME_URL,

            "calculator_api_url":
                CALCULATE_URL,

            "product_type_id":
                contract[
                    "product_type_id"
                ],

            "calculation_type_id":
                contract[
                    "calculation_type_id"
                ],

            "calculator_minimum":
                contract[
                    "calculator_minimum"
                ],

            "calculator_maximum":
                contract[
                    "calculator_maximum"
                ],

            "calculator_valid_months":
                contract[
                    "valid_months"
                ],

            "official_product_minimum":
                product_semantics[
                    "product_minimum"
                ],

            "official_product_maximum":
                product_semantics[
                    "product_maximum"
                ],

            "canonical_minimum":
                str(
                    canonical_limits[
                        "minimum_financing_amount"
                    ]
                ),

            "canonical_maximum":
                str(
                    canonical_limits[
                        "maximum_financing_amount"
                    ]
                ),

            "canonical_maximum_maturity":
                canonical_limits[
                    "maximum_maturity_months"
                ],
        }


        raw_output = {
            "request":
                live[
                    "request_body"
                ],

            "response":
                live[
                    "response_payload"
                ],

            "official_product_pricing":
                {
                    "maturity_months":
                        18,

                    "profit_share_rate":
                        float(
                            product_semantics[
                                "published_profit_rate"
                            ]
                        ),

                    "allocation_fee_rate":
                        float(
                            product_semantics[
                                "published_allocation_fee_rate"
                            ]
                        ),

                    "monthly_total_cost_rate":
                        float(
                            product_semantics[
                                "published_monthly_cost_rate"
                            ]
                        ),

                    "annual_total_cost_rate":
                        float(
                            product_semantics[
                                "published_annual_cost_rate"
                            ]
                        ),

                    "cost_table_basis_note":
                        (
                            "Published product-page cost "
                            "rates belong to the bank's "
                            "separate example cost table "
                            "and are not copied into this "
                            "50000 TL live scenario."
                        ),
                },

            "validation":
                {
                    "installment_row_sum":
                        str(
                            live[
                                "row_sum"
                            ]
                        ),

                    "row_sum_delta":
                        str(
                            live[
                                "row_sum_delta"
                            ]
                        ),

                    "principal_sum":
                        str(
                            live[
                                "principal_sum"
                            ]
                        ),
                },

            "semantics":
                {
                    "total_repayment":
                        (
                            "Official calculator "
                            "totalInstallmentAmount."
                        ),

                    "annual_simple_profit_rate":
                        (
                            "Stored as raw evidence only; "
                            "not mapped to annual_cost_rate "
                            "or effective annual profit rate."
                        ),

                    "allocation_fee":
                        (
                            "Official 18-month product "
                            "pricing table publishes "
                            "allocation fee rate as zero."
                        ),
                },

            "annual_simple_profit_rate":
                str(
                    live[
                        "annual_simple_profit_rate"
                    ]
                ),
        }


        if not write:

            after = canonical_snapshot(
                conn,
                [
                    PRODUCT_ID,
                ],
            )

            assert_canonical_unchanged(
                before,
                after,
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
                "CANONICAL STANDARD_PRODUCTS "
                "DEGISTIRILMEDI"
            )

            return


        backup_path = backup_scenarios(
            conn,
            bank_slug=BANK_SLUG,
            product_ids=[
                PRODUCT_ID,
            ],
        )


        print(
            "BACKUP =",
            backup_path,
        )


        inserted_id = insert_scenario(
            conn,
            product_id=PRODUCT_ID,
            scenario_key=SCENARIO_KEY,
            scenario_type=SCENARIO_TYPE,
            input_amount=BENCHMARK_AMOUNT,
            input_maturity_months=(
                BENCHMARK_MONTHS
            ),
            input_variant=INPUT_VARIANT,
            input_metadata=input_metadata,
            profit_share_rate=(
                live[
                    "monthly_profit_rate"
                ]
            ),
            monthly_installment=(
                live[
                    "monthly_installment"
                ]
            ),
            total_repayment=(
                live[
                    "total_repayment"
                ]
            ),
            allocation_fee=Decimal(
                "0"
            ),
            mortgage_fee=None,
            appraisal_fee=None,
            total_fees=Decimal(
                "0"
            ),
            monthly_cost_rate=None,
            annual_cost_rate=None,
            effective_annual_profit_rate=None,
            scenario_status="verified",
            source_kind=(
                "official_live_calculator"
            ),
            source_url=HOME_URL,
            source_note=(
                "Hayat Finans official live "
                "calculator snapshot. Product "
                "page limit and 18-month pricing "
                "were verified separately. "
                "annualSimpleProfitRate is kept "
                "only in raw_output."
            ),
            raw_output=raw_output,
            checked_at=utc_now(),
        )


        print(
            "INSERTED SCENARIO ID =",
            inserted_id,
        )


        verify_latest_after_write(
            conn,
            expected_rate=(
                live[
                    "monthly_profit_rate"
                ]
            ),
            expected_installment=(
                live[
                    "monthly_installment"
                ]
            ),
            expected_total=(
                live[
                    "total_repayment"
                ]
            ),
        )


        print(
            "LATEST VIEW VALIDATION = PASS"
        )


        after = canonical_snapshot(
            conn,
            [
                PRODUCT_ID,
            ],
        )


        assert_canonical_unchanged(
            before,
            after,
        )


        print(
            "CANONICAL SNAPSHOT = PASS"
        )


        conn.commit()


        print()
        print(
            "WRITE PASS"
        )

        print(
            "CANONICAL STANDARD_PRODUCTS "
            "DEGISTIRILMEDI"
        )


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Insert the verified live scenario "
            "into PostgreSQL."
        ),
    )

    args = parser.parse_args()

    run(
        write=args.write,
    )


if __name__ == "__main__":
    main()
