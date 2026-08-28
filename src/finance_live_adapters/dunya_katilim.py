# FINANCE_LIVE_ADAPTER_DUNYA_HOUSING_V2_1

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import json
import requests
from bs4 import BeautifulSoup

from src.finance_live_runtime import live_http_timeout

from src.finance_live_contract import (
    FinanceLiveAdapter,
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)

from src.finance_runtime_repository import (
    get_standard_products,
)


BANK_NAME = (
    "D\u00fcnya Kat\u0131l\u0131m"
)

PRODUCT_ID = 3

FAMILY_KEY = (
    "konut_finansmani"
)

PAGE_URL = (
    "https://dunyakatilim.com.tr/"
    "kendim-icin/finansmanlar/"
    "konut-finansmanlari/"
    "konut-finansmani"
)

HOME_URL = "https://dunyakatilim.com.tr/"
PAGE_URLS = (PAGE_URL, HOME_URL)

BASE_URL = (
    "https://dunyakatilim.com.tr"
)

INIT_URL = (
    BASE_URL
    + "/LoanInstallmentValues?lang=tr"
)

CALC_URL = (
    BASE_URL
    + "/LoanCheckRate?lang=tr"
)

HEADERS = {
    "User-Agent":
        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/151 Safari/537.36"
        ),

    "Accept-Language":
        "tr-TR,tr;q=0.9,en;q=0.5",
}

VARIANTS = {
    "yeni_konut":
        "KONUTTUKETICI",

    "2el_konut":
        "2ELKONUTTUKETICI",
}


