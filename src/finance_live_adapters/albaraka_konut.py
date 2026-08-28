# FINANCE_LIVE_ADAPTER_ALBARAKA_KONUT_V2_1

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import re

import requests
from bs4 import BeautifulSoup

from src.finance_live_runtime import live_http_timeout

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)

from src.finance_live_adapters.albaraka import (
    AlbarakaLiveAdapter,
)


BANK_NAME = "Albaraka T\u00fcrk"

PRODUCT_ID = 97

FAMILY_KEY = (
    "konut_finansmani"
)

PAGE_URL = (
    "https://www.albaraka.com.tr/"
    "tr/hesaplama-araclari/"
    "finansman-hesaplama/"
    "konut-finansmani-hesaplama"
)

VARIANTS = {
    "ilk_ev": {
        "ProductCode":
            "KONTKRD",

        "ProductParCode":
            "1",

        "ProjectCode":
            "YOKKNTF",

        "CampaingCode":
            "YKKNT0B",

        "ProjectParCode":
            "143",

        "CampaignName":
            (
                "\u0130LK EV\u0130M "
                "KONUT F\u0130NANSMANI"
            ),
    },

    "mevcut_konut": {
        "ProductCode":
            "KONTKRD",

        "ProductParCode":
            "1",

        "ProjectCode":
            "VARKNTF",

        "CampaingCode":
            "VRKNT0B",

        "ProjectParCode":
            "144",

        "CampaignName":
            (
                "2. VE SONRAK\u0130 "
                "KONUT F\u0130NANSMANI"
            ),
    },
}


