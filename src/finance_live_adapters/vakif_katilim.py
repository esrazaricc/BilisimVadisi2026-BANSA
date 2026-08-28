# FINANCE_LIVE_ADAPTER_VAKIF_V1

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

from decimal import (
    Decimal,
    InvalidOperation,
)

import re
import unicodedata
from typing import Any

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


BANK_NAME = (
    "Vak\u0131f Kat\u0131l\u0131m"
)

# Verified product-to-calculator mappings.  The actual official calculator
# option value is discovered from the live HTML by label; we do not guess or
# hard-code the bank's internal financingType code.
PRODUCT_MAPPINGS = {
    296: {
        "family_key": "konut_finansmani",
        "calculator_label_tokens": ("konut", "finansman"),
    },
    286: {
        "family_key": "arac_finansmani",
        "calculator_label_tokens": ("tasit", "finansman"),
    },
    318: {
        "family_key": "ihtiyac_finansmani",
        "calculator_label_tokens": ("ihtiyac", "finansman"),
    },
}

CALCULATE_TYPE = "1"

BASE_URL = (
    "https://www.vakifkatilim.com.tr"
)

CALCULATOR_PAGE = (
    BASE_URL
    + "/tr/yardimci-sayfalar/"
      "hesaplama-araclari/"
      "finansman-hesaplama"
)

CALCULATOR_ENDPOINT = (
    BASE_URL
    + "/plugins/FinancingComputationExecute"
)

PAYMENT_PLAN_ENDPOINT = (
    BASE_URL
    + "/plugins/InstallmentPayBack"
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
        "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
}

PLAN_TOLERANCE = Decimal("0.01")


