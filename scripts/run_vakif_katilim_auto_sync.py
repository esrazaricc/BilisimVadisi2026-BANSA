from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BANK = "Vakıf Katılım"
LOCK_PATH = PROJECT_ROOT / "data" / "vakif_katilim_sync.lock"
LOG_PATH = PROJECT_ROOT / "data" / "logs" / "vakif_katilim_auto_sync.log"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {message}\n")


def run(command: list[str]) -> None:
    append_log("Çalıştırılıyor: " + " ".join(command))
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        append_log("STDOUT:\n" + result.stdout.strip())
    if result.stderr:
        append_log("STDERR:\n" + result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"Komut başarısız oldu ({result.returncode}): "
            + " ".join(command)
        )


def extraction_supports_bank(script_path: Path) -> bool:
    if not script_path.exists():
        return False
    content = script_path.read_text(encoding="utf-8", errors="replace")
    return '"--bank"' in content or "'--bank'" in content


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Vakıf Katılım kampanyalarını keşfeder, detaylarını çeker, "
            "veritabanına senkronize eder ve dashboard verisini günceller."
        )
    )
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Karşılaştırma alanı çıkarımını çalıştırmaz.",
    )
    args = parser.parse_args()

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        age_seconds = (
            datetime.now().timestamp() - LOCK_PATH.stat().st_mtime
        )
        if age_seconds < 7200:
            append_log(
                "Başka bir senkronizasyon çalışıyor göründüğü için atlandı."
            )
            return 0
        LOCK_PATH.unlink(missing_ok=True)

    LOCK_PATH.write_text(now_iso(), encoding="utf-8")

    try:
        append_log("Vakıf Katılım senkronizasyonu başladı.")

        run(
            [
                sys.executable,
                "scripts/refresh_and_sync_campaigns.py",
                "--bank",
                BANK,
                "--delay",
                str(args.delay),
            ]
        )

        extraction_script = (
            PROJECT_ROOT / "scripts" / "extract_comparison_fields.py"
        )
        if (
            not args.skip_extraction
            and extraction_supports_bank(extraction_script)
        ):
            run(
                [
                    sys.executable,
                    str(extraction_script.relative_to(PROJECT_ROOT)),
                    "--bank",
                    BANK,
                ]
            )
        else:
            append_log(
                "Karşılaştırma alanı çıkarımı yok veya --bank desteklemiyor; "
                "ana kampanya senkronizasyonu tamamlandı."
            )

        append_log("Vakıf Katılım senkronizasyonu başarıyla tamamlandı.")
        return 0
    except Exception as error:
        append_log(
            f"SENKRONİZASYON HATASI: {type(error).__name__}: {error}"
        )
        print(f"Hata: {error}", file=sys.stderr)
        return 1
    finally:
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
