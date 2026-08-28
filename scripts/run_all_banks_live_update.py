from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import canonicalize_url, ensure_schema
from src.scraping.campaign_discovery import load_bank_config

DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "banks.json"
DISCOVERY_PATH = PROJECT_ROOT / "data" / "discovered_campaign_pages.json"
REPORT_PATH = PROJECT_ROOT / "data" / "all_banks_live_update_report.json"
LOG_PATH = PROJECT_ROOT / "data" / "logs" / "all_banks_live_update.log"
LOCK_PATH = PROJECT_ROOT / "data" / "all_banks_live_update.lock"
BACKUP_ROOT = PROJECT_ROOT / "data" / "backups" / "all_banks_live_update"
STATE_PATH = PROJECT_ROOT / "data" / "campaign_missing_state.json"

SPECIAL_REFRESH = {
    "Hayat Finans": "run_hayat_finans_live_refresh.py",
}

SPECIAL_POST = {
    "Dünya Katılım": ["run_dunya_katilim_post_sync_pipeline.py"],
    "Hayat Finans": ["run_hayat_finans_post_sync_pipeline.py", "--skip-refresh"],
    "Kuveyt Türk": ["run_kuveyt_post_sync_pipeline.py", "--bank", "Kuveyt Türk"],
    "Türkiye Finans": ["run_turkiye_finans_post_sync_pipeline.py", "--bank", "Türkiye Finans"],
    "Ziraat Katılım": ["run_ziraat_katilim_post_sync_pipeline.py"],
}


