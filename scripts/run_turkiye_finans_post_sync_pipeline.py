from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
DEFAULT_DB = ROOT / "data" / "campaigns.db"
DEFAULT_REPORT = (
    ROOT / "data" / "turkiye_finans_extraction_report.json"
)
DEFAULT_BANK = "Türkiye Finans"


@dataclass(frozen=True)
class Step:
    name: str
    script: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class QualitySummary:
    total_records: int
    campaign_records: int
    finance_campaigns: int
    finance_details: int
    benefits: int
    audiences: int
    unclassified_campaigns: int
    missing_nonfinance_benefits: int
    missing_audiences: int
    low_confidence_finance: int
    categories: dict[str, int]


class PipelineError(RuntimeError):
    pass


def build_steps(
    bank: str = DEFAULT_BANK,
    report_path: Path = DEFAULT_REPORT,
) -> list[Step]:
    return [
        Step(
            name="Türkiye Finans kayıtlarını sınıflandır",
            script="classify_campaign_records.py",
            args=("--bank", bank),
        ),
        Step(
            name="Doğrulanmış sınıflandırma override'larını uygula",
            script="apply_campaign_classification_overrides.py",
            args=("--bank", bank),
        ),
        Step(
            name="Karşılaştırma alanlarını çıkar",
            script="extract_comparison_fields.py",
            args=(
                "--bank",
                bank,
                "--report",
                str(report_path),
            ),
        ),
    ]


def ensure_required_files(
    db_path: Path,
    steps: Iterable[Step],
) -> None:
    missing: list[Path] = []

    if not db_path.exists():
        missing.append(db_path)

    for step in steps:
        script_path = SCRIPTS_DIR / step.script
        if not script_path.exists():
            missing.append(script_path)

    required_configs = (
        ROOT / "config" / "campaign_classification_overrides.json",
        ROOT / "config" / "finance_extraction_overrides.json",
    )

    for config_path in required_configs:
        if not config_path.exists():
            missing.append(config_path)

    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise PipelineError(
            "Gerekli dosyalar bulunamadı:\n" + formatted
        )


def sqlite_backup(
    source_path: Path,
    destination_path: Path,
) -> None:
    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if destination_path.exists():
        destination_path.unlink()

    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)

    try:
        source.execute("PRAGMA wal_checkpoint(FULL)")
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def sqlite_restore(
    backup_path: Path,
    destination_path: Path,
) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(destination_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    source = sqlite3.connect(backup_path)
    destination = sqlite3.connect(destination_path)

    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]


def table_exists(
    connection: sqlite3.Connection,
    table: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table,),
    ).fetchone()

    return row is not None