class AlbarakaKonutLiveAdapter(
    AlbarakaLiveAdapter,
):

    bank_name = BANK_NAME


    def can_handle(
        self,
        request: LiveCalculationRequest,
    ) -> bool:

        try:

            product_id = int(
                request.product_id
            )

        except Exception:

            return False


        if product_id != PRODUCT_ID:

            return False


        if (
            self._normalized(
                request.bank_name
            )
            !=
            self._normalized(
                BANK_NAME
            )
        ):

            return False


        if (
            self._normalized(
                request.family_key
            )
            !=
            FAMILY_KEY
        ):

            return False


        if (
            "konut"
            not in
            self._normalized(
                request.product_name
            )
        ):

            return False


        return (
            self._normalized(
                request.variant
            )
            in {
                "",
                "standard",
                "ilk_ev",
                "mevcut_konut",
            }
        )


    def _housing_unverified(
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


    def _housing_ineligible(
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


    def _prepare_housing(self):

        session = requests.Session()

        session.headers.update(
            self.HEADERS
        )


        response = session.get(
            PAGE_URL,
            timeout=live_http_timeout(),
        )

        response.raise_for_status()

        html = response.text


        def extract(pattern):

            match = re.search(
                pattern,
                html,
            )

            return (
                match.group(1).strip()
                if match
                else ""
            )


        lang_id = extract(
            r"""langId\s*:\s*['"]([^'"]+)['"]"""
        )

        language = extract(
            r"""language\s*:\s*['"]([^'"]+)['"]"""
        )

        slug = extract(
            r"""Slug\s*:\s*['"]([^'"]+)['"]"""
        )


        if not all(
            (
                lang_id,
                language,
                slug,
            )
        ):

            raise RuntimeError(
                "Albaraka calculator context missing."
            )


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
                "Albaraka finance selector missing."
            )


        mappings = {}


        for option in select.find_all(
            "option"
        ):

            raw = str(
                option.get("value")
                or ""
            )


            try:

                item = json.loads(
                    raw
                )

            except Exception:

                continue


            # V45: campaign/project codes on Albaraka's calculator are dynamic
            # commercial identifiers and may change while the underlying
            # housing product remains the same.  Discover the current official
            # option from the live selector instead of pinning yesterday's
            # campaign code.  ProductCode + visible/current option semantics
            # remain strict guards.
            if str(item.get("ProductCode") or "") != "KONTKRD":
                continue

            product_par = str(item.get("ProductParCode") or "")
            if product_par and product_par != "1":
                continue

            label = self._normalized(
                " ".join(
                    str(v or "")
                    for v in (
                        option.get_text(" ", strip=True),
                        item.get("CampaignName"),
                        item.get("ProjectCode"),
                        item.get("CampaingCode"),
                    )
                )
            )

            variant = None
            if (
                "ilk ev" in label
                or "ilk konut" in label
                or "yeni konut" in label
            ):
                variant = "ilk_ev"
            elif (
                "2. ve sonraki" in label
                or "2 ve sonraki" in label
                or "ikinci" in label
                or "sonraki konut" in label
                or "mevcut konut" in label
            ):
                variant = "mevcut_konut"

            # Backward-compatible semantic fallback for older selector labels.
            if variant is None:
                project_code = self._normalized(item.get("ProjectCode"))
                if project_code.startswith("yokknt"):
                    variant = "ilk_ev"
                elif project_code.startswith("varknt"):
                    variant = "mevcut_konut"

            if variant is None or variant in mappings:
                continue

            project_par = str(
                option.get(
                    "projectparcode"
                )
                or item.get("ProjectParCode")
                or ""
            )

            mappings[variant] = {
                "raw": raw,
                "data": item,
                "project_par": project_par,
                "discovered_label": option.get_text(" ", strip=True),
            }


        if set(mappings) != {"ilk_ev", "mevcut_konut"}:

            raise RuntimeError(
                "Albaraka housing selector no longer exposes both verified housing conditions."
            )


        return {
            "session":
                session,

            "lang_id":
                lang_id,

            "language":
                language,

            "slug":
                slug,

            "mappings":
                mappings,
        }


    def _calculate_housing_variant(
        self,
        request,
        prepared,
        variant,
    ):

        mapping = (
            prepared[
                "mappings"
            ][variant]
        )

        contract = mapping[
            "data"
        ]


        min_maturity = int(
            contract[
                "MaturityMinValue"
            ]
        )

        max_maturity = int(
            contract[
                "MaturityMaxValue"
            ]
        )


        if not (
            min_maturity
            <=
            int(
                request.maturity_months
            )
            <=
            max_maturity
        ):

            return self._housing_ineligible(
                request,
                (
                    "Requested maturity is outside "
                    "the official Albaraka "
                    "housing calculator range."
                ),
            )


        min_amount = self._decimal(
            contract.get(
                "AmountMinValue"
            )
        )

        max_amount = self._decimal(
            contract.get(
                "AmountMaxValue"
            )
        )


        if (
            min_amount is not None
            and
            request.amount
            <
            min_amount
        ):

            return self._housing_ineligible(
                request,
                (
                    "Requested amount is below "
                    "the official Albaraka "
                    "housing calculator range."
                ),
            )


        if (
            max_amount is not None
            and
            request.amount
            >
            max_amount
        ):

            return self._housing_ineligible(
                request,
                (
                    "Requested amount is above "
                    "the official Albaraka "
                    "housing calculator range."
                ),
            )


        response = (
            prepared["session"]
            .get(
                self.CALCULATOR_URL,

                params={
                    "langId":
                        prepared[
                            "lang_id"
                        ],

                    "language":
                        prepared[
                            "language"
                        ],

                    "Slug":
                        prepared[
                            "slug"
                        ],

                    "customFinancingName":
                        "",

                    "ProfitRateByMe":
                        "false",

                    "FinanceType":
                        mapping[
                            "raw"
                        ],

                    "FinanceAmount":
                        str(
                            request.amount
                        ),

                    "Maturity":
                        str(
                            int(
                                request
                                .maturity_months
                            )
                        ),

                    "ProfitRate":
                        "0",

                    "Type":
                        "B",

                    "CreditType":
                        "B",
                },

                headers={
                    **self.HEADERS,

                    "Accept":
                        (
                            "application/json, "
                            "text/javascript, */*; q=0.01"
                        ),

                    "Content-Type":
                        (
                            "application/json; "
                            "charset=utf-8"
                        ),

                    "X-Requested-With":
                        "XMLHttpRequest",

                    "Referer":
                        PAGE_URL,
                },

                timeout=live_http_timeout(),
            )
        )


        response.raise_for_status()

        payload = response.json()


        if (
            not isinstance(
                payload,
                dict,
            )
            or
            payload.get(
                "Result"
            )
            is not True
        ):

            raise RuntimeError(
                "Albaraka calculator Result "
                "contract changed."
            )


        if (
            str(
                payload.get(
                    "ProductCode"
                )
                or ""
            )
            !=
            "KONTKRD"
        ):

            raise RuntimeError(
                "Albaraka housing ProductCode "
                "mismatch."
            )


        data = (
            payload.get("Data")
            or {}
        )


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
            or
            value <= 0

            for value in (
                rate,
                monthly,
                total,
            )
        ):

            raise RuntimeError(
                "Albaraka verified numeric "
                "parser returned invalid values."
            )


        payment_plan = (
            data.get(
                "PaymentPlan"
            )
            or {}
        )

        rows = (
            payment_plan.get(
                "Rows"
            )
            or []
        )


        if (
            not isinstance(
                rows,
                list,
            )
            or
            len(rows)
            !=
            int(
                request.maturity_months
            )
        ):

            raise RuntimeError(
                "Albaraka payment-plan "
                "maturity mismatch."
            )


        total_row = (
            payment_plan.get(
                "TotalRow"
            )
            or {}
        )

        plan_total = self._decimal(
            total_row.get(
                "InstallmentAmount"
            )
        )


        if (
            plan_total is None
            or
            abs(
                plan_total
                -
                total
            )
            >
            Decimal("0.02")
        ):

            raise RuntimeError(
                "Albaraka payment-plan "
                "total mismatch."
            )


        if rows:

            first_installment = (
                self._decimal(
                    rows[0].get(
                        "InstallmentAmount"
                    )
                )
            )


            if (
                first_installment
                is not None
                and
                abs(
                    first_installment
                    -
                    monthly
                )
                >
                Decimal("0.02")
            ):

                raise RuntimeError(
                    "Albaraka first installment "
                    "does not match monthly payment."
                )


        allocation_fee = None
        appraisal_fee = None
        mortgage_fee = None


        for expense in (
            data.get(
                "AmortizationScheduleExpenses"
            )
            or []
        ):

            if not isinstance(
                expense,
                dict,
            ):

                continue


            explanation = (
                self._normalized(
                    expense.get(
                        "FeeExplanation"
                    )
                )
            )

            expense_amount = self._decimal(
                expense.get(
                    "AmountWithTax"
                )
            )


            if expense_amount is None:
                continue


            if (
                "tahsis"
                in explanation
            ):

                allocation_fee = (
                    expense_amount
                    if allocation_fee is None
                    else allocation_fee
                    + expense_amount
                )


            elif (
                "ekspertiz"
                in explanation
            ):

                appraisal_fee = (
                    expense_amount
                    if appraisal_fee is None
                    else appraisal_fee
                    + expense_amount
                )


            elif (
                "ipotek"
                in explanation
                and
                "tesis"
                in explanation
            ):

                mortgage_fee = (
                    expense_amount
                    if mortgage_fee is None
                    else mortgage_fee
                    + expense_amount
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
                    allocation_fee
                ),

                mortgage_fee=mortgage_fee,

                appraisal_fee=appraisal_fee,

                total_fees=total_fees,

                source_kind=(
                    "official_live_calculator_endpoint"
                ),

                source_url=PAGE_URL,

                source_note=(
                    "Albaraka Turk official "
                    "Konut Finansmani calculator; "
                    "existing production numeric "
                    "parser reused."
                ),

                checked_at=datetime.now(
                    timezone.utc
                ),

                raw_output={
                    "housing_variant":
                        variant,

                    "ProductCode":
                        contract.get(
                            "ProductCode"
                        ),

                    "ProductParCode":
                        contract.get(
                            "ProductParCode"
                        ),

                    "ProjectCode":
                        contract.get(
                            "ProjectCode"
                        ),

                    "CampaingCode":
                        contract.get(
                            "CampaingCode"
                        ),

                    "ProjectParCode":
                        mapping.get(
                            "project_par"
                        ),

                    "annual_cost_rate":
                        (
                            str(
                                annual_cost
                            )
                            if
                            annual_cost
                            is not None
                            else None
                        ),

                    "payment_plan_rows":
                        len(rows),
                },
            )
        )


    @staticmethod
    def _housing_signature(
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
        request: LiveCalculationRequest,
    ) -> LiveCalculationResult:

        if not self.can_handle(
            request
        ):

            return self._housing_unverified(
                request,
                (
                    "Albaraka housing adapter "
                    "identity guard rejected request."
                ),
            )


        try:

            prepared = (
                self._prepare_housing()
            )

            variant = (
                self._normalized(
                    request.variant
                )
            )


            if variant in VARIANTS:

                return (
                    self._calculate_housing_variant(
                        request,
                        prepared,
                        variant,
                    )
                )


            variants = (
                "ilk_ev",
                "mevcut_konut",
            )


            results = [
                self._calculate_housing_variant(
                    request,
                    prepared,
                    item,
                )

                for item in variants
            ]


            if not all(
                result.status
                ==
                LiveCalculationStatus.VERIFIED

                for result in results
            ):

                return self._housing_unverified(
                    request,
                    (
                        "Both Albaraka housing "
                        "conditions could not be "
                        "verified live."
                    ),
                )


            signatures = {
                self._housing_signature(
                    result
                )
                for result in results
            }


            if len(signatures) != 1:

                return self._housing_unverified(
                    request,
                    (
                        "Albaraka housing results "
                        "are condition-specific; "
                        "generic numeric collapse "
                        "was blocked."
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
                        "Albaraka Turk official "
                        "Konut Finansmani calculator; "
                        "both housing conditions were "
                        "verified live and returned "
                        "the same financial result."
                    ),

                    raw_output=raw,
                )
            )


        except Exception as exc:

            return self._housing_unverified(
                request,
                (
                    "Albaraka live housing "
                    "verification failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
