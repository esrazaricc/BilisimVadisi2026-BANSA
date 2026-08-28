from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent
DB = PROJECT_ROOT / "data" / "campaigns.db"
BANK = "Türkiye Emlak Katılım"


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def is_broken_detail_url(url: str) -> bool:
    path = unquote(urlsplit(url or "").path or "")
    return (
        "/tr/bireysel/kampanyalar/kampanya/" in path
        and any(ch.isspace() for ch in path)
    )


def main() -> int:
    if not DB.exists():
        raise FileNotFoundError(DB)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "data"
        / "backups"
        / f"campaigns_before_emlak_bad_link_cleanup_{stamp}.db"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB, backup)

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")

    try:
        rows = con.execute(
            """
            SELECT
                id,
                title,
                source_url,
                current_status,
                is_current,
                content_hash
            FROM live_campaigns
            WHERE bank_name = ?
            """,
            (BANK,),
        ).fetchall()

        targets = [
            row
            for row in rows
            if is_broken_detail_url(
                str(row["source_url"] or "")
            )
        ]

        print("=" * 78)
        print("TÜRKİYE EMLAK KATILIM — BOZUK DETAY URL TEMİZLİĞİ")
        print("=" * 78)
        print("Bulunan bozuk kayıt:", len(targets))

        if not targets:
            print("Temizlenecek kayıt yok.")
            print("DB yedeği:", backup)
            return 0

        if len(targets) != 1:
            print("Güvenlik nedeniyle işlem yapılmadı.")
            for row in targets:
                print("-", row["title"])
                print(" ", row["source_url"])
            raise RuntimeError(
                "Tam 1 bozuk kayıt bekleniyordu."
            )

        row = targets[0]
        timestamp = now_iso()
        campaign_id = int(row["id"])
        url = str(row["source_url"] or "")

        print("İşaretlenecek kayıt:")
        print("-", row["title"])
        print(" ", url)

        with con:
            con.execute(
                """
                UPDATE live_campaigns
                SET
                    current_status = 'removed',
                    is_current = 0,
                    removed_at = ?,
                    last_checked_at = ?,
                    updated_at = ?,
                    fetch_status = 'invalid_detail_url'
                WHERE id = ?
                """,
                (
                    timestamp,
                    timestamp,
                    timestamp,
                    campaign_id,
                ),
            )

            con.execute(
                """
                INSERT INTO live_campaign_changes (
                    campaign_id,
                    bank_name,
                    source_url,
                    change_type,
                    old_content_hash,
                    new_content_hash,
                    old_status,
                    new_status,
                    changed_at,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    BANK,
                    url,
                    "removed",
                    str(row["content_hash"] or "") or None,
                    str(row["content_hash"] or "") or None,
                    str(row["current_status"] or ""),
                    "removed",
                    timestamp,
                    (
                        '{"reason":"invalid_detail_url_redirects_homepage",'
                        '"source":"emlak_broken_link_stability_fix"}'
                    ),
                ),
            )

        print()
        print("Kayıt DB'den silinmedi; audit geçmişi için tutuldu.")
        print("is_current: 0")
        print("current_status: removed")
        print("fetch_status: invalid_detail_url")
        print("DB yedeği:", backup)
        return 0

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