def rows_digest(
    rows: Iterable[sqlite3.Row],
) -> str:
    """Return an order-independent digest for SQLite rows."""
    payloads = [
        json.dumps(
            list(row),
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        for row in rows
    ]

    digest = hashlib.sha256()

    for payload in sorted(payloads):
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")

    return digest.hexdigest()


def other_banks_fingerprint(
    db_path: Path,
    target_bank: str,
) -> dict[str, str]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    fingerprints: dict[str, str] = {}

    try:
        campaign_columns = table_columns(
            connection,
            "live_campaigns",
        )
        campaign_select = ", ".join(
            f"c.{column}"
            for column in campaign_columns
        )

        campaign_rows = connection.execute(
            f"""
            SELECT {campaign_select}
            FROM live_campaigns AS c
            WHERE c.bank_name != ?
            ORDER BY c.id
            """,
            (target_bank,),
        ).fetchall()

        fingerprints["live_campaigns"] = rows_digest(
            campaign_rows
        )

        dependent_tables = (
            "live_campaign_finance_details",
            "live_campaign_benefits",
            "live_campaign_audiences",
        )

        for table in dependent_tables:
            if not table_exists(connection, table):
                fingerprints[table] = "missing"
                continue

            columns = table_columns(connection, table)
            campaign_column = next(
                (
                    name
                    for name in (
                        "campaign_id",
                        "live_campaign_id",
                    )
                    if name in columns
                ),
                None,
            )

            if campaign_column is None:
                fingerprints[table] = "no_campaign_column"
                continue

            select_columns = ", ".join(
                f"d.{column}"
                for column in columns
            )
            rows = connection.execute(
                f"""
                SELECT {select_columns}
                FROM {table} AS d
                JOIN live_campaigns AS c
                  ON c.id = d.{campaign_column}
                WHERE c.bank_name != ?
                """,
                (target_bank,),
            ).fetchall()

            fingerprints[table] = rows_digest(rows)

    finally:
        connection.close()

    return fingerprints


def run_step(
    step: Step,
    timeout_seconds: int,
) -> str:
    script_path = SCRIPTS_DIR / step.script
    command = [
        sys.executable,
        str(script_path),
        *step.args,
    ]

    print()
    print("=" * 88)
    print("ADIM:", step.name)
    print(
        "KOMUT:",
        " ".join(
            f'"{part}"' if " " in part else part
            for part in command
        ),
    )
    print("=" * 88)

    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )

    output_parts = []

    if result.stdout:
        print(result.stdout, end="")
        output_parts.append(result.stdout)

    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
        output_parts.append(result.stderr)

    if result.returncode != 0:
        raise PipelineError(
            f"{step.script} başarısız oldu. "
            f"Çıkış kodu: {result.returncode}"
        )

    return "".join(output_parts)


def scalar(
    connection: sqlite3.Connection,
    query: str,
    params: tuple[object, ...] = (),
) -> int:
    value = connection.execute(
        query,
        params,
    ).fetchone()[0]

    return int(value or 0)