def _verified_allocation_fee(
    financing_amount,
):

    """
    Resolve D?nya Kat?l?m Konut Finansman?
    allocation fee from verified runtime rules.

    Fail closed:
    - no hard-coded fee rate
    - no rule -> None
    - conflicting rules -> None
    """

    try:
        amount = Decimal(
            str(financing_amount)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None

    try:
        products = (
            get_standard_products()
        )

        rows = products[
            products["id"]
            .astype(int)
            .eq(PRODUCT_ID)
        ]

        if len(rows) != 1:
            return None

        raw_rules = (
            rows.iloc[0]
            .get(
                "finance_rules_json"
            )
        )

        if not isinstance(
            raw_rules,
            str,
        ):
            return None

        rules = json.loads(
            raw_rules
        )

    except Exception:
        return None

    fee_rules = (
        rules.get(
            "fee_rules"
        )
        if isinstance(
            rules,
            dict,
        )
        else None
    )

    if not isinstance(
        fee_rules,
        list,
    ):
        return None

    candidates = []

    for fee in fee_rules:

        if not isinstance(
            fee,
            dict,
        ):
            continue

        if (
            str(
                fee.get(
                    "fee_type"
                )
                or ""
            )
            .strip()
            .casefold()
            != "allocation"
        ):
            continue

        if bool(
            fee.get(
                "waived"
            )
        ):
            candidates.append(
                Decimal("0.00")
            )
            continue

        fixed_amount = (
            fee.get(
                "amount"
            )
        )

        rate = (
            fee.get(
                "rate"
            )
        )

        # Ambiguous rule:
        # both fixed amount and rate.
        if (
            fixed_amount is not None
            and
            rate is not None
        ):
            return None

        if fixed_amount is not None:

            try:
                value = Decimal(
                    str(
                        fixed_amount
                    )
                )
            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return None

            candidates.append(
                value.quantize(
                    Decimal("0.01")
                )
            )

            continue

        if rate is not None:

            try:
                percentage = Decimal(
                    str(
                        rate
                    )
                )
            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                return None

            if not (
                Decimal("0")
                <= percentage
                <= Decimal("100")
            ):
                return None

            value = (
                amount
                * percentage
                / Decimal("100")
            )

            candidates.append(
                value.quantize(
                    Decimal("0.01")
                )
            )

    unique = sorted(
        set(
            candidates
        )
    )

    if len(unique) != 1:
        return None

    return unique[0]


def _verified_minimum_fee_metadata(
    financing_amount,
):

    """
    Return only explicitly published MINIMUM
    housing fees from verified finance_rules_json.

    Exact allocation fee is calculated separately.
    Variable minimum fees are metadata only and
    must never populate LiveCalculationResult.total_fees.
    """

    try:
        amount = Decimal(
            str(financing_amount)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return {}

    try:
        products = (
            get_standard_products()
        )

        rows = products[
            products["id"]
            .astype(int)
            .eq(PRODUCT_ID)
        ]

        if len(rows) != 1:
            return {}

        raw_rules = (
            rows.iloc[0]
            .get(
                "finance_rules_json"
            )
        )

        if not isinstance(
            raw_rules,
            str,
        ):
            return {}

        rules = json.loads(
            raw_rules
        )

    except Exception:
        return {}

    fee_rules = (
        rules.get(
            "fee_rules"
        )
        if isinstance(
            rules,
            dict,
        )
        else None
    )

    if not isinstance(
        fee_rules,
        list,
    ):
        return {}

    wanted = {
        "appraisal":
            "minimum_appraisal_fee",

        "mortgage_establishment":
            "minimum_mortgage_establishment_fee",
    }

    collected = {
        key: []
        for key in wanted.values()
    }

    for fee in fee_rules:

        if not isinstance(
            fee,
            dict,
        ):
            continue

        fee_type = (
            str(
                fee.get(
                    "fee_type"
                )
                or ""
            )
            .strip()
            .casefold()
        )

        metadata_key = (
            wanted.get(
                fee_type
            )
        )

        if metadata_key is None:
            continue

        if bool(
            fee.get(
                "waived"
            )
        ):
            continue

        # This path is ONLY for values explicitly
        # described by the verified source as minimum.
        note = (
            str(
                fee.get(
                    "note"
                )
                or ""
            )
            .casefold()
        )

        if "asgari" not in note:
            continue

        raw_amount = (
            fee.get(
                "amount"
            )
        )

        if raw_amount is None:
            continue

        # Minimum rate-based values are deliberately
        # not inferred here.
        if (
            fee.get(
                "rate"
            )
            is not None
        ):
            continue

        try:
            value = Decimal(
                str(
                    raw_amount
                )
            )
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            continue

        if value < 0:
            continue

        collected[
            metadata_key
        ].append(
            value.quantize(
                Decimal("0.01")
            )
        )

    metadata = {}

    for key, values in collected.items():

        unique = sorted(
            set(
                values
            )
        )

        # Fail closed if conflicting verified
        # minimum values exist.
        if len(unique) != 1:
            continue

        metadata[key] = str(
            unique[0]
        )

    allocation_fee = (
        _verified_allocation_fee(
            amount
        )
    )

    appraisal = (
        metadata.get(
            "minimum_appraisal_fee"
        )
    )

    mortgage = (
        metadata.get(
            "minimum_mortgage_establishment_fee"
        )
    )

    # Produce a minimum total only when all three
    # required components are verified.
    if (
        allocation_fee is not None
        and appraisal is not None
        and mortgage is not None
    ):

        minimum_total = (
            allocation_fee
            + Decimal(
                appraisal
            )
            + Decimal(
                mortgage
            )
        )

        metadata[
            "minimum_verified_fees_total"
        ] = str(
            minimum_total.quantize(
                Decimal("0.01")
            )
        )

    return metadata


def norm(value):

    return (
        str(value or "")
        .strip()
        .casefold()
    )


def dec(value):

    if value is None:
        return None


    text = (
        str(value)
        .replace("\u00a0", "")
        .replace("TL", "")
        .replace("\u20ba", "")
        .replace("%", "")
        .replace(" ", "")
        .strip()
    )


    if not text:
        return None


    if (
        "."
        in text
        and
        ","
        in text
    ):

        text = (
            text
            .replace(".", "")
            .replace(",", ".")
        )

    elif "," in text:

        text = text.replace(
            ",",
            ".",
        )


    try:

        return Decimal(
            text
        )

    except InvalidOperation:

        return None


def _compact_tr(value):
    text = norm(value)
    table = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    })
    return " ".join(text.translate(table).replace("-", " ").replace("/", " ").split())


def _discover_housing_variant_codes(options):
    """Resolve current Dünya housing product codes from the official form.

    Product codes are bank implementation details and may change without the
    user-facing product name changing.  V49 therefore treats the option label
    as the stable semantic contract and only uses the historical codes as a
    compatibility fallback.
    """
    discovered = {}
    housing = []
    for code, label in (options or {}).items():
        t = _compact_tr(label)
        if "konut" not in t:
            continue
        housing.append((code, label, t))
        second = any(k in t for k in ("2 el", "2. el", "ikinci el", "ikinci"))
        if second and "2el_konut" not in discovered:
            discovered["2el_konut"] = code
        elif not second and "yeni_konut" not in discovered:
            discovered["yeni_konut"] = code

    # Historical codes are only a fallback when they are still present.
    for variant, old_code in VARIANTS.items():
        if variant not in discovered and old_code in (options or {}):
            discovered[variant] = old_code

    # Some revisions expose one generic "Konut Finansmanı" option and apply
    # the property/BSMV condition elsewhere.  In that case keep one canonical
    # standard code instead of declaring the calculator unavailable.
    if housing and not discovered:
        discovered["standard"] = housing[0][0]
    elif len(housing) == 1:
        discovered.setdefault("standard", housing[0][0])

    return discovered


