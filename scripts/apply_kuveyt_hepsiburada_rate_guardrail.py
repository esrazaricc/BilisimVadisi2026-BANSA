from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

BANK = "Kuveyt Türk"
TITLE_TOKEN = "Hepsiburada"
URL_TOKEN = "hepsiburadada-yeni-musteriye-ozel-vade-farksiz-50000-tl-firsati"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kuveyt Türk Hepsiburada kampanyasındaki kanıtsız %0 kâr payını temizler."
    )
    parser.add_argument("--db", type=Path, default=Path("data/campaigns.db"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.resolve()
    root = Path.cwd()
    backup_dir = root / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not db_path.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {db_path}")

    db_backup = backup_dir / f"campaigns_before_kuveyt_hepsiburada_rate_fix_{stamp}.db"
    shutil.copy2(db_path, db_backup)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT c.id, c.bank_name, c.title, c.source_url
            FROM live_campaigns AS c
            JOIN live_campaign_finance_details AS f
              ON f.campaign_id = c.id
            WHERE c.bank_name = ?
              AND (
                    c.id = 189
                    OR c.title LIKE ?
                    OR c.source_url LIKE ?
                  )
              AND (
                    f.financing_amount_max = 50000
                    OR f.financing_amount_text LIKE '%50.000%'
                  )
              AND (
                    f.maturity_max_months = 9
                    OR f.maturity_text LIKE '%9 ay%'
                  )
            ORDER BY CASE WHEN c.id = 189 THEN 0 ELSE 1 END
            """,
            (BANK, f"%{TITLE_TOKEN}%", f"%{URL_TOKEN}%"),
        ).fetchall()

        unique = {row["id"]: row for row in rows}
        if len(unique) != 1:
            raise RuntimeError(
                f"Tek Hepsiburada finansman kaydı bekleniyordu; bulunan: {len(unique)}"
            )

        campaign = next(iter(unique.values()))

        with conn:
            cursor = conn.execute(
                """
                UPDATE live_campaign_finance_details
                SET
                    profit_share_rate_min = NULL,
                    profit_share_rate_max = NULL,
                    profit_share_rate_text = NULL,
                    campaign_advantage = ?,
                    evidence_text = ?,
                    extraction_confidence = 1.0
                WHERE campaign_id = ?
                """,
                (
                    "Hepsiburada alışverişlerinde 50.000 TL'ye kadar vade farksız 9 taksit.",
                    "Kampanya metni 50.000 TL'ye kadar 9 taksit avantajını belirtmektedir; sayısal kâr payı oranı açıkça belirtilmemiştir.",
                    campaign["id"],
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Finansman detayı güncellenemedi: {cursor.rowcount}")

        patched_json = []
        for path in root.rglob("finance_extraction_overrides.json"):
            if "backups" in {part.casefold() for part in path.parts}:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, list):
                continue

            changed = False
            for item in data:
                if item.get("bank_name") != BANK:
                    continue
                if URL_TOKEN not in str(item.get("source_url_contains") or ""):
                    continue
                fields = item.setdefault("fields", {})
                fields["profit_share_rate_min"] = None
                fields["profit_share_rate_max"] = None
                fields["profit_share_rate_text"] = None
                fields["campaign_advantage"] = (
                    "Hepsiburada alışverişlerinde 50.000 TL'ye kadar vade farksız 9 taksit."
                )
                fields["evidence_text"] = (
                    "Kampanya metni 50.000 TL'ye kadar 9 taksit avantajını belirtmektedir; "
                    "sayısal kâr payı oranı açıkça belirtilmemiştir."
                )
                changed = True

            if changed:
                backup = backup_dir / f"{path.stem}_before_kuveyt_hepsiburada_fix_{stamp}.json"
                shutil.copy2(path, backup)
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                patched_json.append(str(path))

        result = conn.execute(
            """
            SELECT
                c.id,
                c.title,
                f.profit_share_rate_min,
                f.profit_share_rate_max,
                f.profit_share_rate_text,
                f.financing_amount_text,
                f.maturity_text,
                f.installment_count
            FROM live_campaigns AS c
            JOIN live_campaign_finance_details AS f
              ON f.campaign_id = c.id
            WHERE c.id = ?
            """,
            (campaign["id"],),
        ).fetchone()

        print("=" * 92)
        print("KUVEYT TÜRK HEPSİBURADA KÂR PAYI DÜZELTİLDİ")
        print("=" * 92)
        print("ID:", result["id"])
        print("Kampanya:", result["title"])
        print("Kâr payı:", result["profit_share_rate_text"] or "Belirtilmemiş")
        print("Alt oran:", result["profit_share_rate_min"])
        print("Üst oran:", result["profit_share_rate_max"])
        print("Tutar:", result["financing_amount_text"])
        print("Vade:", result["maturity_text"])
        print("Taksit:", result["installment_count"])
        print("Güncellenen override dosyası:", len(patched_json))
        for path in patched_json:
            print(" -", path)
        print("DB yedeği:", db_backup)

        assert result["profit_share_rate_min"] is None
        assert result["profit_share_rate_max"] is None
        assert result["profit_share_rate_text"] is None
        return 0

    except Exception:
        conn.rollback()
        conn.close()
        shutil.copy2(db_backup, db_path)
        print("Hata nedeniyle DB geri yüklendi:", db_backup)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
