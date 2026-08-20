from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


DB = Path("data") / "campaigns.db"
REPORT_DIR = Path("data") / "quality"
REPORT_JSON = (
    REPORT_DIR
    / "standard_products_global_quality.json"
)


def norm_text(value) -> str:
    return " ".join(
        str(value or "").strip().casefold().split()
    )


def is_vehicle_family(value) -> bool:
    key = norm_text(value)

    return any(
        token in key
        for token in (
            "araç",
            "arac",
            "taşıt",
            "tasit",
            "motosiklet",
        )
    )


def safe_float(value):
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result):
        return None

    return result


def main() -> int:
    if not DB.exists():
        raise SystemExit(
            f"DB bulunamadı: {DB}"
        )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    findings: list[dict] = []

    def add(
        severity: str,
        code: str,
        *,
        bank: str | None = None,
        product: str | None = None,
        product_id: int | None = None,
        detail: str,
    ):
        findings.append(
            {
                "severity": severity,
                "code": code,
                "bank": bank,
                "product": product,
                "product_id": product_id,
                "detail": detail,
            }
        )

    # --------------------------------------------------------
    # Active standard products
    # --------------------------------------------------------
    products = con.execute(
        """
        SELECT
            c.id,
            c.bank_name,
            c.source_url,
            d.product_name,
            d.product_family,
            d.scope,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.minimum_maturity_months,
            d.maximum_maturity_months,
            d.profit_share_rate,
            d.profit_share_rate_text,
            d.vehicle_finance_rules_text,
            d.vehicle_age_rules_text,
            d.finance_rules_json
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
          ON d.product_id=c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            c.bank_name,
            d.product_family,
            d.product_name
        """
    ).fetchall()

    product_by_id = {
        int(row["id"]): row
        for row in products
    }

    print("=" * 100)
    print("STANDART ÜRÜNLER — GLOBAL KALİTE DENETİMİ")
    print("=" * 100)
    print("Aktif standart ürün:", len(products))
    print()

    # --------------------------------------------------------
    # 1) Required fields / impossible numeric values
    # --------------------------------------------------------
    for row in products:
        pid = int(row["id"])
        bank = row["bank_name"]
        name = str(
            row["product_name"] or ""
        ).strip()
        family = row["product_family"]

        if not name:
            add(
                "ERROR",
                "EMPTY_PRODUCT_NAME",
                bank=bank,
                product_id=pid,
                detail="Aktif standart ürünün adı boş.",
            )

        if not str(
            row["source_url"] or ""
        ).strip():
            add(
                "ERROR",
                "EMPTY_SOURCE_URL",
                bank=bank,
                product=name,
                product_id=pid,
                detail="Resmî kaynak URL alanı boş.",
            )

        min_amount = safe_float(
            row["minimum_financing_amount"]
        )
        max_amount = safe_float(
            row["maximum_financing_amount"]
        )

        if (
            min_amount is not None
            and min_amount < 0
        ):
            add(
                "ERROR",
                "NEGATIVE_MIN_AMOUNT",
                bank=bank,
                product=name,
                product_id=pid,
                detail=f"Minimum tutar negatif: {min_amount}",
            )

        if (
            max_amount is not None
            and max_amount < 0
        ):
            add(
                "ERROR",
                "NEGATIVE_MAX_AMOUNT",
                bank=bank,
                product=name,
                product_id=pid,
                detail=f"Maksimum tutar negatif: {max_amount}",
            )

        if (
            min_amount is not None
            and max_amount is not None
            and min_amount > max_amount
        ):
            add(
                "ERROR",
                "MIN_AMOUNT_GT_MAX_AMOUNT",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    f"Minimum tutar {min_amount} > "
                    f"maksimum tutar {max_amount}"
                ),
            )

        min_maturity = row[
            "minimum_maturity_months"
        ]
        max_maturity = row[
            "maximum_maturity_months"
        ]

        for label, value in (
            ("minimum", min_maturity),
            ("maximum", max_maturity),
        ):
            if (
                value is not None
                and not 1 <= int(value) <= 120
            ):
                add(
                    "WARN",
                    "SUSPICIOUS_MATURITY",
                    bank=bank,
                    product=name,
                    product_id=pid,
                    detail=(
                        f"{label} vade şüpheli: "
                        f"{value} ay"
                    ),
                )

        rate = safe_float(
            row["profit_share_rate"]
        )
        if (
            rate is not None
            and not 0 <= rate <= 100
        ):
            add(
                "ERROR",
                "INVALID_PROFIT_RATE",
                bank=bank,
                product=name,
                product_id=pid,
                detail=f"Kâr payı oranı geçersiz: %{rate}",
            )

        if (
            not is_vehicle_family(family)
            and str(
                row["vehicle_finance_rules_text"]
                or ""
            ).strip()
        ):
            add(
                "ERROR",
                "NON_VEHICLE_HAS_VEHICLE_RULE",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    "Araç ailesinde olmayan üründe "
                    "vehicle_finance_rules_text dolu."
                ),
            )

        if (
            not is_vehicle_family(family)
            and str(
                row["vehicle_age_rules_text"]
                or ""
            ).strip()
        ):
            add(
                "ERROR",
                "NON_VEHICLE_HAS_VEHICLE_AGE_RULE",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    "Araç ailesinde olmayan üründe "
                    "vehicle_age_rules_text dolu."
                ),
            )

    # --------------------------------------------------------
    # 2) Duplicate current products
    # --------------------------------------------------------
    duplicate_groups = defaultdict(list)

    for row in products:
        key = (
            norm_text(row["bank_name"]),
            norm_text(row["product_name"]),
            norm_text(row["scope"]),
        )
        duplicate_groups[key].append(row)

    for group in duplicate_groups.values():
        if len(group) <= 1:
            continue

        urls = {
            norm_text(row["source_url"])
            for row in group
        }

        # Aynı banka + aynı ürün adı birden fazla aktif kayıt.
        add(
            "WARN",
            "DUPLICATE_ACTIVE_PRODUCT_NAME",
            bank=group[0]["bank_name"],
            product=group[0]["product_name"],
            detail=(
                f"{len(group)} aktif kayıt var "
                f"(aynı kapsam: {group[0]['scope']}). "
                f"Kaynak URL sayısı: {len(urls)}. "
                f"ID'ler: "
                + ", ".join(
                    str(row["id"])
                    for row in group
                )
            ),
        )

    # --------------------------------------------------------
    # 3) Pricing tiers
    # --------------------------------------------------------
    pricing = con.execute(
        """
        SELECT
            r.product_id,
            r.pricing_variant,
            r.maturity_months,
            r.profit_share_rate,
            r.allocation_fee_rate,
            r.monthly_total_cost_rate,
            r.annual_total_cost_rate
        FROM live_product_pricing_tiers AS r
        JOIN live_campaigns AS c
          ON c.id=r.product_id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            r.product_id,
            r.pricing_variant,
            r.maturity_months
        """
    ).fetchall()

    pricing_by_product = defaultdict(list)

    for row in pricing:
        pricing_by_product[
            int(row["product_id"])
        ].append(row)

        pid = int(row["product_id"])
        product = product_by_id.get(pid)

        if not product:
            continue

        bank = product["bank_name"]
        name = product["product_name"]

        maturity = row["maturity_months"]
        profit = safe_float(
            row["profit_share_rate"]
        )
        allocation = safe_float(
            row["allocation_fee_rate"]
        )

        if (
            maturity is not None
            and not 1 <= int(maturity) <= 120
        ):
            add(
                "ERROR",
                "INVALID_PRICING_MATURITY",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    f"Fiyatlama vadesi geçersiz: "
                    f"{maturity}"
                ),
            )

        if (
            profit is not None
            and not 0 <= profit <= 100
        ):
            add(
                "ERROR",
                "INVALID_PRICING_PROFIT_RATE",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    f"Fiyatlama kâr oranı "
                    f"geçersiz: %{profit}"
                ),
            )

        if (
            allocation is not None
            and not 0 <= allocation <= 100
        ):
            add(
                "ERROR",
                "INVALID_ALLOCATION_RATE",
                bank=bank,
                product=name,
                product_id=pid,
                detail=(
                    "Tahsis ücreti oranı "
                    f"geçersiz: %{allocation}"
                ),
            )

    # Duplicate pricing rows / conflicting same maturity.
    for pid, rows in pricing_by_product.items():
        product = product_by_id.get(pid)
        if not product:
            continue

        groups = defaultdict(list)

        for row in rows:
            key = (
                norm_text(
                    row["pricing_variant"]
                    or "standart"
                ),
                row["maturity_months"],
            )
            groups[key].append(row)

        for (
            variant,
            maturity,
        ), group in groups.items():
            if len(group) <= 1:
                continue

            economic_signatures = {
                (
                    safe_float(
                        row["profit_share_rate"]
                    ),
                    safe_float(
                        row["allocation_fee_rate"]
                    ),
                    safe_float(
                        row["monthly_total_cost_rate"]
                    ),
                    safe_float(
                        row["annual_total_cost_rate"]
                    ),
                )
                for row in group
            }

            if len(economic_signatures) > 1:
                add(
                    "WARN",
                    "CONFLICTING_PRICING_ROWS",
                    bank=product["bank_name"],
                    product=product["product_name"],
                    product_id=pid,
                    detail=(
                        f"{variant} / {maturity} ay için "
                        f"{len(economic_signatures)} farklı "
                        "fiyatlama satırı var."
                    ),
                )

    # --------------------------------------------------------
    # 4) Fee rules vs pricing-table allocation fee
    # --------------------------------------------------------
    fee_rows = con.execute(
        """
        SELECT
            r.product_id,
            r.fee_type,
            r.fee_label,
            r.waived,
            r.amount,
            r.rate
        FROM live_product_fee_rules AS r
        JOIN live_campaigns AS c
          ON c.id=r.product_id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY r.product_id
        """
    ).fetchall()

    fees_by_product = defaultdict(list)

    for row in fee_rows:
        fees_by_product[
            int(row["product_id"])
        ].append(row)

    for pid, product in product_by_id.items():
        tiers = pricing_by_product.get(pid, [])
        fees = fees_by_product.get(pid, [])

        table_allocation = sorted({
            safe_float(
                row["allocation_fee_rate"]
            )
            for row in tiers
            if safe_float(
                row["allocation_fee_rate"]
            ) is not None
        })

        allocation_fees = [
            row
            for row in fees
            if norm_text(
                row["fee_type"]
            ) == "allocation"
            or "tahsis" in norm_text(
                row["fee_label"]
            )
        ]

        fee_allocation = sorted({
            safe_float(row["rate"])
            for row in allocation_fees
            if safe_float(row["rate"])
            is not None
        })

        # Pricing table has one unambiguous rate.
        if len(table_allocation) == 1:
            expected = table_allocation[0]

            if fee_allocation:
                wrong = [
                    value
                    for value in fee_allocation
                    if abs(
                        value - expected
                    ) > 1e-9
                ]

                if wrong:
                    add(
                        "ERROR",
                        "ALLOCATION_FEE_CONFLICT",
                        bank=product["bank_name"],
                        product=product["product_name"],
                        product_id=pid,
                        detail=(
                            "Fiyatlama tablosu tahsis "
                            f"%{expected}; fee_rules "
                            f"{fee_allocation}."
                        ),
                    )

            for fee in allocation_fees:
                if (
                    int(fee["waived"] or 0) == 1
                    and abs(expected) > 1e-9
                ):
                    add(
                        "ERROR",
                        "ALLOCATION_WAIVER_CONFLICT",
                        bank=product["bank_name"],
                        product=product["product_name"],
                        product_id=pid,
                        detail=(
                            "Fee rule 'alınmıyor' diyor "
                            "ama fiyatlama tablosu "
                            f"%{expected} gösteriyor."
                        ),
                    )

        # Heuristic: very high allocation fee. Not automatic error.
        for value in fee_allocation:
            if value > 5:
                add(
                    "WARN",
                    "SUSPICIOUS_HIGH_ALLOCATION_FEE",
                    bank=product["bank_name"],
                    product=product["product_name"],
                    product_id=pid,
                    detail=(
                        f"Tahsis ücreti %{value}. "
                        "Kaynakla manuel doğrulama önerilir."
                    ),
                )

    # --------------------------------------------------------
    # 5) Normalized child tables vs finance_rules_json
    # --------------------------------------------------------
    child_counts = {}

    for table, key in (
        (
            "live_product_category_rules",
            "category_rules",
        ),
        (
            "live_product_amount_maturity_rules",
            "amount_maturity_rules",
        ),
        (
            "live_product_pricing_tiers",
            "pricing_tiers",
        ),
        (
            "live_product_fee_rules",
            "fee_rules",
        ),
        (
            "live_product_offer_rules",
            "offer_rules",
        ),
    ):
        rows = con.execute(
            f"""
            SELECT product_id, COUNT(*) AS n
            FROM {table}
            GROUP BY product_id
            """
        ).fetchall()

        child_counts[key] = {
            int(row["product_id"]): int(row["n"])
            for row in rows
        }

    for pid, product in product_by_id.items():
        raw = product["finance_rules_json"]

        if not raw:
            continue

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            add(
                "ERROR",
                "INVALID_FINANCE_RULES_JSON",
                bank=product["bank_name"],
                product=product["product_name"],
                product_id=pid,
                detail=(
                    "finance_rules_json parse edilemiyor."
                ),
            )
            continue

        for key in (
            "category_rules",
            "amount_maturity_rules",
            "pricing_tiers",
            "fee_rules",
            "offer_rules",
        ):
            json_count = len(
                payload.get(key, []) or []
            )
            db_count = (
                child_counts
                .get(key, {})
                .get(pid, 0)
            )

            if json_count != db_count:
                add(
                    "ERROR",
                    "NORMALIZED_RULE_COUNT_MISMATCH",
                    bank=product["bank_name"],
                    product=product["product_name"],
                    product_id=pid,
                    detail=(
                        f"{key}: JSON={json_count}, "
                        f"DB={db_count}"
                    ),
                )

    # --------------------------------------------------------
    # 6) Amount-maturity rule sanity / overlap
    # --------------------------------------------------------
    amount_rules = con.execute(
        """
        SELECT
            r.product_id,
            r.min_amount,
            r.max_amount,
            r.min_inclusive,
            r.max_inclusive,
            r.max_maturity_months
        FROM live_product_amount_maturity_rules r
        JOIN live_campaigns c
          ON c.id=r.product_id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            r.product_id,
            CASE
              WHEN r.min_amount IS NULL THEN -1
              ELSE r.min_amount
            END
        """
    ).fetchall()

    amount_by_product = defaultdict(list)

    for row in amount_rules:
        pid = int(row["product_id"])
        amount_by_product[pid].append(row)

        product = product_by_id.get(pid)
        if not product:
            continue

        lo = safe_float(row["min_amount"])
        hi = safe_float(row["max_amount"])
        maturity = row[
            "max_maturity_months"
        ]

        if (
            lo is not None
            and hi is not None
            and lo > hi
        ):
            add(
                "ERROR",
                "INVALID_AMOUNT_BAND",
                bank=product["bank_name"],
                product=product["product_name"],
                product_id=pid,
                detail=(
                    f"Tutar bandı ters: "
                    f"{lo} → {hi}"
                ),
            )

        if (
            maturity is not None
            and not 1 <= int(maturity) <= 120
        ):
            add(
                "ERROR",
                "INVALID_AMOUNT_RULE_MATURITY",
                bank=product["bank_name"],
                product=product["product_name"],
                product_id=pid,
                detail=(
                    f"Tutar-vade kuralında "
                    f"şüpheli vade: {maturity}"
                ),
            )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------
    con.close()

    severity_order = {
        "ERROR": 0,
        "WARN": 1,
        "INFO": 2,
    }

    findings.sort(
        key=lambda row: (
            severity_order.get(
                row["severity"],
                9,
            ),
            norm_text(row["bank"]),
            norm_text(row["product"]),
            row["code"],
        )
    )

    counts = Counter(
        row["severity"]
        for row in findings
    )

    code_counts = Counter(
        row["code"]
        for row in findings
    )

    print("SONUÇ")
    print("-" * 100)
    print("ERROR :", counts.get("ERROR", 0))
    print("WARN  :", counts.get("WARN", 0))
    print("INFO  :", counts.get("INFO", 0))
    print()

    if not findings:
        print(
            "Şüpheli kayıt bulunamadı. ✅"
        )
    else:
        current_severity = None

        for row in findings:
            if (
                row["severity"]
                != current_severity
            ):
                current_severity = (
                    row["severity"]
                )
                print()
                print(
                    "=" * 100
                )
                print(current_severity)
                print(
                    "=" * 100
                )

            bank = (
                row["bank"]
                or "-"
            )
            product = (
                row["product"]
                or "-"
            )

            print(
                f"[{row['code']}] "
                f"{bank} | {product}"
            )
            print(
                f"  {row['detail']}"
            )

    report = {
        "generated_at": datetime.now().isoformat(),
        "database": str(DB),
        "active_standard_products": len(products),
        "summary": {
            "ERROR": counts.get("ERROR", 0),
            "WARN": counts.get("WARN", 0),
            "INFO": counts.get("INFO", 0),
        },
        "code_counts": dict(
            sorted(code_counts.items())
        ),
        "findings": findings,
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print(
        "JSON raporu:",
        REPORT_JSON,
    )
    print("=" * 100)

    # Audit hata buldu diye shell'i fail ettirmiyoruz.
    # Amaç önce raporu görmek.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