class DunyaKatilimLiveAdapter(
    FinanceLiveAdapter,
):

    bank_name = BANK_NAME


    def can_handle(
        self,
        request,
    ):

        try:

            product_id = int(
                request.product_id
            )

        except Exception:

            return False


        return (
            product_id
            ==
            PRODUCT_ID

            and
            norm(
                request.bank_name
            )
            ==
            norm(
                BANK_NAME
            )

            and
            norm(
                request.family_key
            )
            ==
            FAMILY_KEY

            and
            "konut"
            in
            norm(
                request.product_name
            )

            and
            norm(
                request.variant
            )
            in {
                "",
                "standard",
                "yeni_konut",
                "2el_konut",
            }
        )


    def unverified(
        self,
        request,
        reason,
    ):

        return validate_live_result(
            LiveCalculationResult(
                request=request,

                status=(
                    LiveCalculationStatus
                    .UNVERIFIED
                ),

                reason=reason,
            )
        )


    def ineligible(
        self,
        request,
        reason,
    ):

        return validate_live_result(
            LiveCalculationResult(
                request=request,

                status=(
                    LiveCalculationStatus
                    .INELIGIBLE
                ),

                reason=reason,

                source_kind=(
                    "official_live_calculator_endpoint"
                ),

                source_url=PAGE_URL,

                checked_at=datetime.now(
                    timezone.utc
                ),
            )
        )


    def prepare(self):

        last_error = None

        for page_url in PAGE_URLS:
            session = requests.Session()
            session.headers.update(HEADERS)

            try:
                response = session.get(
                    page_url,
                    timeout=live_http_timeout(),
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # The official calculator has historically used loanForm /
                # loanSelect, but those DOM ids are presentation details.
                # Prefer them, then fall back to semantic form/select lookup.
                form = soup.find("form", id="loanForm")
                if form is None:
                    candidate_select = (
                        soup.find("select", id="loanSelect")
                        or soup.find("select", attrs={"name": "productCode"})
                        or soup.find("select", attrs={"name": "loanSelect"})
                    )
                    form = candidate_select.find_parent("form") if candidate_select else None
                if form is None:
                    # Last resort: find a form whose select options contain a
                    # housing product.
                    for candidate in soup.find_all("form"):
                        labels = " ".join(
                            opt.get_text(" ", strip=True)
                            for opt in candidate.find_all("option")
                        )
                        if "konut" in _compact_tr(labels):
                            form = candidate
                            break
                if form is None:
                    raise RuntimeError("Dunya finance calculator form missing.")

                token_input = (
                    form.find("input", attrs={"name": "__RequestVerificationToken"})
                    or soup.find("input", attrs={"name": "__RequestVerificationToken"})
                )
                if token_input is None:
                    raise RuntimeError("Dunya antiforgery token missing.")
                token = str(token_input.get("value") or "").strip()
                if not token:
                    raise RuntimeError("Dunya antiforgery token empty.")

                select = (
                    form.find("select", id="loanSelect")
                    or form.find("select", attrs={"name": "productCode"})
                    or form.find("select", attrs={"name": "loanSelect"})
                )
                if select is None:
                    selects = form.find_all("select")
                    select = next(
                        (x for x in selects if "konut" in _compact_tr(
                            " ".join(o.get_text(" ", strip=True) for o in x.find_all("option"))
                        )),
                        None,
                    )
                if select is None:
                    raise RuntimeError("Dunya finance product select missing.")

                options = {}
                for option in select.find_all("option"):
                    code = str(option.get("value") or "").strip()
                    if code:
                        options[code] = option.get_text(" ", strip=True)

                variant_codes = _discover_housing_variant_codes(options)
                if not variant_codes:
                    raise RuntimeError("Dunya housing option could not be discovered from official form.")

                rate_checkbox = (
                    form.find("input", id="checkProfitRateCheckbox")
                    or soup.find("input", id="checkProfitRateCheckbox")
                )
                rate_input = (
                    form.find(id="checkProfitRateInput")
                    or soup.find(id="checkProfitRateInput")
                )
                user_selected = bool(rate_checkbox and rate_checkbox.has_attr("checked"))
                raw_user_rate = str(rate_input.get("value") or "") if rate_input else ""
                try:
                    user_rate = f"{float(raw_user_rate):.2f}".replace(".", ",")
                except Exception:
                    user_rate = "NaN"

                return {
                    "session": session,
                    "token": token,
                    "options": options,
                    "variant_codes": variant_codes,
                    "page_url": page_url,
                    "user_selected": user_selected,
                    "user_rate": user_rate,
                }

            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(
            "Dunya official calculator could not be prepared from product page or homepage: "
            + (f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error")
        )


    def calculate_variant(
        self,
        request,
        prepared,
        variant,
    ):

        variant_codes = prepared.get("variant_codes") or {}
        code = variant_codes.get(variant)
        if code is None and variant in {"yeni_konut", "2el_konut"}:
            code = variant_codes.get("standard")
        if code is None:
            raise RuntimeError("Dunya requested housing variant is not exposed by current official form.")

        name = prepared["options"][code]


        ajax_headers = {
            **HEADERS,

            "Referer":
                prepared.get("page_url") or PAGE_URL,

            "Origin":
                BASE_URL,

            "X-Requested-With":
                "XMLHttpRequest",
        }


        init_response = (
            prepared["session"]
            .post(
                INIT_URL,

                data={
                    "productCode":
                        code,

                    "__RequestVerificationToken":
                        prepared[
                            "token"
                        ],
                },

                headers=ajax_headers,

                timeout=live_http_timeout(),
            )
        )

        init_response.raise_for_status()

        init_data = (
            init_response.json()
        )


        if (
            not isinstance(
                init_data,
                dict,
            )
            or
            init_data.get(
                "result"
            )
            !=
            "SUCCESS"
        ):

            raise RuntimeError(
                "Dunya initialization failed."
            )


        min_amount = dec(
            init_data.get(
                "minAmount"
            )
        )

        max_amount = dec(
            init_data.get(
                "maxAmount"
            )
        )


        if (
            min_amount is None
            or
            max_amount is None
        ):

            raise RuntimeError(
                "Dunya amount limits missing."
            )


        min_month = int(
            init_data.get(
                "minInstallment"
            )
        )

        max_month = int(
            init_data.get(
                "maxInstallment"
            )
        )


        if not (
            min_amount
            <=
            request.amount
            <=
            max_amount
        ):

            return self.ineligible(
                request,
                (
                    "Requested amount is outside "
                    "the official Dunya "
                    "calculator range."
                ),
            )


        if not (
            min_month
            <=
            int(
                request.maturity_months
            )
            <=
            max_month
        ):

            return self.ineligible(
                request,
                (
                    "Requested maturity is outside "
                    "the official Dunya "
                    "calculator range."
                ),
            )


        if (
            request.amount
            !=
            request.amount.to_integral_value()
        ):

            return self.unverified(
                request,
                (
                    "Dunya calculator browser "
                    "contract requires a whole-TL "
                    "financing amount."
                ),
            )


        amount_text = (
            f"{int(request.amount):,}"
            .replace(",", ".")
        )


        calc_response = (
            prepared["session"]
            .post(
                CALC_URL,

                data={
                    "productName":
                        name,

                    "productCode":
                        code,

                    "productCategory":
                        str(
                            init_data.get(
                                "category"
                            )
                            or ""
                        ),

                    "amount":
                        amount_text,

                    "installmentCount":
                        str(
                            int(
                                request
                                .maturity_months
                            )
                        ),

                    "userRate":
                        prepared[
                            "user_rate"
                        ],

                    "userSelected":
                        (
                            "true"
                            if
                            prepared[
                                "user_selected"
                            ]
                            else
                            "false"
                        ),

                    "__RequestVerificationToken":
                        prepared[
                            "token"
                        ],
                },

                headers=ajax_headers,

                timeout=live_http_timeout(),
            )
        )

        calc_response.raise_for_status()

        data = calc_response.json()


        if (
            not isinstance(
                data,
                dict,
            )
            or
            data.get(
                "result"
            )
            !=
            "SUCCESS"
        ):

            raise RuntimeError(
                "Dunya calculation failed: "
                + str(
                    data.get(
                        "message"
                    )
                    if isinstance(
                        data,
                        dict,
                    )
                    else data
                )
            )


        rate = dec(
            data.get(
                "rate"
            )
        )

        monthly = dec(
            data.get(
                "monthlyInterest"
            )
        )

        total = dec(
            data.get(
                "totalPayment"
            )
        )


        if any(
            value is None
            or
            value <= 0

            for value in (
                rate,
                monthly,
                total,
            )
        ):

            raise RuntimeError(
                "Dunya numeric verification failed."
            )


        payment_plan_html = str(
            data.get(
                "paymentPlanHTML"
            )
            or ""
        )


        if not payment_plan_html.strip():

            raise RuntimeError(
                "Dunya payment plan missing."
            )


        return validate_live_result(
            LiveCalculationResult(
                request=request,

                status=(
                    LiveCalculationStatus
                    .VERIFIED
                ),

                calculated_amount=(
                    request.amount
                ),

                calculated_maturity_months=(
                    int(
                        request.maturity_months
                    )
                ),

                profit_share_rate=rate,

                monthly_installment=monthly,

                total_repayment=total,

                allocation_fee=(
                    _verified_allocation_fee(
                        request.amount
                    )
                ),

                mortgage_fee=None,

                appraisal_fee=None,

                total_fees=None,

                source_kind=(
                    "official_live_calculator_endpoint"
                ),

                source_url=(prepared.get("page_url") or PAGE_URL),

                source_note=(
                    "Dunya Katilim official financial calculator; product code discovered from the current official form."
                ),

                checked_at=datetime.now(
                    timezone.utc
                ),

                raw_output={
                    **(
                        _verified_minimum_fee_metadata(
                            request.amount
                        )
                    ),

                    "housing_variant":
                        variant,

                    "product_code":
                        code,

                    "product_category":
                        init_data.get(
                            "category"
                        ),

                    "payment_plan_html_length":
                        len(
                            payment_plan_html
                        ),
                },
            )
        )


    @staticmethod
    def signature(
        result,
    ):

        return (
            result.profit_share_rate,
            result.monthly_installment,
            result.total_repayment,
            result.allocation_fee,
            result.mortgage_fee,
            result.appraisal_fee,
            result.total_fees,
        )


    def calculate(
        self,
        request,
    ):

        if not self.can_handle(
            request
        ):

            return self.unverified(
                request,
                (
                    "Dunya housing adapter "
                    "identity guard rejected request."
                ),
            )


        try:

            prepared = (
                self.prepare()
            )

            variant = norm(
                request.variant
            )


            available = prepared.get("variant_codes") or {}

            if variant in {"yeni_konut", "2el_konut", "standard"}:
                chosen = variant
                if chosen not in available and available.get("standard"):
                    chosen = "standard"
                return self.calculate_variant(request, prepared, chosen)

            # When the current calculator exposes a single generic housing
            # option, calculate it directly rather than falsely reporting that
            # Dünya Katılım has no live calculator.
            if available.get("standard") and not (available.get("yeni_konut") or available.get("2el_konut")):
                return self.calculate_variant(request, prepared, "standard")

            variants = tuple(
                v for v in ("yeni_konut", "2el_konut")
                if available.get(v)
            )
            if not variants:
                return self.unverified(request, "Dunya official form exposed no usable housing variant.")


            results = [
                self.calculate_variant(
                    request,
                    prepared,
                    item,
                )

                for item in variants
            ]


            if not all(
                result.status == LiveCalculationStatus.VERIFIED
                for result in results
            ):
                return self.unverified(
                    request,
                    "Dunya housing condition(s) could not be verified live.",
                )

            if len(results) == 1:
                base = results[0]
                return validate_live_result(replace(
                    base, request=request,
                    source_note=(
                        "Dunya Katilim official calculator; current form exposed one canonical housing option and it was verified live."
                    ),
                ))


            signatures = {
                self.signature(
                    result
                )
                for result in results
            }


            if len(signatures) != 1:

                return self.unverified(
                    request,
                    (
                        "Dunya Yeni and 2.El "
                        "results differ; generic "
                        "numeric collapse was blocked."
                    ),
                )


            base = results[0]

            raw = dict(
                base.raw_output
            )

            raw[
                "collapsed_housing_variants"
            ] = list(
                variants
            )


            return validate_live_result(
                replace(
                    base,

                    request=request,

                    source_note=(
                        "Dunya Katilim official "
                        "calculator; Yeni and 2.El "
                        "were both verified live "
                        "and returned the same result."
                    ),

                    raw_output=raw,
                )
            )


        except Exception as exc:

            return self.unverified(
                request,
                (
                    "Dunya live housing "
                    "verification failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
