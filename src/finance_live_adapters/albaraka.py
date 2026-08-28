# FINANCE_LIVE_ADAPTER_ALBARAKA_V1

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.finance_live_runtime import live_http_timeout

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)


class AlbarakaLiveAdapter:
    """
    Verified dynamic Albaraka Turk official calculator adapter.

    IMPORTANT:
    This adapter intentionally supports ONLY BANSA product_id=118:
    Motosiklet, ATV, Bisiklet.

    It must NOT be treated as the generic Albaraka "Ihtiyac Finansmani"
    product (product_id=121).

    Official calculator mapping:
        ProductCode    = IHTKRED
        ProductParCode = 3
        ProjectParCode = 135
        ProjectCode    = MOTOFIN (Turkish dotted-I form on source)
        CampaignCode   = MOTOFIN (Turkish dotted-I form on source)
    """

    bank_name = "Albaraka T\u00fcrk"

    PRODUCT_ID = 118

    PRODUCT_CODE = "IHTKRED"

    PROJECT_CODE = "MOTOF\u0130N"

    CALCULATOR_TITLE = (
        "D\u0130\u011eER TA\u015eIT F\u0130NANSMANI "
        "(MOTOS\u0130KLET)"
    )

    PAGE_URL = (
        "https://www.albaraka.com.tr/"
        "tr/hesaplama-araclari/"
        "finansman-hesaplama/"
        "ihtiyac-finansmani-hesaplama"
    )

    CALCULATOR_URL = (
        "https://www.albaraka.com.tr/"
        "plugins/getFinanceCalculate"
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


    @staticmethod
    def _normalized(value: Any) -> str:

        text = str(
            value
            or ""
        )

        text = (
            text
            .replace("\u0131", "i")
            .replace("\u0130", "I")
        )

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            ch
            for ch in text
            if not unicodedata.combining(ch)
        )

        return text.casefold().strip()


    @staticmethod
    def _decimal(value: Any) -> Decimal | None:

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

        if "." in text and "," in text:

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


    @staticmethod
    def _extract(
        pattern: str,
        text: str,
    ) -> str | None:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if not match:
            return None

        return match.group(1)


    def can_handle(
        self,
        request: LiveCalculationRequest,
    ) -> bool:

        if int(
            request.product_id
        ) != self.PRODUCT_ID:

            return False

        if self._normalized(
            request.bank_name
        ) != self._normalized(
            self.bank_name
        ):

            return False

        if self._normalized(
            request.family_key
        ) != "ihtiyac_finansmani":

            return False

        product_name = self._normalized(
            request.product_name
        )

        if "motosiklet" not in product_name:

            return False

        if request.variant not in (
            None,
            "",
            "standard",
        ):

            return False

        return True


    def _unverified(
        self,
        request: LiveCalculationRequest,
        reason: str,
        *,
        raw_output: dict[str, Any] | None = None,
    ) -> LiveCalculationResult:

        result = LiveCalculationResult(
            request=request,

            status=(
                LiveCalculationStatus
                .UNVERIFIED
            ),

            reason=reason,

            source_kind=(
                "official_live_calculator_endpoint"
            ),

            source_url=self.PAGE_URL,

            checked_at=datetime.now(
                timezone.utc
            ),

            raw_output=(
                raw_output
                or {}
            ),
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
                    "Albaraka adapter product identity "
                    "guard rejected this request."
                ),
            )


        try:

            session = requests.Session()

            session.headers.update(
                self.HEADERS
            )


            # --------------------------------------------------
            # Official calculator page
            # --------------------------------------------------

            page = session.get(
                self.PAGE_URL,
                timeout=live_http_timeout(),
            )

            page.raise_for_status()

            html = page.text


            # --------------------------------------------------
            # UNIGATE.current
            # --------------------------------------------------

            lang_id = self._extract(
                r"""langId\s*:\s*['"]([^'"]+)['"]""",
                html,
            )

            language = self._extract(
                r"""language\s*:\s*['"]([^'"]+)['"]""",
                html,
            )

            slug = self._extract(
                r"""Slug\s*:\s*['"]([^'"]+)['"]""",
                html,
            )


            if not all(
                (
                    lang_id,
                    language,
                    slug,
                )
            ):

                raise RuntimeError(
                    "Official UNIGATE context missing."
                )


            # --------------------------------------------------
            # Exact official HTML product mapping
            # --------------------------------------------------

            soup = BeautifulSoup(
                html,
                "html.parser",
            )

            select = soup.find(
                "select",
                id="slcfinansmanTuru",
            )

            if select is None:

                raise RuntimeError(
                    "Official financing select missing."
                )


            finance_type = None
            contract = None
            project_par_code = None


            for option in select.find_all(
                "option"
            ):

                raw_value = str(
                    option.get(
                        "value"
                    )
                    or ""
                )

                try:

                    data = json.loads(
                        raw_value
                    )

                except Exception:

                    continue


                if (
                    str(
                        data.get(
                            "ProductCode"
                        )
                        or ""
                    )
                    ==
                    self.PRODUCT_CODE
                    and
                    str(
                        data.get(
                            "ProjectCode"
                        )
                        or ""
                    )
                    ==
                    self.PROJECT_CODE
                    and
                    str(
                        data.get(
                            "CampaingCode"
                        )
                        or ""
                    )
                    ==
                    self.PROJECT_CODE
                    and
                    str(
                        data.get(
                            "CampaignName"
                        )
                        or ""
                    )
                    ==
                    self.CALCULATOR_TITLE
                ):

                    finance_type = raw_value

                    contract = data

                    project_par_code = (
                        option.get(
                            "projectparcode"
                        )
                    )

                    break


            if (
                finance_type is None
                or
                contract is None
            ):

                raise RuntimeError(
                    "Official MOTOFIN mapping missing."
                )


            if str(
                project_par_code
            ) != "135":

                raise RuntimeError(
                    "Official ProjectParCode changed."
                )


            if str(
                contract.get(
                    "ProductParCode"
                )
            ) != "3":

                raise RuntimeError(
                    "Official ProductParCode changed."
                )


            # --------------------------------------------------
            # Official calculator bounds
            # --------------------------------------------------

            maturity_min = int(
                contract.get(
                    "MaturityMinValue"
                )
            )

            maturity_max = int(
                contract.get(
                    "MaturityMaxValue"
                )
            )


            if not (
                maturity_min
                <=
                int(
                    request.maturity_months
                )
                <=
                maturity_max
            ):

                return LiveCalculationResult(
                    request=request,

                    status=(
                        LiveCalculationStatus
                        .INELIGIBLE
                    ),

                    reason=(
                        "Requested maturity is outside "
                        "the official calculator range."
                    ),

                    source_kind=(
                        "official_live_calculator_endpoint"
                    ),

                    source_url=self.PAGE_URL,

                    checked_at=datetime.now(
                        timezone.utc
                    ),

                    raw_output={
                        "contract":
                            contract,
                    },
                )


            amount_min = self._decimal(
                contract.get(
                    "AmountMinValue"
                )
            )

            amount_max = self._decimal(
                contract.get(
                    "AmountMaxValue"
                )
            )


            if (
                amount_min is not None
                and
                request.amount
                <
                amount_min
            ):

                return LiveCalculationResult(
                    request=request,

                    status=(
                        LiveCalculationStatus
                        .INELIGIBLE
                    ),

                    reason=(
                        "Requested amount is below "
                        "the official calculator minimum."
                    ),

                    source_kind=(
                        "official_live_calculator_endpoint"
                    ),

                    source_url=self.PAGE_URL,

                    checked_at=datetime.now(
                        timezone.utc
                    ),

                    raw_output={
                        "contract":
                            contract,
                    },
                )


            if (
                amount_max is not None
                and
                request.amount
                >
                amount_max
            ):

                return LiveCalculationResult(
                    request=request,

                    status=(
                        LiveCalculationStatus
                        .INELIGIBLE
                    ),

                    reason=(
                        "Requested amount is above "
                        "the official calculator maximum."
                    ),

                    source_kind=(
                        "official_live_calculator_endpoint"
                    ),

                    source_url=self.PAGE_URL,

                    checked_at=datetime.now(
                        timezone.utc
                    ),

                    raw_output={
                        "contract":
                            contract,
                    },
                )


            # --------------------------------------------------
            # Exact official JS request contract
            # --------------------------------------------------

            params = {
                "langId":
                    lang_id,

                "language":
                    language,

                "Slug":
                    slug,

                "customFinancingName":
                    "",

                "ProfitRateByMe":
                    "false",

                "FinanceType":
                    finance_type,

                "FinanceAmount":
                    str(
                        request.amount
                    ),

                "Maturity":
                    str(
                        int(
                            request.maturity_months
                        )
                    ),

                "ProfitRate":
                    "0",

                "Type":
                    "B",

                "CreditType":
                    "B",
            }


            headers = {
                **self.HEADERS,

                "Accept":
                    (
                        "application/json, "
                        "text/javascript, */*; q=0.01"
                    ),

                "Content-Type":
                    "application/json; charset=utf-8",

                "X-Requested-With":
                    "XMLHttpRequest",

                "Referer":
                    self.PAGE_URL,
            }


            response = session.get(
                self.CALCULATOR_URL,
                params=params,
                headers=headers,
                timeout=live_http_timeout(),
            )

            response.raise_for_status()

            payload = response.json()


            if not isinstance(
                payload,
                dict,
            ):

                raise RuntimeError(
                    "Calculator response is not an object."
                )


            if payload.get(
                "Result"
            ) is not True:

                raise RuntimeError(
                    "Official calculator Result != true: "
                    + str(
                        payload.get(
                            "Error"
                        )
                    )
                )


            if str(
                payload.get(
                    "ProductCode"
                )
                or ""
            ) != self.PRODUCT_CODE:

                raise RuntimeError(
                    "Calculator ProductCode mismatch."
                )


            data = (
                payload.get(
                    "Data"
                )
                or {}
            )


            # --------------------------------------------------
            # Critical numeric fields
            # --------------------------------------------------

            rate = self._decimal(
                data.get(
                    "ProfitRate"
                )
            )

            monthly = self._decimal(
                data.get(
                    "MonthlyInstallmentAmount"
                )
            )

            total = self._decimal(
                data.get(
                    "TotalAmountTobeRefunded"
                )
            )

            total_fees = self._decimal(
                data.get(
                    "TotalFees"
                )
            )

            annual_cost = self._decimal(
                data.get(
                    "AnnualCostRate"
                )
            )


            if any(
                value is None
                for value in (
                    rate,
                    monthly,
                    total,
                )
            ):

                raise RuntimeError(
                    "Critical calculator numeric field missing."
                )


            if (
                rate <= 0
                or
                monthly <= 0
                or
                total <= 0
            ):

                raise RuntimeError(
                    "Critical calculator numeric field invalid."
                )


            # --------------------------------------------------
            # Payment-plan verification
            # --------------------------------------------------

            payment_plan = data.get(
                "PaymentPlan"
            )


            if not isinstance(
                payment_plan,
                dict,
            ):

                raise RuntimeError(
                    "PaymentPlan is not an object."
                )


            rows = payment_plan.get(
                "Rows"
            )

            total_row = payment_plan.get(
                "TotalRow"
            )


            if not isinstance(
                rows,
                list,
            ):

                raise RuntimeError(
                    "PaymentPlan.Rows is not a list."
                )


            if len(
                rows
            ) != int(
                request.maturity_months
            ):

                raise RuntimeError(
                    "Payment plan maturity mismatch."
                )


            if not isinstance(
                total_row,
                dict,
            ):

                raise RuntimeError(
                    "PaymentPlan.TotalRow missing."
                )


            total_row_amount = self._decimal(
                total_row.get(
                    "InstallmentAmount"
                )
            )


            if total_row_amount is None:

                raise RuntimeError(
                    "Payment plan total row amount missing."
                )


            if abs(
                total_row_amount
                -
                total
            ) > Decimal(
                "0.02"
            ):

                raise RuntimeError(
                    "Calculator total and payment-plan "
                    "total do not match."
                )


            first_installment = None

            if rows:

                first_installment = self._decimal(
                    rows[0].get(
                        "InstallmentAmount"
                    )
                )


            if (
                first_installment is not None
                and
                abs(
                    first_installment
                    -
                    monthly
                )
                >
                Decimal(
                    "0.02"
                )
            ):

                raise RuntimeError(
                    "Monthly installment and first payment "
                    "plan row do not match."
                )


            # --------------------------------------------------
            # Explicit fee verification
            # --------------------------------------------------

            expenses = (
                data.get(
                    "AmortizationScheduleExpenses"
                )
                or []
            )


            if not isinstance(
                expenses,
                list,
            ):

                raise RuntimeError(
                    "Expense structure is not a list."
                )


            allocation_fee = None

            explicit_fee_sum = Decimal(
                "0"
            )

            parsed_expense_count = 0


            for expense in expenses:

                if not isinstance(
                    expense,
                    dict,
                ):

                    continue


                amount_value = self._decimal(
                    expense.get(
                        "AmountWithTax"
                    )
                )


                if amount_value is not None:

                    explicit_fee_sum += (
                        amount_value
                    )

                    parsed_expense_count += 1


                explanation = self._normalized(
                    expense.get(
                        "FeeExplanation"
                    )
                )


                if (
                    "tahsis"
                    in explanation
                    and
                    amount_value is not None
                ):

                    allocation_fee = (
                        amount_value
                    )


            if (
                total_fees is not None
                and
                parsed_expense_count > 0
                and
                abs(
                    explicit_fee_sum
                    -
                    total_fees
                )
                >
                Decimal(
                    "0.02"
                )
            ):

                raise RuntimeError(
                    "Explicit expense sum and TotalFees "
                    "do not match."
                )


            # --------------------------------------------------
            # Verified result
            # --------------------------------------------------

            result = LiveCalculationResult(
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
                    allocation_fee
                ),

                mortgage_fee=None,

                appraisal_fee=None,

                total_fees=total_fees,

                source_kind=(
                    "official_live_calculator_endpoint"
                ),

                source_url=self.PAGE_URL,

                source_note=(
                    "Albaraka Turk official financing "
                    "calculator; exact MOTOFIN product "
                    "mapping verified from the official "
                    "HTML option contract."
                ),

                checked_at=datetime.now(
                    timezone.utc
                ),

                raw_output={
                    "calculator_title":
                        contract.get(
                            "CampaignName"
                        ),

                    "ProductCode":
                        contract.get(
                            "ProductCode"
                        ),

                    "ProductParCode":
                        contract.get(
                            "ProductParCode"
                        ),

                    "ProjectParCode":
                        project_par_code,

                    "project_code":
                        contract.get(
                            "ProjectCode"
                        ),

                    "campaign_code":
                        contract.get(
                            "CampaingCode"
                        ),

                    "annual_cost_rate":
                        (
                            str(
                                annual_cost
                            )
                            if annual_cost
                            is not None
                            else None
                        ),

                    "payment_plan_rows":
                        len(
                            rows
                        ),

                    "calculator_data":
                        data,
                },
            )


            return validate_live_result(
                result
            )


        except Exception as exc:

            return self._unverified(
                request,

                (
                    "Albaraka official live calculator "
                    "verification failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