@dataclass
class BankResult:
    bank_name: str
    status: str
    started_at: str
    finished_at: str = ""
    previous_current: int = 0
    discovered: int = 0
    current_after: int = 0
    visible_campaigns: int = 0
    created: int = 0
    content_changed: int = 0
    pending_removal: int = 0
    removed: int = 0
    expired: int = 0
    backup_path: str = ""
    message: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] {message}\n")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception:
            return False
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> str:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        pid = int(payload.get("pid") or 0)
        if pid and _process_exists(pid):
            raise RuntimeError(
                f"Başka bir tüm-bankalar güncellemesi çalışıyor (PID={pid})."
            )
        LOCK_PATH.unlink(missing_ok=True)

    token = f"{os.getpid()}-{time.time_ns()}"
    payload = {
        "pid": os.getpid(),
        "token": token,
        "started_at": utc_now(),
    }
    descriptor = os.open(
        str(LOCK_PATH),
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
    )
    try:
        os.write(
            descriptor,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    finally:
        os.close(descriptor)
    return token


def release_lock(token: str) -> None:
    if not LOCK_PATH.exists():
        return
    try:
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    if payload.get("token") == token and int(payload.get("pid") or 0) == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def slug(value: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return "_".join(value.translate(table).casefold().split())


def run(command: list[str], label: str) -> str:
    append_log(f"{label}: {' '.join(command)}")

    # Windows'ta alt Python süreçleri sistemin cp1254/charmap
    # kodlamasını kullanırsa kampanya başlıklarındaki emoji ve bazı
    # Unicode karakterleri yazdırırken UnicodeEncodeError oluşabilir.
    # Tüm alt süreçleri UTF-8'e zorlayarak gerçek bir fetch işleminin
    # yalnızca konsol çıktısı yüzünden FAILED sayılmasını engelliyoruz.
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env,
    )
    if completed.stdout:
        append_log(label + " STDOUT:\n" + completed.stdout.strip())
    if completed.stderr:
        append_log(label + " STDERR:\n" + completed.stderr.strip())
    if completed.returncode != 0:
        # Hata ayrıntısını yalnızca loga gömmek yerine konsolda da göster.
        if completed.stdout:
            print("\n---", label, "STDOUT ---")
            print(completed.stdout.strip())
        if completed.stderr:
            print("\n---", label, "STDERR ---")
            print(completed.stderr.strip())
        detail = (
            (completed.stderr or completed.stdout or "")
            .strip()
            .splitlines()
        )
        tail = detail[-1] if detail else ""
        suffix = f" Son mesaj: {tail}" if tail else ""
        raise RuntimeError(
            f"{label} başarısız oldu (kod={completed.returncode}).{suffix}"
        )
    return completed.stdout


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
    finally:
        source_conn.close()
        destination_conn.close()


def restore_db(backup: Path) -> None:
    source_conn = sqlite3.connect(backup)
    destination_conn = sqlite3.connect(DB_PATH)
    try:
        source_conn.backup(destination_conn)
    finally:
        source_conn.close()
        destination_conn.close()


def db_counts(bank_name: str) -> dict[str, int]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        ensure_schema(connection)
        current = connection.execute(
            "SELECT COUNT(*) FROM live_campaigns WHERE bank_name=? AND is_current=1",
            (bank_name,),
        ).fetchone()[0]
        visible = connection.execute(
            """
            SELECT COUNT(*) FROM live_campaigns
            WHERE bank_name=? AND is_current=1 AND record_kind='campaign'
            """,
            (bank_name,),
        ).fetchone()[0]
        return {"current": int(current or 0), "visible": int(visible or 0)}
    finally:
        connection.close()


def discovery_urls(bank_name: str) -> set[str]:
    try:
        rows = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
    except Exception:
        rows = []
    if not isinstance(rows, list):
        return set()
    return {
        canonicalize_url(row.get("url"))
        for row in rows
        if isinstance(row, dict)
        and row.get("bank_name") == bank_name
        and canonicalize_url(row.get("url"))
    }


def scanner_ready_banks() -> list[str]:
    banks = load_bank_config(CONFIG_PATH)
    return [
        str(bank["name"])
        for bank in banks
        if bank.get("scanner_ready") is True
    ]


def refresh_bank(bank_name: str, delay: float, headed: bool) -> None:
    special = SPECIAL_REFRESH.get(bank_name)
    if special:
        command = [
            sys.executable,
            f"scripts/{special}",
            "--delay",
            str(delay),
        ]
    else:
        command = [
            sys.executable,
            "scripts/refresh_live_campaigns.py",
            "--bank",
            bank_name,
            "--delay",
            str(delay),
        ]
    if headed:
        command.append("--headed")
    run(command, f"{bank_name} canlı keşif/fetch")


def sync_bank_without_removal(bank_name: str) -> dict[str, Any]:
    run(
        [
            sys.executable,
            "scripts/sync_campaigns_to_db.py",
            "--bank",
            bank_name,
            "--no-mark-removed",
        ],
        f"{bank_name} güvenli DB senkronizasyonu",
    )
    report_path = PROJECT_ROOT / "data" / "live_db_sync_report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        report = {}
    return report if isinstance(report, dict) else {}


def generic_post(bank_name: str) -> None:
    run(
        [sys.executable, "scripts/classify_campaign_records.py", "--bank", bank_name],
        f"{bank_name} sınıflandırma",
    )
    run(
        [
            sys.executable,
            "scripts/apply_campaign_classification_overrides.py",
            "--bank",
            bank_name,
        ],
        f"{bank_name} sınıflandırma override",
    )

    if bank_name == "Albaraka Türk":
        extractor = "scripts/extract_comparison_fields_albaraka_guardrail.py"
        report = "data/albaraka_comparison_extraction_report.json"
    else:
        extractor = "scripts/extract_comparison_fields.py"
        report = f"data/{slug(bank_name)}_comparison_extraction_report.json"

    run(
        [
            sys.executable,
            extractor,
            "--bank",
            bank_name,
            "--report",
            report,
        ],
        f"{bank_name} karşılaştırma alanları",
    )

    if bank_name == "Albaraka Türk":
        run(
            [sys.executable, "scripts/apply_albaraka_finance_type_overrides.py"],
            "Albaraka Türk finansman türü doğrulaması",
        )


def post_process(bank_name: str) -> None:
    special = SPECIAL_POST.get(bank_name)
    if special:
        run(
            [sys.executable, "scripts/" + special[0], *special[1:]],
            f"{bank_name} post-sync kalite pipeline",
        )
        return
    generic_post(bank_name)


def safe_removal(bank_name: str, confirm_after: int) -> dict[str, Any]:
    report = PROJECT_ROOT / "data" / f"{slug(bank_name)}_safe_removal_report.json"
    run(
        [
            sys.executable,
            "scripts/safe_campaign_removals.py",
            "--bank",
            bank_name,
            "--confirm-after",
            str(confirm_after),
            "--report",
            str(report.relative_to(PROJECT_ROOT)),
        ],
        f"{bank_name} güvenli kaldırma kontrolü",
    )
    try:
        value = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        value = {}
    return value if isinstance(value, dict) else {}


def validate_bank(bank_name: str, expected_discovered: int) -> dict[str, int]:
    discovered = discovery_urls(bank_name)
    if len(discovered) != expected_discovered:
        raise RuntimeError(
            f"{bank_name}: doğrulama sırasında keşif sayısı değişti "
            f"({expected_discovered} -> {len(discovered)})."
        )

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT source_url, is_current, record_kind, title
            FROM live_campaigns
            WHERE bank_name=?
            """,
            (bank_name,),
        ).fetchall()
        by_url = {
            canonicalize_url(row["source_url"]): row
            for row in rows
            if canonicalize_url(row["source_url"])
        }
        missing = discovered - set(by_url)
        if missing:
            raise RuntimeError(
                f"{bank_name}: keşfedilen {len(missing)} URL DB'de yok."
            )

        invalid_discovered = [
            url
            for url in discovered
            if (
                int(by_url[url]["is_current"] or 0) == 0
                and str(by_url[url]["record_kind"] or "") != "duplicate"
            )
        ]
        if invalid_discovered:
            raise RuntimeError(
                f"{bank_name}: keşfedilen fakat pasif kalan "
                f"{len(invalid_discovered)} kayıt var."
            )

        counts = db_counts(bank_name)
        if counts["visible"] <= 0:
            raise RuntimeError(f"{bank_name}: dashboard için görünür kampanya yok.")
        return counts
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "scanner_ready=true olan bütün bankaları canlı yeniler; DB, "
            "sınıflandırma, karşılaştırma alanları ve güvenli kaldırma "
            "kontrolünü tek akışta çalıştırır."
        )
    )
    parser.add_argument("--bank", action="append", default=[])
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--confirm-removal-after", type=int, default=2)
    parser.add_argument("--skip-removals", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    available = scanner_ready_banks()
    banks = args.bank or available
    unknown = [bank for bank in banks if bank not in available]
    if unknown:
        raise SystemExit(
            "scanner_ready=true olmayan/konfigürasyonda bulunmayan banka: "
            + ", ".join(unknown)
        )

    if args.dry_run:
        print("Çalıştırılacak bankalar:")
        for bank in banks:
            print("-", bank)
        print("\nDry-run: veri değiştirilmedi.")
        return 0

    token = acquire_lock()
    started = utc_now()
    results: list[BankResult] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    append_log("Tüm bankalar canlı güncellemesi başladı: " + ", ".join(banks))

    try:
        for bank in banks:
            before = db_counts(bank)
            backup = BACKUP_ROOT / stamp / f"{slug(bank)}.db"
            state_backup = BACKUP_ROOT / stamp / f"{slug(bank)}_missing_state.json"
            sqlite_backup(DB_PATH, backup)
            state_existed = STATE_PATH.exists()
            if state_existed:
                state_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(STATE_PATH, state_backup)
            result = BankResult(
                bank_name=bank,
                status="running",
                started_at=utc_now(),
                previous_current=before["current"],
                backup_path=str(backup.relative_to(PROJECT_ROOT)),
            )

            try:
                refresh_bank(bank, args.delay, args.headed)
                discovered_count = len(discovery_urls(bank))
                if discovered_count <= 0:
                    raise RuntimeError(f"{bank}: keşif sonucu boş.")
                result.discovered = discovered_count

                if bank == "Hayat Finans":
                    # Hayat'ın doğrulanmış post-sync pipeline'ı kendi güvenli
                    # --no-mark-removed DB senkronizasyonunu içerir.
                    post_process(bank)
                    sync_report_path = (
                        PROJECT_ROOT / "data" / "live_db_sync_report.json"
                    )
                    try:
                        sync_report = json.loads(
                            sync_report_path.read_text(encoding="utf-8")
                        )
                    except Exception:
                        sync_report = {}
                    if not isinstance(sync_report, dict):
                        sync_report = {}
                else:
                    sync_report = sync_bank_without_removal(bank)
                    post_process(bank)

                if not args.skip_removals:
                    removal = safe_removal(
                        bank,
                        max(args.confirm_removal_after, 1),
                    )
                else:
                    removal = {}

                counts = validate_bank(bank, discovered_count)
                result.current_after = counts["current"]
                result.visible_campaigns = counts["visible"]
                result.created = int(sync_report.get("created") or 0)
                result.content_changed = int(sync_report.get("content_changed") or 0)
                result.pending_removal = int(removal.get("pending_count") or 0)
                result.removed = int(removal.get("removed_count") or 0)
                result.expired = int(removal.get("expired_count") or 0)
                result.status = "success"
                result.message = "Canlı veri, DB, karşılaştırma ve dashboard doğrulaması tamamlandı."
                result.finished_at = utc_now()

                append_log(
                    f"{bank} başarılı: keşif={result.discovered}, "
                    f"yeni={result.created}, içerik_değişen={result.content_changed}, "
                    f"bekleyen_kaldırma={result.pending_removal}, "
                    f"kaldırılan={result.removed}, süresi_dolan={result.expired}"
                )
                print(
                    f"[SUCCESS] {bank}: keşif={result.discovered}, "
                    f"yeni={result.created}, içerik değişen={result.content_changed}, "
                    f"bekleyen kaldırma={result.pending_removal}, "
                    f"kaldırılan={result.removed}, süresi dolan={result.expired}"
                )

            except Exception as error:
                restore_db(backup)
                if state_existed and state_backup.exists():
                    shutil.copy2(state_backup, STATE_PATH)
                elif not state_existed:
                    STATE_PATH.unlink(missing_ok=True)
                result.status = "failed"
                result.finished_at = utc_now()
                result.message = f"{type(error).__name__}: {error}"
                result.current_after = db_counts(bank)["current"]
                append_log(
                    f"{bank} başarısız; banka öncesi DB yedeği geri yüklendi: "
                    + result.message
                )
                print(f"[FAILED] {bank}: {result.message}")

            results.append(result)

        report = {
            "started_at": started,
            "finished_at": utc_now(),
            "success_count": sum(item.status == "success" for item in results),
            "failed_count": sum(item.status == "failed" for item in results),
            "banks": [asdict(item) for item in results],
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        append_log(
            "Tüm bankalar canlı güncellemesi bitti. "
            f"başarılı={report['success_count']}, başarısız={report['failed_count']}"
        )
        print("Rapor:", REPORT_PATH)
        print("Log:", LOG_PATH)
        return 1 if report["failed_count"] else 0
    finally:
        release_lock(token)


if __name__ == "__main__":
    raise SystemExit(main())
