from __future__ import annotations

import argparse
import base64
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from .common import (
        assert_canonical_unchanged,
        assert_product_identity,
        backup_scenarios,
        canonical_snapshot,
        connect_postgres,
        get_latest_scenario,
        insert_scenario,
        normalize_text,
        utc_now,
    )
except ImportError:
    from common import (
        assert_canonical_unchanged,
        assert_product_identity,
        backup_scenarios,
        canonical_snapshot,
        connect_postgres,
        get_latest_scenario,
        insert_scenario,
        normalize_text,
        utc_now,
    )


BANK_NAME = "T.O.M. Kat\u0131l\u0131m"
BANK_SLUG = "tom_katilim"

PRODUCT_ID = 227
PRODUCT_NAME = "Taksitli Al\u0131\u015fveri\u015f Kredisi"
FAMILY_KEY = "alisveris_finansmani"
SCOPE = "bireysel"

PRODUCT_URL = (
    "https://tombank.com.tr/"
    "taksitle.html"
)

CALCULATOR_URL = (
    "https://www.tombank.com.tr/"
    "hesaplama-araclari.html"
)

CALCULATOR_JS_URL = (
    "https://www.tombank.com.tr/"
    "assets/js/calculation-tool-dynamic.js"
)

RATE_URL = (
    "https://webintegration.tombank.com.tr/"
    "webintegration/api/LoanCalculation/"
    "LoanRateList"
)

PLAN_URL = (
    "https://webintegration.tombank.com.tr/"
    "webintegration/api/LoanCalculation/"
    "GetLoanPayBackPlan"
)

PRODUCT_CODE = "TKTCDGRFNS"

SCENARIO_KEY = "benchmark_100000_24"
SCENARIO_TYPE = "live_calculator_snapshot"
INPUT_VARIANT = "standard"

BENCHMARK_AMOUNT = Decimal("100000")
BENCHMARK_MONTHS = 24

SCENARIO_STATUS = (
    "verified_live_calculator_direct_mapping"
)

SOURCE_KIND = (
    "official_live_calculator_endpoint"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language":
        "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def decimal_2(
    value: Decimal,
) -> Decimal:

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def parse_tr_decimal(
    value: Any,
) -> Decimal | None:

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = (
        text
        .replace("TL", "")
        .replace("\u20ba", "")
        .replace("%", "")
        .replace(" ", "")
    )

    if "," in text:
        text = (
            text
            .replace(".", "")
            .replace(",", ".")
        )

    try:
        return Decimal(text)

    except Exception:
        return None


def create_session() -> requests.Session:

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    return session


def get_text(
    session: requests.Session,
    url: str,
) -> str:

    response = session.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    # T.O.M. pages are UTF-8, but some responses do not
    # advertise the charset reliably. requests may otherwise
    # decode Turkish characters as mojibake (?..., ?...).
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


