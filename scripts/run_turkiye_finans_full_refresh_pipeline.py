from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
DEFAULT_BANK = "Türkiye Finans"
DEFAULT_DB = DATA / "campaigns.db"

try:
    from run_turkiye_finans_post_sync_pipeline import (  # noqa: E402
        other_banks_fingerprint,
        sqlite_backup,
        sqlite_restore,
    )
except ModuleNotFoundError:
    from scripts.run_turkiye_finans_post_sync_pipeline import (  # noqa: E402
        other_banks_fingerprint,
        sqlite_backup,
        sqlite_restore,
    )


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class Step:
    name: str
    script: str
    args: tuple[str, ...]


def run_help(script: Path) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return (result.stdout or "") + "\n" + (result.stderr or "")


def supports_flag(help_text: str, flag: str) -> bool:
    return re.search(
        rf"(?<![\w-]){re.escape(flag)}(?![\w-])",
        help_text,
    ) is not None


def build_steps(
    bank: str,
    fetch_timeout: int,
    headed_fetch: bool,
    post_sync_timeout: int,
) -> list[Step]:
    discover = SCRIPTS / "discover_campaign_links.py"
    fetch = SCRIPTS / "fetch_campaign_pages.py"
    sync = SCRIPTS / "sync_campaigns_to_db.py"
    post = SCRIPTS / "run_turkiye_finans_post_sync_pipeline.py"

    for path in (discover, fetch, sync, post):
        if not path.exists():
            raise PipelineError(f"Gerekli script bulunamadı: {path}")

    discover_help = run_help(discover)
    fetch_help = run_help(fetch)
    sync_help = run_help(sync)
    post_help = run_help(post)

    if not supports_flag(discover_help, "--bank"):
        raise PipelineError(
            "discover_campaign_links.py --bank desteklemiyor."
        )
    if not supports_flag(sync_help, "--bank"):
        raise PipelineError(
            "sync_campaigns_to_db.py --bank desteklemiyor."
        )
    if not supports_flag(sync_help, "--no-mark-removed"):
        raise PipelineError(
            "Güvenli senkronizasyon için --no-mark-removed gerekli."
        )

    fetch_args: list[str] = []
    if supports_flag(fetch_help, "--bank"):
        fetch_args += ["--bank", bank]
    if supports_flag(fetch_help, "--timeout"):
        fetch_args += ["--timeout", str(fetch_timeout)]
    if headed_fetch:
        if supports_flag(fetch_help, "--headed"):
            fetch_args.append("--headed")
        elif supports_flag(fetch_help, "--headful"):
            fetch_args.append("--headful")
        else:
            raise PipelineError(
                "Fetch scriptinde --headed/--headful bulunamadı."
            )

    post_args: list[str] = []
    if supports_flag(post_help, "--bank"):
        post_args += ["--bank", bank]
    if supports_flag(post_help, "--timeout"):
        post_args += ["--timeout", str(post_sync_timeout)]

    return [
        Step(
            "Kampanya bağlantılarını keşfet",
            "discover_campaign_links.py",
            ("--bank", bank),
        ),
        Step(
            "Kampanya sayfalarını getir",
            "fetch_campaign_pages.py",
            tuple(fetch_args),
        ),
        Step(
            "Veritabanına güvenli senkronize et",
            "sync_campaigns_to_db.py",
            ("--bank", bank, "--no-mark-removed"),
        ),
        Step(
            "Post-sync sınıflandırma ve kalite kontrolü",
            "run_turkiye_finans_post_sync_pipeline.py",
            tuple(post_args),
        ),
    ]


def command_for(step: Step) -> list[str]:
    return [
        sys.executable,
        str(SCRIPTS / step.script),
        *step.args,
    ]


def run_step(step: Step, timeout: int) -> str:
    command = command_for(step)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    print()
    print("=" * 92)
    print("ADIM:", step.name)
    print(
        "KOMUT:",
        " ".join(
            f'"{part}"' if " " in part else part
            for part in command
        ),
    )
    print("=" * 92)

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )

    output = (result.stdout or "") + (result.stderr or "")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        raise PipelineError(
            f"{step.script} başarısız oldu. "
            f"Çıkış kodu: {result.returncode}"
        )

    return output


def walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def count_unique_urls(value: Any) -> int:
    urls: set[str] = set()
    for item in walk_json(value):
        if not isinstance(item, str):
            continue
        for match in re.findall(
            r"https?://[^\s\"'<>]+",
            item,
            flags=re.IGNORECASE,
        ):
            urls.add(match.rstrip(".,);]"))
    return len(urls)


def normalize_bank_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def record_lists(value: Any):
    """
    Kampanya kayıtlarını yalnızca beklenen liste seviyelerinden
    döndürür. Metinlerin içindeki URL'leri veya rapor kaynaklarını
    kampanya olarak saymaz.
    """
    if isinstance(value, list):
        yield value
        return

    if not isinstance(value, dict):
        return

    for key in (
        "pages",
        "campaigns",
        "items",
        "records",
        "results",
        "index",
    ):
        child = value.get(key)
        if isinstance(child, list):
            yield child


def preferred_record_url(
    row: dict[str, Any],
    fields: tuple[str, ...],
) -> str:
    for field in fields:
        value = str(row.get(field) or "").strip()

        if re.match(
            r"^https?://",
            value,
            flags=re.IGNORECASE,
        ):
            return value.rstrip(".,);]")

    return ""


def count_discovered_campaign_records(
    value: Any,
    bank: str,
) -> int:
    """
    discovered_campaign_pages.json içindeki hedef bankaya ait
    gerçek kampanya satırlarını sayar.

    source_page, status_evidence ve listing_text içindeki bağlantılar
    bu sayıya dahil edilmez.
    """
    target = normalize_bank_name(bank)
    urls: set[str] = set()

    for rows in record_lists(value):
        for row in rows:
            if not isinstance(row, dict):
                continue

            if normalize_bank_name(
                row.get("bank_name")
            ) != target:
                continue

            url = preferred_record_url(
                row,
                (
                    "url",
                    "requested_url",
                    "campaign_url",
                    "source_url",
                ),
            )

            if url:
                urls.add(url)

    return len(urls)


def count_fetched_campaign_records(
    value: Any,
    bank: str,
) -> int:
    """
    campaign_page_index.json içindeki hedef bankaya ait başarılı
    veya kontrol edilebilir kampanya metinlerini sayar.

    Bir kaydın raw_text/clean_text alanındaki bağlantılar ve sayfa
    içi navigasyon URL'leri hesaba katılmaz.
    """
    target = normalize_bank_name(bank)
    accepted_statuses = {
        "ok",
        "needs_review",
    }
    urls: set[str] = set()

    for rows in record_lists(value):
        for row in rows:
            if not isinstance(row, dict):
                continue

            if normalize_bank_name(
                row.get("bank_name")
            ) != target:
                continue

            status = str(
                row.get("fetch_status") or ""
            ).strip().casefold()

            if status and status not in accepted_statuses:
                continue

            url = preferred_record_url(
                row,
                (
                    "requested_url",
                    "url",
                    "campaign_url",
                    "source_url",
                ),
            )

            if url:
                urls.add(url)

    return len(urls)


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except json.JSONDecodeError as error:
        raise PipelineError(
            f"JSON okunamadı: {path} | {error}"
        ) from error