def category_counts(
    connection: sqlite3.Connection,
    bank: str,
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT
            COALESCE(campaign_category, 'NULL') AS category,
            COUNT(*) AS count
        FROM live_campaigns
        WHERE bank_name = ?
        GROUP BY COALESCE(campaign_category, 'NULL')
        ORDER BY category
        """,
        (bank,),
    ).fetchall()

    return {
        str(row["category"]): int(row["count"])
        for row in rows
    }


def finance_campaign_column(
    connection: sqlite3.Connection,
) -> str:
    columns = table_columns(
        connection,
        "live_campaign_finance_details",
    )

    column = next(
        (
            name
            for name in (
                "campaign_id",
                "live_campaign_id",
            )
            if name in columns
        ),
        None,
    )

    if column is None:
        raise PipelineError(
            "Finansman detay tablosunda kampanya bağlantı "
            "sütunu bulunamadı."
        )

    return column


def validate_known_finance_records(
    connection: sqlite3.Connection,
    bank: str,
) -> list[str]:
    errors: list[str] = []
    campaign_column = finance_campaign_column(connection)

    checks = (
        {
            "path": "banka-calisanlarina-ozel-ihtiyac-finansmani",
            "amount_min": 1000.0,
            "amount_max": 1000000.0,
            "maturity_min": 3,
            "maturity_max": 36,
            "profit_min": 3.96,
            "profit_max": 5.06,
            "allocation_rate": 0.50,
        },
        {
            "path": "kamu-calisanlarina-ozel-ihtiyac-finansmani",
            "amount_min": 50000.0,
            "amount_max": 400000.0,
            "maturity_min": 3,
            "maturity_max": 36,
            "profit_min": 4.01,
            "profit_max": 5.26,
            "allocation_rate": 0.50,
        },
        {
            "path": "ihtiyac-finansmani-kampanyasi",
            "amount_min": 50000.0,
            "amount_max": 50000.0,
            "maturity_min": 3,
            "maturity_max": 3,
            "profit_min": 0.0,
            "profit_max": 0.0,
            "allocation_rate": None,
        },
    )

    for check in checks:
        row = connection.execute(
            f"""
            SELECT
                f.financing_amount_min,
                f.financing_amount_max,
                f.maturity_min_months,
                f.maturity_max_months,
                f.profit_share_rate_min,
                f.profit_share_rate_max,
                f.allocation_fee_rate,
                f.extraction_confidence
            FROM live_campaigns AS c
            JOIN live_campaign_finance_details AS f
              ON f.{campaign_column} = c.id
            WHERE c.bank_name = ?
              AND c.source_url LIKE ?
            """,
            (
                bank,
                f"%{check['path']}%",
            ),
        ).fetchone()

        if row is None:
            errors.append(
                "Doğrulanmış finansman kaydı bulunamadı: "
                + check["path"]
            )
            continue

        numeric_fields = (
            ("financing_amount_min", "amount_min"),
            ("financing_amount_max", "amount_max"),
            ("maturity_min_months", "maturity_min"),
            ("maturity_max_months", "maturity_max"),
            ("profit_share_rate_min", "profit_min"),
            ("profit_share_rate_max", "profit_max"),
        )

        for db_field, expected_field in numeric_fields:
            actual = row[db_field]
            expected = check[expected_field]

            if actual is None or abs(float(actual) - float(expected)) > 0.001:
                errors.append(
                    f"{check['path']} | {db_field}: "
                    f"beklenen {expected}, bulunan {actual}"
                )

        actual_allocation = row["allocation_fee_rate"]
        expected_allocation = check["allocation_rate"]

        if expected_allocation is None:
            if actual_allocation is not None:
                errors.append(
                    f"{check['path']} | allocation_fee_rate "
                    f"None olmalı, bulunan {actual_allocation}"
                )
        elif (
            actual_allocation is None
            or abs(
                float(actual_allocation)
                - float(expected_allocation)
            )
            > 0.001
        ):
            errors.append(
                f"{check['path']} | allocation_fee_rate: "
                f"beklenen {expected_allocation}, "
                f"bulunan {actual_allocation}"
            )

        confidence = row["extraction_confidence"]

        if confidence is None or float(confidence) < 1.0:
            errors.append(
                f"{check['path']} | extraction_confidence "
                f"1.0 olmalı, bulunan {confidence}"
            )

    return errors


def validate_known_nonfinance_records(
    connection: sqlite3.Connection,
    bank: str,
) -> list[str]:
    errors: list[str] = []

    benefit_count = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM live_campaigns AS c
        JOIN live_campaign_benefits AS b
          ON b.campaign_id = c.id
        WHERE c.bank_name = ?
          AND c.source_url LIKE '%pasaport-harci%'
          AND b.benefit_type = 'installment'
          AND b.description = '3 taksit'
        """,
        (bank,),
    )

    if benefit_count != 1:
        errors.append(
            "Pasaport harcı kampanyasında tek bir "
            "'3 taksit' avantajı bulunmalı."
        )

    audience_checks = (
        (
            "asistanlik-hizmetleri-2026",
            "Âlâ Kart Sahipleri",
        ),
        (
            "ala-yolcu360-nisan-2026",
            "Bireysel Âlâ Kart Sahipleri",
        ),
        (
            "ala-bes-2026",
            "Âlâ Bankacılık Müşterileri",
        ),
        (
            "ala-hgs-2026",
            "Âlâ Kart Sahipleri",
        ),
    )

    for url_path, expected_label in audience_checks:
        count = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaigns AS c
            JOIN live_campaign_audiences AS a
              ON a.campaign_id = c.id
            WHERE c.bank_name = ?
              AND c.source_url LIKE ?
              AND a.audience_label = ?
            """,
            (
                bank,
                f"%{url_path}%",
                expected_label,
            ),
        )

        if count != 1:
            errors.append(
                f"{url_path} için hedef kitle bulunamadı: "
                f"{expected_label}"
            )

    return errors


def validate_quality(
    db_path: Path,
    bank: str,
    minimum_campaigns: int,
    minimum_finance_campaigns: int,
    minimum_finance_confidence: float,
) -> QualitySummary:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    errors: list[str] = []

    try:
        required_tables = (
            "live_campaigns",
            "live_campaign_finance_details",
            "live_campaign_benefits",
            "live_campaign_audiences",
        )

        missing_tables = [
            table
            for table in required_tables
            if not table_exists(connection, table)
        ]

        if missing_tables:
            raise PipelineError(
                "Kalite kontrolü için tablolar eksik: "
                + ", ".join(missing_tables)
            )

        campaign_column = finance_campaign_column(connection)

        total_records = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
            """,
            (bank,),
        )
        campaign_records = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
              AND record_kind = 'campaign'
            """,
            (bank,),
        )
        finance_campaigns = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
              AND record_kind = 'campaign'
              AND campaign_category = 'finance_campaign'
            """,
            (bank,),
        )
        finance_details = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM live_campaign_finance_details AS f
            JOIN live_campaigns AS c
              ON c.id = f.{campaign_column}
            WHERE c.bank_name = ?
              AND c.record_kind = 'campaign'
              AND c.campaign_category = 'finance_campaign'
            """,
            (bank,),
        )
        benefits = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaign_benefits AS b
            JOIN live_campaigns AS c
              ON c.id = b.campaign_id
            WHERE c.bank_name = ?
            """,
            (bank,),
        )
        audiences = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaign_audiences AS a
            JOIN live_campaigns AS c
              ON c.id = a.campaign_id
            WHERE c.bank_name = ?
            """,
            (bank,),
        )
        unclassified_campaigns = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
              AND (
                  record_kind IN (
                      'unclassified',
                      'needs_review'
                  )
                  OR (
                      record_kind = 'campaign'
                      AND (
                          campaign_category IS NULL
                          OR campaign_category = ''
                          OR campaign_category = 'unclassified'
                      )
                  )
              )
            """,
            (bank,),
        )
        missing_nonfinance_benefits = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM (
                SELECT c.id
                FROM live_campaigns AS c
                LEFT JOIN live_campaign_benefits AS b
                  ON b.campaign_id = c.id
                WHERE c.bank_name = ?
                  AND c.record_kind = 'campaign'
                  AND c.campaign_category != 'finance_campaign'
                GROUP BY c.id
                HAVING COUNT(b.id) = 0
            )
            """,
            (bank,),
        )
        missing_audiences = scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM (
                SELECT c.id
                FROM live_campaigns AS c
                LEFT JOIN live_campaign_audiences AS a
                  ON a.campaign_id = c.id
                WHERE c.bank_name = ?
                  AND c.record_kind = 'campaign'
                GROUP BY c.id
                HAVING COUNT(a.id) = 0
            )
            """,
            (bank,),
        )
        low_confidence_finance = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM live_campaign_finance_details AS f
            JOIN live_campaigns AS c
              ON c.id = f.{campaign_column}
            WHERE c.bank_name = ?
              AND c.record_kind = 'campaign'
              AND c.campaign_category = 'finance_campaign'
              AND (
                  f.extraction_confidence IS NULL
                  OR f.extraction_confidence < ?
              )
            """,
            (
                bank,
                minimum_finance_confidence,
            ),
        )

        categories = category_counts(connection, bank)

        if total_records < minimum_campaigns:
            errors.append(
                f"Toplam kayıt {total_records}; en az "
                f"{minimum_campaigns} olmalı."
            )

        if campaign_records < minimum_campaigns:
            errors.append(
                f"Kampanya kaydı {campaign_records}; en az "
                f"{minimum_campaigns} olmalı."
            )

        if finance_campaigns < minimum_finance_campaigns:
            errors.append(
                f"Finansman kampanyası {finance_campaigns}; "
                f"en az {minimum_finance_campaigns} olmalı."
            )

        if finance_details != finance_campaigns:
            errors.append(
                "Finansman kampanyası ve finansman detay "
                f"sayısı eşleşmiyor: {finance_campaigns} / "
                f"{finance_details}"
            )

        if unclassified_campaigns:
            errors.append(
                f"Sınıflandırılmamış/kontrollük kayıt: "
                f"{unclassified_campaigns}"
            )

        if missing_nonfinance_benefits:
            errors.append(
                "Finansman dışı avantajı olmayan kampanya: "
                f"{missing_nonfinance_benefits}"
            )

        if missing_audiences:
            errors.append(
                f"Hedef kitlesi olmayan kampanya: "
                f"{missing_audiences}"
            )

        if low_confidence_finance:
            errors.append(
                "Doğrulanmamış finansman kaydı: "
                f"{low_confidence_finance}"
            )

        errors.extend(
            validate_known_finance_records(
                connection,
                bank,
            )
        )
        errors.extend(
            validate_known_nonfinance_records(
                connection,
                bank,
            )
        )

        summary = QualitySummary(
            total_records=total_records,
            campaign_records=campaign_records,
            finance_campaigns=finance_campaigns,
            finance_details=finance_details,
            benefits=benefits,
            audiences=audiences,
            unclassified_campaigns=unclassified_campaigns,
            missing_nonfinance_benefits=(
                missing_nonfinance_benefits
            ),
            missing_audiences=missing_audiences,
            low_confidence_finance=low_confidence_finance,
            categories=categories,
        )

        if errors:
            formatted = "\n".join(
                f"- {error}"
                for error in errors
            )
            raise PipelineError(
                "Kalite kontrolü başarısız:\n" + formatted
            )

        return summary

    finally:
        connection.close()


def print_quality_summary(
    summary: QualitySummary,
) -> None:
    print()
    print("=" * 88)
    print("TÜRKİYE FİNANS KALİTE ÖZETİ")
    print("=" * 88)
    print("Toplam kayıt:", summary.total_records)
    print("Kampanya kaydı:", summary.campaign_records)
    print("Finansman kampanyası:", summary.finance_campaigns)
    print("Finansman detayı:", summary.finance_details)
    print("Avantaj kaydı:", summary.benefits)
    print("Hedef kitle kaydı:", summary.audiences)
    print(
        "Sınıflandırılmamış kayıt:",
        summary.unclassified_campaigns,
    )
    print(
        "Finansman dışı avantaj eksiği:",
        summary.missing_nonfinance_benefits,
    )
    print(
        "Hedef kitle eksiği:",
        summary.missing_audiences,
    )
    print(
        "Doğrulanmamış finansman:",
        summary.low_confidence_finance,
    )
    print("Kategoriler:")

    for category, count in summary.categories.items():
        print(f"  - {category}: {count}")


def write_log(
    log_path: Path,
    bank: str,
    backup_path: Path,
    step_outputs: list[tuple[Step, str]],
    summary: QualitySummary | None,
    status: str,
    error: str | None = None,
) -> None:
    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = [
        f"Zaman: {datetime.now().isoformat(timespec='seconds')}",
        f"Banka: {bank}",
        f"Durum: {status}",
        f"Veritabanı yedeği: {backup_path}",
    ]

    if error:
        lines.append(f"Hata: {error}")

    for step, output in step_outputs:
        lines.extend(
            [
                "",
                "=" * 88,
                f"ADIM: {step.name}",
                f"SCRIPT: {step.script}",
                "=" * 88,
                output.rstrip(),
            ]
        )

    if summary is not None:
        lines.extend(
            [
                "",
                "=" * 88,
                "KALİTE ÖZETİ",
                "=" * 88,
                json.dumps(
                    {
                        "total_records": summary.total_records,
                        "campaign_records": (
                            summary.campaign_records
                        ),
                        "finance_campaigns": (
                            summary.finance_campaigns
                        ),
                        "finance_details": (
                            summary.finance_details
                        ),
                        "benefits": summary.benefits,
                        "audiences": summary.audiences,
                        "unclassified_campaigns": (
                            summary.unclassified_campaigns
                        ),
                        "missing_nonfinance_benefits": (
                            summary.missing_nonfinance_benefits
                        ),
                        "missing_audiences": (
                            summary.missing_audiences
                        ),
                        "low_confidence_finance": (
                            summary.low_confidence_finance
                        ),
                        "categories": summary.categories,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )

    log_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Türkiye Finans post-sync sınıflandırma, "
            "override, çıkarım ve kalite kontrol akışını "
            "güvenli biçimde çalıştırır."
        )
    )
    parser.add_argument(
        "--bank",
        default=DEFAULT_BANK,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Her bir adım için saniye cinsinden süre.",
    )
    parser.add_argument(
        "--minimum-campaigns",
        type=int,
        default=49,
    )
    parser.add_argument(
        "--minimum-finance-campaigns",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--minimum-finance-confidence",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Komutları gösterir, veritabanını değiştirmez.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.resolve()
    report_path = args.report.resolve()
    steps = build_steps(
        bank=args.bank,
        report_path=report_path,
    )

    ensure_required_files(db_path, steps)

    print("Türkiye Finans güvenli post-sync pipeline")
    print("Proje:", ROOT)
    print("Banka:", args.bank)
    print("Veritabanı:", db_path)
    print("Rapor:", report_path)
    print("Adımlar:")

    for index, step in enumerate(steps, start=1):
        print(
            f"  {index}. {step.script} "
            + " ".join(step.args)
        )

    if args.dry_run:
        print()
        print("Dry-run tamamlandı; değişiklik yapılmadı.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        ROOT
        / "data"
        / "backups"
        / f"campaigns_before_tf_post_sync_{timestamp}.db"
    )
    log_path = (
        ROOT
        / "data"
        / "logs"
        / f"turkiye_finans_post_sync_{timestamp}.log"
    )

    sqlite_backup(db_path, backup_path)
    print("Güvenlik yedeği:", backup_path)

    step_outputs: list[tuple[Step, str]] = []
    summary: QualitySummary | None = None

    try:
        before_other_banks = other_banks_fingerprint(
            db_path,
            args.bank,
        )

        for step in steps:
            output = run_step(
                step,
                timeout_seconds=args.timeout,
            )
            step_outputs.append((step, output))

        after_other_banks = other_banks_fingerprint(
            db_path,
            args.bank,
        )

        if before_other_banks != after_other_banks:
            changed = [
                table
                for table in before_other_banks
                if (
                    before_other_banks.get(table)
                    != after_other_banks.get(table)
                )
            ]
            raise PipelineError(
                "Türkiye Finans dışındaki banka verileri "
                "değişti: "
                + ", ".join(changed)
            )

        summary = validate_quality(
            db_path=db_path,
            bank=args.bank,
            minimum_campaigns=args.minimum_campaigns,
            minimum_finance_campaigns=(
                args.minimum_finance_campaigns
            ),
            minimum_finance_confidence=(
                args.minimum_finance_confidence
            ),
        )
        print_quality_summary(summary)

        write_log(
            log_path=log_path,
            bank=args.bank,
            backup_path=backup_path,
            step_outputs=step_outputs,
            summary=summary,
            status="SUCCESS",
        )

        print()
        print("Pipeline başarıyla tamamlandı.")
        print("Yedek:", backup_path)
        print("Log:", log_path)
        return 0

    except Exception as error:
        print()
        print("HATA:", error, file=sys.stderr)
        print(
            "Veritabanı güvenlik yedeğinden geri yükleniyor...",
            file=sys.stderr,
        )

        sqlite_restore(backup_path, db_path)

        write_log(
            log_path=log_path,
            bank=args.bank,
            backup_path=backup_path,
            step_outputs=step_outputs,
            summary=summary,
            status="FAILED_ROLLED_BACK",
            error=str(error),
        )

        print(
            "Geri yükleme tamamlandı.",
            file=sys.stderr,
        )
        print("Yedek:", backup_path, file=sys.stderr)
        print("Log:", log_path, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
