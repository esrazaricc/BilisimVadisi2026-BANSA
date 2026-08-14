from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("\n>", " ".join(command))
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def slug(value: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return "_".join(value.translate(table).casefold().split())


def post_process(bank: str) -> None:
    # Kuveyt Türk'te genel classifier doğrulanmış dağılımı bozabildiği için
    # bankaya özel post-sync pipeline kullanılır.
    special = {
        "Dünya Katılım": ["scripts/run_dunya_katilim_post_sync_pipeline.py"],
        "Kuveyt Türk": [
            "scripts/run_kuveyt_post_sync_pipeline.py",
            "--bank",
            "Kuveyt Türk",
        ],
        "Türkiye Finans": [
            "scripts/run_turkiye_finans_post_sync_pipeline.py",
            "--bank",
            "Türkiye Finans",
        ],
        "Ziraat Katılım": ["scripts/run_ziraat_katilim_post_sync_pipeline.py"],
    }

    if bank in special:
        run([sys.executable, *special[bank]])
        return

    run([sys.executable, "scripts/classify_campaign_records.py", "--bank", bank])
    run([
        sys.executable,
        "scripts/apply_campaign_classification_overrides.py",
        "--bank",
        bank,
    ])

    if bank == "Albaraka Türk":
        extractor = "scripts/extract_comparison_fields_albaraka_guardrail.py"
        report = "data/albaraka_comparison_extraction_report.json"
    else:
        extractor = "scripts/extract_comparison_fields.py"
        report = f"data/{slug(bank)}_comparison_extraction_report.json"

    run([
        sys.executable,
        extractor,
        "--bank",
        bank,
        "--report",
        report,
    ])

    if bank == "Albaraka Türk":
        run([sys.executable, "scripts/apply_albaraka_finance_type_overrides.py"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bir bankayı canlı yeniler, DB'ye güvenli senkronize eder ve "
            "Streamlit'in kullandığı sınıflandırma/karşılaştırma alanlarını "
            "aynı çalışmada yeniden üretir."
        )
    )
    parser.add_argument("--bank", required=True)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--allow-immediate-removal",
        action="store_true",
        help=(
            "Eski davranış: tek başarılı keşifte listede olmayan URL'leri "
            "hemen removed yapar. Önerilmez."
        ),
    )
    args = parser.parse_args()

    if args.bank == "Hayat Finans":
        command = [
            sys.executable,
            "scripts/run_hayat_finans_live_refresh.py",
            "--delay",
            str(args.delay),
        ]
    else:
        command = [
            sys.executable,
            "scripts/refresh_live_campaigns.py",
            "--bank",
            args.bank,
            "--delay",
            str(args.delay),
        ]
    if args.headed:
        command.append("--headed")
    run(command)

    if args.bank == "Hayat Finans":
        run([
            sys.executable,
            "scripts/run_hayat_finans_post_sync_pipeline.py",
            "--skip-refresh",
        ])
    else:
        sync_command = [
            sys.executable,
            "scripts/sync_campaigns_to_db.py",
            "--bank",
            args.bank,
        ]
        if not args.allow_immediate_removal:
            sync_command.append("--no-mark-removed")
        run(sync_command)
        post_process(args.bank)

    if not args.allow_immediate_removal:
        run([
            sys.executable,
            "scripts/safe_campaign_removals.py",
            "--bank",
            args.bank,
        ])

    print(
        "\nCanlı yenileme, DB senkronizasyonu, sınıflandırma, "
        "karşılaştırma alanları ve güvenli kaldırma kontrolü tamamlandı."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
