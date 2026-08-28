from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BANK = "Hayat Finans"
INITIAL_URLS = {
    "https://hayatfinans.com.tr/hesaplar/avantajli-hesap",
    "https://hayatfinans.com.tr/kampanyalar/arkadasini-getir-avantajli-hesap-ac-nakit-odul-kazan",
    "https://hayatfinans.com.tr/kampanyalar/avantajli-hesap-musterilerine-ozel-fx-dar-makas-avantaji",
    "https://hayatfinans.com.tr/kampanyalar/bana-bunu-al-is-ortagim-ile-troy-magaza-firsatlari",
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-dijital-uyelikler-kampanyasi",
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-ile-arkadasini-getir-kazan",
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-yemek-harcamasi-nakit-iade-kampanyasi",
    "https://hayatfinans.com.tr/kampanyalar/hayat-finans-ile-gastroclub-ayricaliklari",
    "https://hayatfinans.com.tr/kampanyalar/hayatfinansla-islem-yaptikca-kazan",
    "https://hayatfinans.com.tr/kampanyalar/hayatfx-ile-gumus-islemleri",
    "https://hayatfinans.com.tr/kampanyalar/xiaomi-urunlerinde-finansman-avantaji",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_step(root: Path, label: str, cmd: list[str]) -> None:
    print("\n" + "=" * 100)
    print(label)
    print("=" * 100)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=root, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"{label} başarısız. Çıkış kodu: {result.returncode}")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def set_scanner_ready(config_path: Path, value: bool) -> None:
    data = load_json(config_path)
    if isinstance(data, list):
        bank = next((x for x in data if x.get("name") == BANK), None)
    elif isinstance(data, dict) and isinstance(data.get("banks"), list):
        bank = next((x for x in data["banks"] if x.get("name") == BANK), None)
    else:
        bank = None
    if not isinstance(bank, dict):
        raise RuntimeError("Hayat Finans config kaydı bulunamadı.")
    bank["scanner_ready"] = value
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--skip-refresh", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    db = root / "data" / "campaigns.db"
    config = root / "config" / "banks.json"
    report_path = root / "data" / "hayat_finans_post_sync_report.json"
    extraction_report = root / "data" / "hayat_finans_extraction_report.json"

    scripts = {
        "refresh": root / "scripts" / "run_hayat_finans_live_refresh.py",
        "sync": root / "scripts" / "sync_campaigns_to_db.py",
        "classify": root / "scripts" / "classify_campaign_records.py",
        "override": root / "scripts" / "apply_hayat_finans_classification_overrides.py",
        "extract": root / "scripts" / "extract_comparison_fields.py",
        "guardrail": root / "scripts" / "finalize_hayat_finans_extraction_guardrails.py",
    }
    missing = [str(p) for p in scripts.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Eksik scriptler:\n- " + "\n- ".join(missing))

    backup_dir = root / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_backup = backup_dir / f"campaigns_before_hf_post_sync_{stamp}.db"
    config_backup = backup_dir / f"banks_before_hf_post_sync_{stamp}.json"
    shutil.copy2(db, db_backup)
    shutil.copy2(config, config_backup)

    py = sys.executable
    try:
        set_scanner_ready(config, False)

        if not args.skip_refresh:
            run_step(root, "1/6 — CANLI KEŞİF VE FETCH", [py, str(scripts["refresh"]), "--delay", str(args.delay)])
        run_step(root, "2/6 — VERİTABANI SENKRONİZASYONU", [py, str(scripts["sync"]), "--bank", BANK, "--no-mark-removed"])
        run_step(root, "3/6 — GENEL SINIFLANDIRMA", [py, str(scripts["classify"]), "--bank", BANK])
        run_step(root, "4/6 — SINIFLANDIRMA GUARDRAIL", [py, str(scripts["override"]), "--bank", BANK])
        run_step(root, "5/6 — KARŞILAŞTIRMA ALANLARI", [py, str(scripts["extract"]), "--bank", BANK, "--report", str(extraction_report)])
        run_step(root, "6/6 — FİNANSMAN GUARDRAIL", [py, str(scripts["guardrail"]), "--bank", BANK])

        discovered_rows = load_json(root / "data" / "discovered_campaign_pages.json")
        discovered_urls = {
            str(r.get("url") or "").rstrip("/")
            for r in discovered_rows
            if r.get("bank_name") == BANK and str(r.get("url") or "").strip()
        }
        if not discovered_urls:
            raise RuntimeError("Hayat Finans için keşfedilen URL yok.")

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, title, source_url, record_kind, campaign_category,
                       comparison_eligible, current_status, is_current, clean_text
                FROM live_campaigns WHERE bank_name=? ORDER BY title
                """,
                (BANK,),
            ).fetchall()
            current = [r for r in rows if int(r["is_current"] or 0) == 1]
            by_url = {str(r["source_url"] or "").rstrip("/"): r for r in current}

            missing_in_db = sorted(discovered_urls - set(by_url))
            if missing_in_db:
                raise RuntimeError("Keşfedildiği hâlde DB'de olmayan URL:\n- " + "\n- ".join(missing_in_db))

            empty_text = [u for u in discovered_urls if not str(by_url[u]["clean_text"] or "").strip()]
            if empty_text:
                raise RuntimeError("Metni boş kampanya:\n- " + "\n- ".join(empty_text))

            extra_current = [r for u, r in by_url.items() if u not in discovered_urls]
            unsafe_extra = [r for r in extra_current if str(r["current_status"] or "").lower() not in {"expired", "ended", "inactive"}]
            if unsafe_extra:
                raise RuntimeError(
                    "Listede olmayan fakat aktif/güncel kalan kayıt:\n- "
                    + "\n- ".join(f"{r['title']} | {r['current_status']} | {r['source_url']}" for r in unsafe_extra)
                )

            benefits = conn.execute(
                "SELECT COUNT(*) FROM live_campaign_benefits b JOIN live_campaigns c ON c.id=b.campaign_id WHERE c.bank_name=? AND c.is_current=1",
                (BANK,),
            ).fetchone()[0]
            audiences = conn.execute(
                "SELECT COUNT(*) FROM live_campaign_audiences a JOIN live_campaigns c ON c.id=a.campaign_id WHERE c.bank_name=? AND c.is_current=1",
                (BANK,),
            ).fetchone()[0]
            finance = conn.execute(
                "SELECT COUNT(*) FROM live_campaign_finance_details f JOIN live_campaigns c ON c.id=f.campaign_id WHERE c.bank_name=? AND c.is_current=1 AND c.campaign_category='finance_campaign'",
                (BANK,),
            ).fetchone()[0]
        finally:
            conn.close()

        new_urls = sorted(discovered_urls - INITIAL_URLS)
        category_dist = Counter(str(r["campaign_category"] or "NULL") for r in current)
        status_dist = Counter(str(r["current_status"] or "unknown") for r in current)

        set_scanner_ready(config, True)
        report_path.write_text(
            json.dumps(
                {
                    "bank_name": BANK,
                    "scanner_ready": True,
                    "discovered_count": len(discovered_urls),
                    "database_current_count": len(current),
                    "newly_discovered_urls_outside_initial_11": new_urls,
                    "retained_expired_or_inactive_outside_listing": [
                        {"title": r["title"], "status": r["current_status"], "url": r["source_url"]}
                        for r in extra_current
                    ],
                    "category_distribution": dict(sorted(category_dist.items())),
                    "status_distribution": dict(sorted(status_dist.items())),
                    "finance_record_count": finance,
                    "benefit_count": benefits,
                    "audience_count": audiences,
                    "database_backup": str(db_backup),
                    "config_backup": str(config_backup),
                    "generated_at": now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("\n" + "=" * 100)
        print("HAYAT FİNANS POST-SYNC PIPELINE BAŞARILI")
        print("=" * 100)
        print("Keşfedilen güncel URL:", len(discovered_urls))
        print("Veritabanındaki güncel kayıt:", len(current))
        print("İlk 11 dışında yeni kampanya:", len(new_urls))
        print("Saklanan süresi dolmuş/liste dışı kayıt:", len(extra_current))
        print("Finansman kaydı:", finance)
        print("Avantaj kaydı:", benefits)
        print("Hedef kitle kaydı:", audiences)
        print("scanner_ready: true")
        print("Rapor:", report_path)
        if new_urls:
            print("\nYENİ EKLENEN KAMPANYALAR")
            for url in new_urls:
                print(f"- [{by_url[url]['campaign_category']}] {by_url[url]['title']}")
                print(f"  {url}")
        return 0

    except Exception:
        shutil.copy2(db_backup, db)
        shutil.copy2(config_backup, config)
        print("\nPIPELINE BAŞARISIZ — DB VE CONFIG GERİ YÜKLENDİ")
        print("DB yedeği:", db_backup)
        print("Config yedeği:", config_backup)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