def fresh_artifacts_by_preference(
    names: tuple[str, ...],
    started_at: float,
) -> list[Path]:
    """Return fresh artifacts in caller-defined preference order."""
    ordered: list[Path] = []
    seen: set[Path] = set()

    for name in names:
        candidates: list[Path] = []

        for base in (DATA, ROOT):
            direct = base / name
            if direct.exists():
                candidates.append(direct)

        for path in DATA.rglob(name):
            if "backups" not in path.parts:
                candidates.append(path)

        for path in sorted(
            candidates,
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            resolved = path.resolve()

            if resolved in seen:
                continue
            seen.add(resolved)

            if path.stat().st_mtime >= started_at - 2:
                ordered.append(path)

    return ordered


def find_fresh_artifact(
    names: tuple[str, ...],
    started_at: float,
) -> Path:
    fresh = fresh_artifacts_by_preference(
        names,
        started_at,
    )

    if not fresh:
        raise PipelineError(
            "Güncellenmiş çıktı bulunamadı: " + ", ".join(names)
        )

    return fresh[0]


def validate_url_artifact(
    names: tuple[str, ...],
    started_at: float,
    minimum_urls: int,
    label: str,
) -> tuple[Path, int]:
    fresh = fresh_artifacts_by_preference(
        names,
        started_at,
    )

    if not fresh:
        raise PipelineError(
            f"{label} için güncellenmiş çıktı bulunamadı: "
            + ", ".join(names)
        )

    checked: list[tuple[Path, int]] = []

    for path in fresh:
        count = count_unique_urls(load_json(path))
        checked.append((path, count))

        if count >= minimum_urls:
            print(
                f"{label} doğrulandı: {count} benzersiz URL"
            )
            print("Çıktı:", path)
            return path, count

    details = "; ".join(
        f"{path.name}={count}"
        for path, count in checked
    )
    raise PipelineError(
        f"{label} URL sayısı yetersiz; en az "
        f"{minimum_urls} bekleniyor. Kontrol: {details}"
    )


def validate_campaign_artifact(
    names: tuple[str, ...],
    started_at: float,
    minimum_records: int,
    label: str,
    bank: str,
    counter,
) -> tuple[Path, int]:
    """
    Kampanya JSON'larını satır yapısına göre doğrular.

    Genel URL taraması yapılmaz; yalnızca hedef bankanın kampanya
    kayıtlarındaki esas URL alanı sayılır.
    """
    fresh = fresh_artifacts_by_preference(
        names,
        started_at,
    )

    if not fresh:
        raise PipelineError(
            f"{label} için güncellenmiş çıktı bulunamadı: "
            + ", ".join(names)
        )

    checked: list[tuple[Path, int]] = []

    for path in fresh:
        count = int(counter(load_json(path), bank))
        checked.append((path, count))

        if count >= minimum_records:
            print(
                f"{label} doğrulandı: "
                f"{count} kampanya kaydı"
            )
            print("Çıktı:", path)
            return path, count

    details = "; ".join(
        f"{path.name}={count}"
        for path, count in checked
    )
    raise PipelineError(
        f"{label} kampanya kaydı yetersiz; en az "
        f"{minimum_records} bekleniyor. Kontrol: {details}"
    )


def count_error_entries(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("errors", "failed", "failures", "items"):
            if key not in value:
                continue
            child = value[key]
            if isinstance(child, (list, dict)):
                return len(child)
            if isinstance(child, int):
                return child
        if any(
            key in value
            for key in ("error", "exception", "traceback")
        ):
            return 1
        return len(value)
    return 1


def validate_fresh_fetch_errors(started_at: float) -> None:
    checked: set[Path] = set()
    for pattern in ("*fetch*error*.json", "*page*error*.json"):
        for path in DATA.rglob(pattern):
            resolved = path.resolve()
            if resolved in checked:
                continue
            checked.add(resolved)
            if path.stat().st_mtime < started_at - 2:
                continue
            errors = count_error_entries(load_json(path))
            if errors:
                raise PipelineError(
                    f"Fetch hata dosyasında {errors} hata var: {path}"
                )
            print("Fetch hata dosyası temiz:", path)


def bank_count(db: Path, bank: str) -> int:
    connection = sqlite3.connect(db)
    try:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM live_campaigns "
                "WHERE bank_name = ?",
                (bank,),
            ).fetchone()[0]
            or 0
        )
    finally:
        connection.close()