def verify_product_source(
    session: requests.Session,
) -> dict[str, Any]:

    html = get_text(
        session,
        PRODUCT_URL,
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    visible = " ".join(
        soup.stripped_strings
    )

    normalized = normalize_text(
        visible
    )

    required = [
        normalize_text(
            "Taksitli Al\u0131\u015fveri\u015f Kredisi"
        ),
        normalize_text(
            "Kredi Tahsis \u00dccreti"
        ),
    ]

    for phrase in required:

        if phrase not in normalized:
            raise RuntimeError(
                "Official product source semantic "
                f"check failed: {phrase!r}"
            )

    raw_lower = visible.casefold()

    fee_rate_match = re.search(
        r"%\s*0[\.,]5",
        raw_lower,
    )

    if not fee_rate_match:
        raise RuntimeError(
            "Official 0.5 percent allocation "
            "fee rule was not found."
        )

    bsmv_match = (
        re.search(
            r"%\s*15[^.\n]{0,120}bsmv",
            raw_lower,
            flags=re.I,
        )
        or
        re.search(
            r"bsmv[^.\n]{0,120}%\s*15",
            raw_lower,
            flags=re.I,
        )
    )

    if not bsmv_match:
        raise RuntimeError(
            "Official 15 percent BSMV rule "
            "was not found."
        )

    first_installment_text = normalize_text(
        "ilk taksit"
    )

    if (
        first_installment_text
        not in normalized
    ):
        raise RuntimeError(
            "Allocation fee first-installment "
            "semantic check failed."
        )

    return {
        "product_source_url":
            PRODUCT_URL,

        "allocation_fee_rate":
            "0.005",

        "allocation_fee_bsmv_rate":
            "0.15",

        "allocation_fee_semantics":
            (
                "Official product page states "
                "0.5 percent allocation fee "
                "with 15 percent BSMV included "
                "in the first installment."
            ),
    }


def discover_calculator_contract(
    session: requests.Session,
) -> dict[str, Any]:

    calculator_html = get_text(
        session,
        CALCULATOR_URL,
    )

    soup = BeautifulSoup(
        calculator_html,
        "html.parser",
    )

    select = soup.find(
        id="productSelection"
    )

    if select is None:
        raise RuntimeError(
            "Calculator productSelection missing."
        )

    product_codes = []

    for option in select.find_all(
        "option"
    ):

        code = str(
            option.get("value")
            or ""
        ).strip()

        if code:
            product_codes.append(
                code
            )

    if product_codes != [
        PRODUCT_CODE
    ]:
        raise RuntimeError(
            "Calculator product catalog changed: "
            f"{product_codes!r}"
        )

    calculator_visible = " ".join(
        soup.stripped_strings
    )

    calculator_normalized = normalize_text(
        calculator_visible
    )

    calculator_semantic = normalize_text(
        "Taksitli al\u0131\u015fveri\u015f kredisinde"
    )

    if (
        calculator_semantic
        not in calculator_normalized
    ):
        raise RuntimeError(
            "Calculator-to-product semantic "
            "mapping evidence changed."
        )

    js = get_text(
        session,
        CALCULATOR_JS_URL,
    )

    if RATE_URL not in js:
        raise RuntimeError(
            "LoanRateList endpoint changed."
        )

    if PLAN_URL not in js:
        raise RuntimeError(
            "GetLoanPayBackPlan endpoint changed."
        )

    rule_match = re.search(
        r"TKTCDGRFNS\s*:\s*\[(.*?)\]",
        js,
        flags=re.S,
    )

    if not rule_match:
        raise RuntimeError(
            "TKTCDGRFNS maturity rule missing."
        )

    rule_block = (
        rule_match.group(1)
    )

    rules = []

    for item in re.finditer(
        r"\{(.*?)\}",
        rule_block,
        flags=re.S,
    ):

        block = item.group(1)

        min_match = re.search(
            r"min\s*:\s*([0-9.]+)",
            block,
        )

        max_match = re.search(
            r"max\s*:\s*([0-9.]+)",
            block,
        )

        maturity_match = re.search(
            r"installment\s*:\s*(\d+)",
            block,
        )

        if not (
            min_match
            and max_match
            and maturity_match
        ):
            continue

        rules.append(
            {
                "min":
                    Decimal(
                        min_match.group(1)
                    ),

                "max":
                    Decimal(
                        max_match.group(1)
                    ),

                "installment":
                    int(
                        maturity_match.group(1)
                    ),
            }
        )

    if not rules:
        raise RuntimeError(
            "Frontend maturity rules could "
            "not be parsed."
        )

    benchmark_rule = None

    for rule in rules:

        if (
            rule["min"]
            <= BENCHMARK_AMOUNT
            <= rule["max"]
        ):
            benchmark_rule = rule
            break

    if benchmark_rule is None:
        raise RuntimeError(
            "Benchmark amount is outside "
            "frontend maturity rules."
        )

    if (
        benchmark_rule["installment"]
        != BENCHMARK_MONTHS
    ):
        raise RuntimeError(
            "Frontend benchmark maturity changed | "
            f"amount={BENCHMARK_AMOUNT} | "
            f"expected={BENCHMARK_MONTHS} | "
            f"actual={benchmark_rule['installment']}"
        )

    auth_match = re.search(
        r'btoa\(\s*"([^"]+)"\s*'
        r'\+\s*":"\s*\+\s*"([^"]+)"\s*\)',
        js,
    )

    if not auth_match:
        raise RuntimeError(
            "Public frontend authorization "
            "contract changed."
        )

    username = auth_match.group(1)
    password = auth_match.group(2)

    token = (
        "Basic "
        + base64.b64encode(
            (
                username
                + ":"
                + password
            ).encode(
                "utf-8"
            )
        ).decode(
            "ascii"
        )
    )

    return {
        "authorization":
            token,

        "rules":
            rules,

        "benchmark_rule":
            benchmark_rule,

        "calculator_product_codes":
            product_codes,

        "mapping_evidence":
            (
                "Official calculator contains a "
                "single product code and explicitly "
                "describes Taksitli Alisveris Kredisi "
                "fee semantics on the same calculator."
            ),
    }


def api_headers(
    authorization: str,
) -> dict[str, str]:

    return {
        **HEADERS,

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "Authorization":
            authorization,

        "Origin":
            "https://www.tombank.com.tr",

        "Referer":
            CALCULATOR_URL,
    }


def fetch_rate(
    session: requests.Session,
    authorization: str,
) -> tuple[Decimal, dict[str, Any]]:

    response = session.post(
        RATE_URL,
        headers=api_headers(
            authorization
        ),
        json={
            "ProductCode":
                PRODUCT_CODE,
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get(
        "Success"
    ):
        raise RuntimeError(
            "LoanRateList returned Success=False."
        )

    rates = (
        (
            payload.get("Data")
            or {}
        ).get("LoanRateList")
        or []
    )

    selected = None

    for item in rates:

        try:

            months = int(
                item.get(
                    "InstallmentsCount"
                )
            )

        except Exception:
            continue

        if (
            months
            == BENCHMARK_MONTHS
        ):
            selected = item
            break

    if selected is None:
        raise RuntimeError(
            "Official 24-month rate missing."
        )

    rate = parse_tr_decimal(
        selected.get(
            "LoanRate"
        )
    )

    if rate is None:
        raise RuntimeError(
            "Official rate could not be parsed."
        )

    return rate, {
        "rate_endpoint":
            RATE_URL,

        "rate_response":
            payload,

        "selected_rate_row":
            selected,
    }


def fetch_payment_plan(
    session: requests.Session,
    authorization: str,
    rate: Decimal,
) -> dict[str, Any]:

    response = session.post(
        PLAN_URL,
        headers=api_headers(
            authorization
        ),
        json={
            "CustomRate":
                float(rate),

            "FundingAmount":
                float(
                    BENCHMARK_AMOUNT
                ),

            "InstallmentCount":
                BENCHMARK_MONTHS,

            "IsTotalAmountByInstallmentAmount":
                False,

            "ProductCode":
                PRODUCT_CODE,
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get(
        "Success"
    ):
        raise RuntimeError(
            "GetLoanPayBackPlan returned "
            "Success=False."
        )

    data = (
        payload.get("Data")
        or {}
    )

    installments = (
        data.get(
            "installmentList"
        )
        or
        data.get(
            "InstallmentList"
        )
        or []
    )

    if (
        len(installments)
        != BENCHMARK_MONTHS
    ):
        raise RuntimeError(
            "Payment-plan installment count "
            "mismatch | "
            f"expected={BENCHMARK_MONTHS} | "
            f"actual={len(installments)}"
        )

    parsed_installments = []

    for index, item in enumerate(
        installments,
        1,
    ):

        if not isinstance(
            item,
            dict,
        ):
            raise RuntimeError(
                "Unexpected installment row type."
            )

        amount = parse_tr_decimal(
            item.get("Amount")
        )

        if amount is None:
            raise RuntimeError(
                "Installment amount parse failed | "
                f"row={index}"
            )

        parsed_installments.append(
            amount
        )

    monthly_rate = parse_tr_decimal(
        data.get(
            "MonthlyProfitRate"
        )
    )

    total = parse_tr_decimal(
        data.get(
            "TotalAmount"
        )
    )

    if monthly_rate is None:
        raise RuntimeError(
            "MonthlyProfitRate parse failed."
        )

    if total is None:
        raise RuntimeError(
            "TotalAmount parse failed."
        )

    if (
        abs(
            monthly_rate
            - rate
        )
        > Decimal("0.01")
    ):
        raise RuntimeError(
            "Rate mismatch between "
            "LoanRateList and payment plan."
        )

    row_sum = sum(
        parsed_installments,
        Decimal("0")
    )

    if (
        abs(
            row_sum
            - total
        )
        > Decimal("1.00")
    ):
        raise RuntimeError(
            "Payment plan sum mismatch | "
            f"rows={row_sum} | "
            f"total={total}"
        )

    return {
        "payload":
            payload,

        "data":
            data,

        "installments":
            installments,

        "parsed_installments":
            parsed_installments,

        "monthly_rate":
            monthly_rate,

        "monthly_installment":
            parsed_installments[0],

        "total_repayment":
            total,

        "payment_plan_sum":
            row_sum,
    }


def calculate_allocation_fee() -> Decimal:

    base_fee = (
        BENCHMARK_AMOUNT
        * Decimal("0.005")
    )

    bsmv = (
        base_fee
        * Decimal("0.15")
    )

    return decimal_2(
        base_fee
        + bsmv
    )


def build_scenario(
    *,
    rate: Decimal,
    payment: dict[str, Any],
    source_evidence: dict[str, Any],
    calculator_contract: dict[str, Any],
    rate_evidence: dict[str, Any],
) -> dict[str, Any]:

    allocation_fee = (
        calculate_allocation_fee()
    )

    checked_at = utc_now()

    return {
        "product_id":
            PRODUCT_ID,

        "scenario_key":
            SCENARIO_KEY,

        "scenario_type":
            SCENARIO_TYPE,

        "input_amount":
            BENCHMARK_AMOUNT,

        "input_maturity_months":
            BENCHMARK_MONTHS,

        "input_variant":
            INPUT_VARIANT,

        "input_metadata": {
            "benchmark":
                "100000_TL_24_month",

            "mapping_status":
                "verified_direct_mapping",

            "calculator_product_code":
                PRODUCT_CODE,

            "calculation_method":
                (
                    "Official TOM LoanRateList "
                    "followed by "
                    "GetLoanPayBackPlan"
                ),

            "frontend_maturity_rule":
                {
                    "min":
                        str(
                            calculator_contract[
                                "benchmark_rule"
                            ]["min"]
                        ),

                    "max":
                        str(
                            calculator_contract[
                                "benchmark_rule"
                            ]["max"]
                        ),

                    "installment":
                        calculator_contract[
                            "benchmark_rule"
                        ]["installment"],
                },

            "allocation_fee_rule":
                (
                    "0.5 percent fee plus "
                    "15 percent BSMV"
                ),
        },

        "profit_share_rate":
            rate,

        "monthly_installment":
            payment[
                "monthly_installment"
            ],

        "total_repayment":
            payment[
                "total_repayment"
            ],

        "allocation_fee":
            allocation_fee,

        "mortgage_fee":
            None,

        "appraisal_fee":
            None,

        "total_fees":
            allocation_fee,

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
            CALCULATOR_URL,

        "source_note":
            (
                "100,000 TL / 24 month benchmark. "
                "The official frontend maturity "
                "rule maps 100,000 TL to 24 months. "
                "The rate is obtained from "
                "LoanRateList and the payment plan "
                "from GetLoanPayBackPlan. "
                "The calculator page explicitly "
                "associates its financing tool with "
                "Taksitli Alisveris Kredisi. "
                "Allocation fee is stored separately "
                "and is not added to total_repayment."
            ),

        "raw_output": {
            "rate_endpoint":
                RATE_URL,

            "payment_plan_endpoint":
                PLAN_URL,

            "product_page":
                PRODUCT_URL,

            "calculator_page":
                CALCULATOR_URL,

            "calculator_product_code":
                PRODUCT_CODE,

            "selected_rate_row":
                rate_evidence[
                    "selected_rate_row"
                ],

            "payment_plan":
                payment[
                    "installments"
                ],

            "payment_plan_sum":
                str(
                    payment[
                        "payment_plan_sum"
                    ]
                ),

            "official_total":
                str(
                    payment[
                        "total_repayment"
                    ]
                ),

            "official_monthly_profit_rate":
                str(
                    payment[
                        "monthly_rate"
                    ]
                ),

            "allocation_fee":
                str(
                    allocation_fee
                ),

            "source_semantics":
                source_evidence,

            "mapping_evidence":
                calculator_contract[
                    "mapping_evidence"
                ],
        },

        "checked_at":
            checked_at,
    }


def validate_live_scenario(
    scenario: dict[str, Any],
) -> None:

    if (
        scenario[
            "input_amount"
        ]
        != BENCHMARK_AMOUNT
    ):
        raise RuntimeError(
            "Benchmark amount mismatch."
        )

    if (
        scenario[
            "input_maturity_months"
        ]
        != BENCHMARK_MONTHS
    ):
        raise RuntimeError(
            "Benchmark maturity mismatch."
        )

    for key in (
        "profit_share_rate",
        "monthly_installment",
        "total_repayment",
    ):

        value = scenario.get(
            key
        )

        if (
            value is None
            or Decimal(
                str(value)
            )
            <= 0
        ):
            raise RuntimeError(
                f"Invalid scenario field: {key}"
            )

    if (
        scenario[
            "allocation_fee"
        ]
        != Decimal("575.00")
    ):
        raise RuntimeError(
            "Allocation fee semantic "
            "calculation changed | "
            f"{scenario['allocation_fee']}"
        )


def verify_latest_after_write(
    conn,
    scenario: dict[str, Any],
) -> None:

    latest = get_latest_scenario(
        conn,
        product_id=
            PRODUCT_ID,
        scenario_key=
            SCENARIO_KEY,
        input_variant=
            INPUT_VARIANT,
    )

    if latest is None:
        raise RuntimeError(
            "Latest scenario not found "
            "after insert."
        )

    checks = {
        "product_id":
            PRODUCT_ID,

        "scenario_key":
            SCENARIO_KEY,

        "input_variant":
            INPUT_VARIANT,

        "input_maturity_months":
            BENCHMARK_MONTHS,
    }

    for key, expected in checks.items():

        actual = latest.get(
            key
        )

        if actual != expected:
            raise RuntimeError(
                "Latest scenario verification "
                f"failed | {key} | "
                f"expected={expected!r} | "
                f"actual={actual!r}"
            )

    decimal_checks = {
        "input_amount":
            scenario[
                "input_amount"
            ],

        "profit_share_rate":
            scenario[
                "profit_share_rate"
            ],

        "monthly_installment":
            scenario[
                "monthly_installment"
            ],

        "total_repayment":
            scenario[
                "total_repayment"
            ],

        "allocation_fee":
            scenario[
                "allocation_fee"
            ],

        "total_fees":
            scenario[
                "total_fees"
            ],
    }

    for key, expected in decimal_checks.items():

        actual = latest.get(
            key
        )

        if actual is None:
            raise RuntimeError(
                "Latest scenario field missing | "
                f"{key}"
            )

        if (
            Decimal(
                str(actual)
            )
            != Decimal(
                str(expected)
            )
        ):
            raise RuntimeError(
                "Latest scenario decimal "
                f"verification failed | {key} | "
                f"expected={expected} | "
                f"actual={actual}"
            )


def run(
    *,
    write: bool = False,
) -> dict[str, Any]:

    print("=" * 150)
    print(
        "T.O.M. KATILIM - LIVE FINANCE "
        "SCENARIO SYNC"
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

    source_evidence = (
        verify_product_source(
            session
        )
    )

    print(
        "OFFICIAL PRODUCT SOURCE "
        "SEMANTICS = PASS"
    )

    calculator_contract = (
        discover_calculator_contract(
            session
        )
    )

    print(
        "OFFICIAL CALCULATOR "
        "CONTRACT = PASS"
    )

    print(
        "PRODUCT CODE =",
        PRODUCT_CODE,
    )

    print(
        "FRONTEND BENCHMARK RULE = PASS"
    )

    print(
        "BENCHMARK = "
        "100000 TL / 24 ay"
    )

    print(
        "AUTH VALUE PRINTED = NO"
    )

    rate, rate_evidence = (
        fetch_rate(
            session,
            calculator_contract[
                "authorization"
            ],
        )
    )

    print(
        "OFFICIAL RATE =",
        rate,
    )

    payment = (
        fetch_payment_plan(
            session,
            calculator_contract[
                "authorization"
            ],
            rate,
        )
    )

    scenario = build_scenario(
        rate=rate,
        payment=payment,
        source_evidence=
            source_evidence,
        calculator_contract=
            calculator_contract,
        rate_evidence=
            rate_evidence,
    )

    validate_live_scenario(
        scenario
    )

    print(
        "LIVE CALCULATOR VALIDATION = PASS"
    )

    print(
        "MONTHLY INSTALLMENT =",
        scenario[
            "monthly_installment"
        ],
    )

    print(
        "TOTAL REPAYMENT =",
        scenario[
            "total_repayment"
        ],
    )

    print(
        "ALLOCATION FEE =",
        scenario[
            "allocation_fee"
        ],
    )

    conn = connect_postgres()

    try:

        identity = assert_product_identity(
            conn,
            product_id=
                PRODUCT_ID,
            bank_name=
                BANK_NAME,
            product_name=
                PRODUCT_NAME,
            family_key=
                FAMILY_KEY,
            scope=
                SCOPE,
        )

        print(
            "DATABASE PRODUCT IDENTITY = PASS"
        )

        print(
            "PRODUCT ID =",
            identity.get(
                "id",
                PRODUCT_ID,
            ),
        )

        before = canonical_snapshot(
            conn,
            [
                PRODUCT_ID
            ],
        )

        if not write:

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

            return scenario

        backup_path = backup_scenarios(
            conn,
            bank_slug=
                BANK_SLUG,
            product_ids=[
                PRODUCT_ID
            ],
        )

        print(
            "BACKUP =",
            backup_path,
        )

        inserted_id = insert_scenario(
            conn,
            **scenario,
        )

        print(
            "INSERTED SCENARIO ID =",
            inserted_id,
        )

        verify_latest_after_write(
            conn,
            scenario,
        )

        after = canonical_snapshot(
            conn,
            [
                PRODUCT_ID
            ],
        )

        assert_canonical_unchanged(
            before,
            after,
        )

        conn.commit()

        print(
            "LATEST VIEW VALIDATION = PASS"
        )

        print(
            "CANONICAL SNAPSHOT = PASS"
        )

        print()
        print(
            "WRITE PASS"
        )

        print(
            "CANONICAL STANDARD_PRODUCTS "
            "DEGISTIRILMEDI"
        )

        return scenario

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "T.O.M. Katilim official live "
            "finance scenario synchronizer."
        )
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Write verified scenario to "
            "PostgreSQL. Default is read-only."
        ),
    )

    args = parser.parse_args()

    run(
        write=args.write,
    )


if __name__ == "__main__":
    main()
