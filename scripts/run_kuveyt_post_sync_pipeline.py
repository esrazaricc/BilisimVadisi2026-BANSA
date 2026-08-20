from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


@dataclass(frozen=True)
class PipelineStep:
    name: str
    script: str
    extra_args: tuple[str, ...] = ()


def build_steps(
    bank: str,
    audit_limit: int,
) -> list[PipelineStep]:
    common = ("--bank", bank)

    # Eski doğrulanmış Kuveyt Türk kayıtlarını yeniden sınıflandırmıyoruz.
    # Yalnızca canlı senkronizasyonda yeni gelen / sınıflandırılmamış
    # güncel kayıtlar genel sınıflandırıcıdan geçirilir.
    return [
        PipelineStep(
            "Yeni/güncel sınıflandırılmamış kayıtları sınıflandır",
            "classify_campaign_records.py",
            (*common, "--only-unclassified-current"),
        ),
        PipelineStep(
            "Doğrulanmış sınıflandırma düzeltmelerini uygula",
            "apply_campaign_classification_overrides.py",
            common,
        ),
        PipelineStep(
            "Sınıflandırmayı kontrol et",
            "check_kuveyt_classification_after_overrides.py",
            common,
        ),
        PipelineStep(
            "Karşılaştırma alanlarını çıkar",
            "extract_comparison_fields.py",
            common,
        ),
        PipelineStep(
            "Finansman ve kritik hedef kitle alanlarını kontrol et",
            "check_kuveyt_third_fixes.py",
            common,
        ),
        PipelineStep(
            "Son üç kampanya düzeltmesini kontrol et",
            "check_kuveyt_final_three.py",
            common,
        ),
        PipelineStep(
            "Finansman dışı kampanyaları denetle",
            "audit_kuveyt_nonfinance_extraction.py",
            (*common, "--limit", str(audit_limit)),
        ),
    ]


def validate_project_files(
    steps: Sequence[PipelineStep],
) -> None:
    missing = [
        PROJECT_ROOT / "scripts" / step.script
        for step in steps
        if not (
            PROJECT_ROOT / "scripts" / step.script
        ).exists()
    ]

    if missing:
        formatted = "\n".join(
            f"  - {path}"
            for path in missing
        )
        raise FileNotFoundError(
            "Gerekli script dosyaları eksik:\n"
            + formatted
        )


def create_database_backup(
    database: Path,
    backup_dir: Path,
) -> Path:
    if not database.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {database}"
        )

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    destination = backup_dir / (
        f"campaigns_before_kuveyt_pipeline_{timestamp}.db"
    )
    shutil.copy2(database, destination)
    return destination


def restore_database_backup(
    backup: Path,
    database: Path,
) -> None:
    if not backup.exists():
        raise FileNotFoundError(
            f"Geri yüklenecek yedek bulunamadı: {backup}"
        )

    database.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(backup, database)


def run_step(
    step_number: int,
    total_steps: int,
    step: PipelineStep,
    *,
    dry_run: bool,
) -> None:
    script_path = (
        PROJECT_ROOT
        / "scripts"
        / step.script
    )
    command = [
        sys.executable,
        str(script_path),
        *step.extra_args,
    ]

    print()
    print("=" * 80)
    print(
        f"[{step_number}/{total_steps}] "
        f"{step.name}"
    )
    print("Komut:", " ".join(command))
    print("=" * 80)

    if dry_run:
        return

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Adım başarısız oldu: {step.name} "
            f"(çıkış kodu {result.returncode})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Doğrulanmış Kuveyt Türk sınıflandırmasını "
            "bozmadan çıkarım ve kalite kontrollerini çalıştırır."
        )
    )
    parser.add_argument(
        "--bank",
        default="Kuveyt Türk",
    )
    parser.add_argument(
        "--audit-limit",
        type=int,
        default=40,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Komutları gösterir fakat çalıştırmaz.",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help=(
            "Yedeklemeyi ve hata halinde otomatik "
            "geri dönüşü kapatır."
        ),
    )
    args = parser.parse_args()

    if args.bank != "Kuveyt Türk":
        raise SystemExit(
            "Bu pipeline şu anda yalnızca Kuveyt Türk için "
            "doğrulanmıştır."
        )

    steps = build_steps(
        args.bank,
        args.audit_limit,
    )
    validate_project_files(steps)

    backup_path: Path | None = None
    if not args.dry_run and not args.skip_backup:
        backup_path = create_database_backup(
            args.db,
            args.backup_dir,
        )
        print("Pipeline öncesi veritabanı yedeği:")
        print(backup_path)

    try:
        for index, step in enumerate(
            steps,
            start=1,
        ):
            run_step(
                index,
                len(steps),
                step,
                dry_run=args.dry_run,
            )
    except Exception as exc:
        print()
        print("PIPELINE BAŞARISIZ")
        print(str(exc))

        if backup_path is not None:
            try:
                restore_database_backup(
                    backup_path,
                    args.db,
                )
                print(
                    "Veritabanı otomatik olarak pipeline "
                    "öncesi yedeğe döndürüldü:"
                )
                print(backup_path)
            except Exception as rollback_error:
                print(
                    "Otomatik geri dönüş de başarısız oldu:"
                )
                print(str(rollback_error))
                print("Elle geri dönüş için yedek:")
                print(backup_path)

        return 1

    print()
    print("=" * 80)
    if args.dry_run:
        print("DRY-RUN TAMAMLANDI")
    else:
        print(
            "KUVEYT TÜRK GÜVENLİ PIPELINE "
            "BAŞARIYLA TAMAMLANDI"
        )
        print("Doğrulanmış sonuçlar:")
        print("  - Yeni/unclassified güncel kayıtlar sınıflandırıldı.")
        print("  - Eski doğrulanmış kayıtlar topluca yeniden sınıflandırılmadı.")
        print("  - Güncel unclassified kayıt kalmadı.")
        print("  - Finansman detay sayısı güncel finance_campaign sayısıyla eşleşti.")
        print("  - Hedefli Kuveyt Türk kalite kontrolleri geçti.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())