def _normalized(
    value: Any,
) -> str:

    text = str(value or "").strip().casefold().replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _decimal_tr(
    value: Any,
) -> Decimal | None:

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

    if (
        not text
        or
        text == "-"
    ):
        return None

    if (
        "." in text
        and
        "," in text
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

    except (
        InvalidOperation,
        ValueError,
    ):

        return None


def _amount_text(
    amount: Decimal,
) -> str:

    if (
        amount
        ==
        amount.to_integral_value()
    ):

        return str(
            int(
                amount
            )
        )

    return format(
        amount,
        "f",
    )


class VakifKatilimLiveAdapter(
    FinanceLiveAdapter,
):

    bank_name = BANK_NAME


    def _mapping(
        self,
        request: LiveCalculationRequest,
    ) -> dict[str, Any] | None:

        mapping = PRODUCT_MAPPINGS.get(
            int(request.product_id)
        )

        if mapping is None:
            return None

        if (
            _normalized(request.family_key)
            != _normalized(mapping["family_key"])
        ):
            return None

        return mapping


    def can_handle(
        self,
        request: LiveCalculationRequest,
    ) -> bool:

        return (
            _normalized(request.bank_name)
            == _normalized(self.bank_name)
            and self._mapping(request) is not None
            and (
                request.variant is None
                or _normalized(request.variant) == "standard"
            )
        )


    def _unverified(
        self,
        request: LiveCalculationRequest,
        reason: str,
    ) -> LiveCalculationResult:

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


    def _ineligible(
        self,
        request: LiveCalculationRequest,
        reason: str,
    ) -> LiveCalculationResult:

        return validate_live_result(
            LiveCalculationResult(
                request=request,
                status=(
                    LiveCalculationStatus
                    .INELIGIBLE
                ),
                reason=reason,
            )
        )


    def _prepare_session(
        self,
        request: LiveCalculationRequest,
    ):

        mapping = self._mapping(request)
        if mapping is None:
            return self._unverified(
                request,
                "No verified Vakıf Katılım calculator mapping exists for this product.",
            )

        session = requests.Session()

        page = session.get(
            CALCULATOR_PAGE,
            headers=HEADERS,
            timeout=live_http_timeout(),
        )

        page.raise_for_status()

        html = page.text

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        form = soup.find(
            "form",
            id="financing-calculator",
        )

        if form is None:

            return self._unverified(
                request,
                (
                    "Official financing calculator "
                    "form could not be verified."
                ),
            )


        token_input = form.find(
            "input",
            attrs={
                "name":
                    "__RequestVerificationToken"
            },
        )

        if token_input is None:

            return self._unverified(
                request,
                (
                    "Official calculator anti-forgery "
                    "token could not be verified."
                ),
            )


        token = str(
            token_input.get(
                "value"
            )
            or ""
        ).strip()

        if not token:

            return self._unverified(
                request,
                (
                    "Official calculator anti-forgery "
                    "token is empty."
                ),
            )


        lang_match = re.search(
            r"""\blangId\s*:\s*['"]([^'"]+)['"]""",
            html,
        )

        language_match = re.search(
            r"""\blanguage\s*:\s*['"]([^'"]+)['"]""",
            html,
        )

        if (
            lang_match is None
            or
            language_match is None
        ):

            return self._unverified(
                request,
                (
                    "Official calculator language "
                    "contract could not be verified."
                ),
            )


        select = form.find(
            "select",
            id="financing-type-select",
        )

        if select is None:

            return self._unverified(
                request,
                (
                    "Official financing product "
                    "catalog could not be verified."
                ),
            )


        wanted_tokens = tuple(
            _normalized(token)
            for token in mapping["calculator_label_tokens"]
        )

        option = None
        for candidate in select.find_all("option"):
            label = _normalized(" ".join(candidate.stripped_strings))
            # Turkish dotted/dotless characters are normalized for stable matching.
            label_ascii = (
                label.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
                .replace("ü", "u").replace("ö", "o").replace("ç", "c")
            )
            tokens_ascii = tuple(
                token.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
                .replace("ü", "u").replace("ö", "o").replace("ç", "c")
                for token in wanted_tokens
            )
            if all(token in label_ascii for token in tokens_ascii):
                option = candidate
                break

        if option is None:
            return self._unverified(
                request,
                "Official calculator no longer publishes the mapped financing type.",
            )

        financing_type = str(option.get("value") or "").strip()
        if not financing_type:
            return self._unverified(
                request,
                "Official calculator financing type code is empty.",
            )


        try:

            max_maturity = int(
                option.get(
                    "data-installments"
                )
            )

        except Exception:

            return self._unverified(
                request,
                (
                    "Official maximum maturity "
                    "could not be verified."
                ),
            )


        if (
            int(
                request.maturity_months
            )
            >
            max_maturity
        ):

            return self._ineligible(
                request,
                (
                    "Requested maturity exceeds "
                    "the official calculator "
                    f"maximum ({max_maturity} months)."
                ),
            )


        radios = form.find_all(
            "input",
            attrs={
                "name":
                    "finansman-type"
            },
        )

        checked = next(
            (
                radio
                for radio in radios
                if radio.has_attr(
                    "checked"
                )
            ),
            None,
        )

        if checked is None:

            return self._unverified(
                request,
                (
                    "Official default calculation "
                    "type could not be verified."
                ),
            )


        calculate_type = str(
            checked.get(
                "value"
            )
            or ""
        ).strip()

        if (
            calculate_type
            !=
            CALCULATE_TYPE
        ):

            return self._unverified(
                request,
                (
                    "Official calculator default "
                    "calculation semantics changed."
                ),
            )


        return {
            "session":
                session,

            "token":
                token,

            "financing_type":
                financing_type,

            "lang_id":
                lang_match.group(
                    1
                ),

            "language":
                language_match.group(
                    1
                ),

            "max_maturity":
                max_maturity,

            "calculator_title":
                " ".join(
                    option.stripped_strings
                ),
        }


    def _calculate(
        self,
        request: LiveCalculationRequest,
    ) -> LiveCalculationResult:

        prepared = self._prepare_session(
            request
        )

        if isinstance(
            prepared,
            LiveCalculationResult,
        ):
            return prepared


        session = prepared[
            "session"
        ]

        token = prepared[
            "token"
        ]

        requested_amount = Decimal(
            str(
                request.amount
            )
        )

        requested_maturity = int(
            request.maturity_months
        )

        amount_text = _amount_text(
            requested_amount
        )


        ajax_headers = {
            "User-Agent":
                HEADERS[
                    "User-Agent"
                ],

            "Accept":
                (
                    "application/json, "
                    "text/javascript, */*; q=0.01"
                ),

            "Accept-Language":
                HEADERS[
                    "Accept-Language"
                ],

            "X-Requested-With":
                "XMLHttpRequest",

            "Origin":
                BASE_URL,

            "Referer":
                CALCULATOR_PAGE,
        }


        calc_params = {
            "langId":
                prepared[
                    "lang_id"
                ],

            "language":
                prepared[
                    "language"
                ],

            "financingType":
                prepared["financing_type"],

            "amount":
                amount_text,

            "numberOfInstallments":
                str(
                    requested_maturity
                ),

            # Official frontend sends no
            # user-supplied custom rate.
            "profitRate":
                "null",

            "calculateType":
                CALCULATE_TYPE,
        }


        response = session.post(
            CALCULATOR_ENDPOINT,
            params=calc_params,
            data={
                "__RequestVerificationToken":
                    token,
            },
            headers=ajax_headers,
            timeout=live_http_timeout(),
        )

        response.raise_for_status()

        payload = response.json()


        if not isinstance(
            payload,
            dict,
        ):

            return self._unverified(
                request,
                (
                    "Official calculator response "
                    "is not a verifiable object."
                ),
            )


        if (
            payload.get(
                "isErrorFriendly"
            )
            is True
        ):

            return self._unverified(
                request,
                (
                    "Official live calculator "
                    "rejected the exact requested "
                    "scenario."
                ),
            )


        rate = _decimal_tr(
            payload.get(
                "profitRate"
            )
        )

        monthly = _decimal_tr(
            payload.get(
                "installmentAmount"
            )
        )

        total = _decimal_tr(
            payload.get(
                "totalAmount"
            )
        )

        appraisal = _decimal_tr(
            payload.get(
                "appraisementFee"
            )
        )

        mortgage = _decimal_tr(
            payload.get(
                "mortgageReleaseFee"
            )
        )


        if (
            rate is None
            or
            rate <= 0
            or
            monthly is None
            or
            monthly <= 0
            or
            total is None
            or
            total <= 0
        ):

            return self._unverified(
                request,
                (
                    "Official calculator returned "
                    "missing or invalid core "
                    "financial values."
                ),
            )


        # ====================================================
        # PAYMENT PLAN CROSS-VERIFICATION
        # ====================================================

        plan_params = {
            "langId":
                prepared[
                    "lang_id"
                ],

            "language":
                prepared[
                    "language"
                ],

            "financingType":
                prepared["financing_type"],

            "amount":
                amount_text,

            "numberOfInstallments":
                str(
                    requested_maturity
                ),

            "profitRate":
                str(
                    payload[
                        "profitRate"
                    ]
                ),

            "calculateType":
                CALCULATE_TYPE,
        }


        plan_response = session.post(
            PAYMENT_PLAN_ENDPOINT,
            params=plan_params,
            data={
                "__RequestVerificationToken":
                    token,
            },
            headers=ajax_headers,
            timeout=live_http_timeout(),
        )

        plan_response.raise_for_status()

        plan_payload = (
            plan_response.json()
        )


        if not isinstance(
            plan_payload,
            dict,
        ):

            return self._unverified(
                request,
                (
                    "Official payment plan response "
                    "is not a verifiable object."
                ),
            )


        plan_info = (
            plan_payload.get(
                "ornekOdemeBilgisi"
            )
            or {}
        )

        plan_rows = (
            plan_payload.get(
                "tableBody"
            )
            or []
        )


        if (
            len(
                plan_rows
            )
            !=
            requested_maturity
        ):

            return self._unverified(
                request,
                (
                    "Official payment-plan row count "
                    "does not match the exact "
                    "requested maturity."
                ),
            )


        plan_rate = _decimal_tr(
            plan_info.get(
                "karOrani"
            )
        )

        plan_monthly = _decimal_tr(
            plan_info.get(
                "taksitTutari"
            )
        )

        plan_total = _decimal_tr(
            plan_info.get(
                "odenecekToplamTutar"
            )
        )


        if (
            plan_rate is None
            or
            abs(
                plan_rate - rate
            )
            >
            Decimal("0.0001")
        ):

            return self._unverified(
                request,
                (
                    "Calculator profit-share rate "
                    "does not match the official "
                    "payment plan."
                ),
            )


        if (
            plan_monthly is None
            or
            abs(
                plan_monthly - monthly
            )
            >
            PLAN_TOLERANCE
        ):

            return self._unverified(
                request,
                (
                    "Calculator installment amount "
                    "does not match the official "
                    "payment plan."
                ),
            )


        if (
            plan_total is None
            or
            abs(
                plan_total - total
            )
            >
            PLAN_TOLERANCE
        ):

            return self._unverified(
                request,
                (
                    "Calculator total repayment "
                    "does not match the official "
                    "payment plan."
                ),
            )


        result = LiveCalculationResult(
            request=request,

            status=(
                LiveCalculationStatus
                .VERIFIED
            ),

            calculated_amount=
                requested_amount,

            calculated_maturity_months=
                requested_maturity,

            profit_share_rate=
                rate,

            monthly_installment=
                monthly,

            total_repayment=
                total,

            # Calculator response does not
            # directly return allocation_fee.
            # Do not infer it here.
            allocation_fee=None,

            mortgage_fee=
                mortgage,

            appraisal_fee=
                appraisal,

            # No complete official total-fees
            # response field is available.
            total_fees=None,

            source_kind=(
                "official_live_calculator_endpoint"
            ),

            source_url=
                CALCULATOR_PAGE,

            source_note=(
                "Vakıf Katılım official live "
                "calculator result for the exact "
                "requested amount and maturity. "
                "Core values were cross-verified "
                "against the official payment plan. "
                "Allocation fee and total fees are "
                "not inferred."
            ),

            checked_at=datetime.now(
                timezone.utc
            ),

            raw_output={
                "product_id":
                    int(request.product_id),

                "financing_type":
                    prepared["financing_type"],

                "calculate_type":
                    CALCULATE_TYPE,

                "calculator_title":
                    prepared[
                        "calculator_title"
                    ],

                "official_max_maturity":
                    prepared[
                        "max_maturity"
                    ],

                "request_params":
                    calc_params,

                "calculator_response":
                    payload,

                "payment_plan_response":
                    plan_payload,

                "validation": {
                    "requested_amount":
                        str(
                            requested_amount
                        ),

                    "requested_maturity":
                        requested_maturity,

                    "payment_plan_rows":
                        len(
                            plan_rows
                        ),

                    "rate_match":
                        True,

                    "monthly_match":
                        True,

                    "total_match":
                        True,

                    "allocation_fee_inferred":
                        False,

                    "total_fees_inferred":
                        False,
                },
            },
        )


        return validate_live_result(
            result
        )


    def calculate(
        self,
        request: LiveCalculationRequest,
    ) -> LiveCalculationResult:

        if not self.can_handle(
            request
        ):

            return self._unverified(
                request,
                (
                    "Request does not match the "
                    "verified Vakif Katilim "
                    "Ihtiyac Finansmani mapping."
                ),
            )

        try:

            return self._calculate(
                request
            )

        except requests.RequestException as exc:

            return self._unverified(
                request,
                (
                    "Official Vakif Katilim "
                    "calculator could not be reached: "
                    f"{type(exc).__name__}"
                ),
            )

        except Exception as exc:

            # Fail closed:
            # parsing or official-site changes must
            # never become guessed financial data.
            return self._unverified(
                request,
                (
                    "Official Vakif Katilim result "
                    "could not be verified: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