def write_log(
    path: Path,
    bank: str,
    status: str,
    backup: Path,
    outputs: list[tuple[Step, str]],
    audits: list[str],
    error: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Zaman: {datetime.now().isoformat(timespec='seconds')}",
        f"Banka: {bank}",
        f"Durum: {status}",
        f"Yedek: {backup}",
    ]
    if error:
        lines.append(f"Hata: {error}")
    if audits:
        lines += ["", "ÇIKTI DOĞRULAMALARI", *audits]
    for step, output in outputs:
        lines += [
            "",
            "=" * 92,
            f"ADIM: {step.name}",
            f"SCRIPT: {step.script}",
            "=" * 92,
            output.rstrip(),
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Türkiye Finans keşif, fetch, güvenli sync ve "
            "post-sync işlemlerini tek komutta çalıştırır."
        )
    )
    parser.add_argument("--bank", default=DEFAULT_BANK)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--minimum-urls", type=int, default=49)
    parser.add_argument("--minimum-records", type=int, default=49)
    parser.add_argument("--fetch-timeout", type=int, default=90)
    parser.add_argument("--step-timeout", type=int, default=1800)
    parser.add_argument("--post-sync-timeout", type=int, default=300)
    parser.add_argument("--headed-fetch", action="store_true")
    parser.add_argument(
        "--skip-artifact-validation",
        action="store_true",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = args.db.resolve()
    if not db.exists():
        raise PipelineError(f"Veritabanı bulunamadı: {db}")

    steps = build_steps(
        args.bank,
        args.fetch_timeout,
        args.headed_fetch,
        args.post_sync_timeout,
    )

    print("Türkiye Finans tam yenileme pipeline")
    print("Proje:", ROOT)
    print("Banka:", args.bank)
    print("Veritabanı:", db)
    print("Adımlar:")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. {step.script} {' '.join(step.args)}")

    if args.dry_run:
        print("Dry-run tamamlandı; değişiklik yapılmadı.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        DATA
        / "backups"
        / f"campaigns_before_tf_full_refresh_{stamp}.db"
    )
    log = (
        DATA
        / "logs"
        / f"turkiye_finans_full_refresh_{stamp}.log"
    )

    sqlite_backup(db, backup)
    print("Ana güvenlik yedeği:", backup)

    outputs: list[tuple[Step, str]] = []
    audits: list[str] = []

    try:
        before_other = other_banks_fingerprint(db, args.bank)

        discovery_started = datetime.now().timestamp()
        outputs.append(
            (
                steps[0],
                run_step(steps[0], args.step_timeout),
            )
        )
        if not args.skip_artifact_validation:
            path, count = validate_campaign_artifact(
                (
                    "discovered_campaign_pages.json",
                    "campaign_discovery_report.json",
                ),
                discovery_started,
                args.minimum_urls,
                "Keşif",
                args.bank,
                count_discovered_campaign_records,
            )
            audits.append(
                f"Keşif: {count} kampanya kaydı | {path}"
            )

        fetch_started = datetime.now().timestamp()
        outputs.append(
            (
                steps[1],
                run_step(steps[1], args.step_timeout),
            )
        )
        if not args.skip_artifact_validation:
            path, count = validate_campaign_artifact(
                (
                    "campaign_page_index.json",
                    "campaign_page_fetch_report.json",
                ),
                fetch_started,
                args.minimum_urls,
                "Fetch",
                args.bank,
                count_fetched_campaign_records,
            )
            audits.append(
                f"Fetch: {count} kampanya kaydı | {path}"
            )
            validate_fresh_fetch_errors(fetch_started)

        outputs.append(
            (
                steps[2],
                run_step(steps[2], args.step_timeout),
            )
        )

        records = bank_count(db, args.bank)
        if records < args.minimum_records:
            raise PipelineError(
                f"Sync sonrası kayıt {records}; "
                f"en az {args.minimum_records} bekleniyor."
            )
        print("Senkronizasyon sonrası banka kaydı:", records)

        outputs.append(
            (
                steps[3],
                run_step(steps[3], args.step_timeout),
            )
        )

        after_other = other_banks_fingerprint(db, args.bank)
        if before_other != after_other:
            changed = sorted(
                key
                for key in set(before_other) | set(after_other)
                if before_other.get(key) != after_other.get(key)
            )
            raise PipelineError(
                "Diğer banka verileri değişti: "
                + ", ".join(changed)
            )

        write_log(
            log,
            args.bank,
            "SUCCESS",
            backup,
            outputs,
            audits,
        )

        print()
        print("=" * 92)
        print("TAM YENİLEME BAŞARIYLA TAMAMLANDI")
        print("=" * 92)
        print("Kayıt:", records)
        print("Yedek:", backup)
        print("Log:", log)
        return 0

    except Exception as error:
        print("HATA:", error, file=sys.stderr)
        print(
            "Veritabanı ana yedekten geri yükleniyor...",
            file=sys.stderr,
        )
        sqlite_restore(backup, db)
        write_log(
            log,
            args.bank,
            "FAILED_ROLLED_BACK",
            backup,
            outputs,
            audits,
            str(error),
        )
        print("Geri yükleme tamamlandı.", file=sys.stderr)
        print("Yedek:", backup, file=sys.stderr)
        print("Log:", log, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
