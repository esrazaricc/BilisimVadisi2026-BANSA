from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import psycopg
except ImportError as exc:
    raise RuntimeError('Çalıştırın: python -m pip install "psycopg[binary]"') from exc

DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN tanımlı değil")

    sq = sqlite3.connect(args.db)
    sq.row_factory = sqlite3.Row
    pg = psycopg.connect(dsn, application_name="bansa_finance_accuracy_v2")

    with pg.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")
        cur.execute("ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2)")
        cur.execute("ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS value_type TEXT NOT NULL DEFAULT 'exact'")
        cur.execute("ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'official_pricing_table'")
        cur.execute("ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS conditions TEXT")
        cur.execute("ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS source_url TEXT")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS finance_fact_evidence (
                id BIGSERIAL PRIMARY KEY,
                legacy_id BIGINT,
                product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
                fact_key TEXT NOT NULL,
                value_text TEXT,
                value_numeric NUMERIC(18,6),
                value_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                conditions TEXT,
                source_url TEXT,
                source_text TEXT,
                verification_status TEXT NOT NULL DEFAULT 'verified',
                updated_at TIMESTAMPTZ
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_finance_evidence_product ON finance_fact_evidence(product_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_finance_evidence_key ON finance_fact_evidence(fact_key)")
    pg.commit()

    detail_rows = sq.execute("""
        SELECT d.*, c.id AS legacy_live_id, c.source_url AS live_source_url,
               c.current_status AS live_current_status, c.fetch_status AS live_fetch_status,
               c.is_current AS live_is_current, c.first_seen_at AS live_first_seen_at,
               c.last_seen_at AS live_last_seen_at, c.last_checked_at AS live_last_checked_at,
               c.created_at AS live_created_at, c.updated_at AS live_updated_at
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.record_kind='standard_product' AND c.is_current=1
    """).fetchall()

    # SQLite'ta doğrulanmış yeni bir standart ürün oluştuysa (örn. ayrı ELÜS
    # ürünü), PostgreSQL'de legacy_live_id yok diye sessizce atlama. Banka,
    # aile ve kaynak sayfasını upsert edip ürün iskeletini oluştur; aşağıdaki
    # ortak update/senkron adımları tüm ayrıntıları doldurur.
    with pg.cursor() as cur:
        for r in detail_rows:
            legacy_id = int(r["legacy_live_id"])
            # Önce legacy kimliği kontrol et. Ürün daha önce bu SQLite kimliğiyle
            # eşlenmişse yeni satır oluşturmaya gerek yok.
            cur.execute("""
                SELECT sp.id, sp.product_name, b.name, sp.is_current
                FROM standard_products sp
                JOIN banks b ON b.id = sp.bank_id
                WHERE sp.legacy_live_id=%s
            """, (legacy_id,))
            legacy_row = cur.fetchone()

            if legacy_row:
                legacy_pg_id = int(legacy_row[0])
                legacy_name = str(legacy_row[1] or "")
                legacy_bank = str(legacy_row[2] or "")
                legacy_is_current = bool(legacy_row[3])

                same_identity = (
                    legacy_bank == str(r["bank_name"] or "")
                    and legacy_name == str(r["product_name"] or "")
                )

                # Ayni dogrulanmis urun zaten PostgreSQL'de guncelse
                # yeniden olusturmaya gerek yok.
                if same_identity and legacy_is_current:
                    continue

                # Eski Ziraat taramalarinda urun adi yerine banka genel
                # basligi kaydedilmis olabilir. Bu satiri silme; yalnizca
                # legacy kimligini serbest birak. Asagidaki canonical
                # senkron gercek urunu ayni legacy_live_id ile olusturur.
                ziraat_generic_collision = (
                    str(r["bank_name"] or "") == "Ziraat Kat\u0131l\u0131m"
                    and legacy_bank == "Ziraat Kat\u0131l\u0131m"
                    and legacy_name == "Ziraat Kat\u0131l\u0131m Bankas\u0131"
                )

                if ziraat_generic_collision:
                    cur.execute(
                        """
                        UPDATE standard_products
                        SET legacy_live_id=NULL,
                            updated_at=NOW()
                        WHERE id=%s
                        """,
                        (legacy_pg_id,),
                    )

                elif not same_identity:
                    raise RuntimeError(
                        "Beklenmeyen legacy_live_id cakismasi: "
                        f"legacy_live_id={legacy_id}, "
                        f"PG={legacy_bank} / {legacy_name}, "
                        f"SQLite={r['bank_name']} / {r['product_name']}"
                    )
            cur.execute("SELECT id FROM banks WHERE name=%s", (r["bank_name"],))
            bank_row = cur.fetchone()
            if not bank_row:
                raise RuntimeError(f"PostgreSQL bankası bulunamadı: {r['bank_name']}")
            bank_id = int(bank_row[0])
            cur.execute("""
                INSERT INTO product_families(family_key,family_name) VALUES (%s,%s)
                ON CONFLICT(family_key) DO UPDATE SET family_name=EXCLUDED.family_name
                RETURNING id
            """, (r["product_family_key"], r["product_family"]))
            family_id = int(cur.fetchone()[0])
            # SOURCE_URL_RESOLVER_V1
            # Direkt ?r?nlerde ger?ek live source URL esas al?n?r.
            # #product= ile ?retilen embedded ?r?nlerde fiziksel
            # kaynak sayfas? source_page olarak korunur.
            _live_source_url = str(
                r["live_source_url"] or ""
            ).strip()
            _source_page = str(
                r["source_page"] or ""
            ).strip()

            if "#product=" in _live_source_url.casefold():
                source_url = (
                    _source_page
                    or _live_source_url.split("#", 1)[0]
                )
            else:
                source_url = (
                    _live_source_url
                    or _source_page
                )
            cur.execute("""
                INSERT INTO source_pages(bank_id,url,page_title,source_group,fetch_status,listing_status,first_seen_at,last_seen_at,last_checked_at,is_current,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,'active',%s,%s,%s,TRUE,COALESCE(%s,NOW()),COALESCE(%s,NOW()))
                ON CONFLICT(bank_id,url) DO UPDATE SET page_title=EXCLUDED.page_title,fetch_status=EXCLUDED.fetch_status,last_seen_at=EXCLUDED.last_seen_at,last_checked_at=EXCLUDED.last_checked_at,is_current=TRUE,updated_at=EXCLUDED.updated_at
                RETURNING id
            """, (bank_id, source_url, r["product_name"], r["product_family"], r["live_fetch_status"], r["live_first_seen_at"], r["live_last_seen_at"], r["live_last_checked_at"], r["live_created_at"], r["live_updated_at"]))
            source_page_id = int(cur.fetchone()[0])

            # PostgreSQL'de aynı mantıksal ürün daha eski bir migrasyondan
            # legacy_live_id olmadan (veya farklı eski legacy id ile) mevcut
            # olabilir. UNIQUE(bank_id,family_id,product_name,source_page_id)
            # bu durumda ikinci INSERT'i haklı olarak reddeder. Aynı doğal
            # kimlik varsa yeni satır açmak yerine mevcut ürünü güncel SQLite
            # kimliğiyle uzlaştır. Böylece ürün çoğalmaz ve alt tablolar aynı
            # standard_products.id üzerinde kalır.
            cur.execute("""
                SELECT id, legacy_live_id
                FROM standard_products
                WHERE bank_id=%s AND family_id=%s AND product_name=%s AND source_page_id=%s
            """, (bank_id, family_id, r["product_name"], source_page_id))
            natural_row = cur.fetchone()
            if natural_row:
                existing_id, existing_legacy_id = int(natural_row[0]), natural_row[1]
                cur.execute("""
                    UPDATE standard_products SET
                        legacy_live_id=%s,
                        scope=%s,
                        current_status=%s,
                        fetch_status=%s,
                        is_current=TRUE,
                        first_seen_at=COALESCE(first_seen_at,%s),
                        last_seen_at=%s,
                        last_checked_at=%s,
                        checked_at=%s,
                        extracted_at=%s,
                        updated_at=COALESCE(%s,NOW())
                    WHERE id=%s
                """, (
                    legacy_id, r["scope"], r["live_current_status"], r["live_fetch_status"],
                    r["live_first_seen_at"], r["live_last_seen_at"], r["live_last_checked_at"],
                    r["checked_at"], r["extracted_at"], r["live_updated_at"], existing_id,
                ))
                print(
                    f"[PG KIMLIK UZLASTIRMA] {r['bank_name']} / {r['product_name']} "
                    f"-> product_id={existing_id}, legacy {existing_legacy_id!r} => {legacy_id}"
                )
                continue

            cur.execute("""
                INSERT INTO standard_products(legacy_live_id,bank_id,source_page_id,family_id,product_name,scope,current_status,fetch_status,is_current,first_seen_at,last_seen_at,last_checked_at,checked_at,extracted_at,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,%s,%s,COALESCE(%s,NOW()),COALESCE(%s,NOW()))
                ON CONFLICT(legacy_live_id) DO NOTHING
            """, (legacy_id,bank_id,source_page_id,family_id,r["product_name"],r["scope"],r["live_current_status"],r["live_fetch_status"],r["live_first_seen_at"],r["live_last_seen_at"],r["live_last_checked_at"],r["checked_at"],r["extracted_at"],r["live_created_at"],r["live_updated_at"]))
        pg.commit()

    with pg.cursor() as cur:
        for r in detail_rows:
            # Kaynak sayfası son doğrulanmış ürün URL'sine taşındıysa mevcut
            # PostgreSQL ürününün source_page_id'sini de güncelle.
            # SOURCE_URL_RESOLVER_V1
            # Direkt ?r?nlerde ger?ek live source URL esas al?n?r.
            # #product= ile ?retilen embedded ?r?nlerde fiziksel
            # kaynak sayfas? source_page olarak korunur.
            _live_source_url = str(
                r["live_source_url"] or ""
            ).strip()
            _source_page = str(
                r["source_page"] or ""
            ).strip()

            if "#product=" in _live_source_url.casefold():
                source_url = (
                    _source_page
                    or _live_source_url.split("#", 1)[0]
                )
            else:
                source_url = (
                    _live_source_url
                    or _source_page
                )
            cur.execute("SELECT id FROM banks WHERE name=%s", (r["bank_name"],))
            bank_row = cur.fetchone()
            if not bank_row:
                raise RuntimeError(f"PostgreSQL bankası bulunamadı: {r['bank_name']}")
            bank_id = int(bank_row[0])
            cur.execute("""
                INSERT INTO source_pages(bank_id,url,page_title,source_group,fetch_status,listing_status,last_seen_at,last_checked_at,is_current,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,'active',COALESCE(%s,NOW()),COALESCE(%s,NOW()),TRUE,NOW(),NOW())
                ON CONFLICT(bank_id,url) DO UPDATE SET page_title=EXCLUDED.page_title,source_group=EXCLUDED.source_group,fetch_status=EXCLUDED.fetch_status,last_seen_at=EXCLUDED.last_seen_at,last_checked_at=EXCLUDED.last_checked_at,is_current=TRUE,updated_at=NOW()
                RETURNING id
            """, (bank_id,source_url,r["product_name"],r["product_family"],r["live_fetch_status"],r["live_last_seen_at"],r["live_last_checked_at"]))
            source_page_id = int(cur.fetchone()[0])
            cur.execute("""
                UPDATE standard_products SET
                    source_page_id=%s,
                    minimum_financing_amount=%s,
                    maximum_financing_amount=%s,
                    maximum_maturity_months=%s,
                    profit_share_rate=%s,
                    profit_share_rate_text=%s,
                    interest_free=%s,
                    interest_free_text=%s,
                    maturity_rules_text=%s,
                    financing_ratio_rules_text=%s,
                    maximum_financing_ratio=%s,
                    housing_first_home_rules_text=%s,
                    housing_additional_home_rules_text=%s,
                    housing_finance_rules=%s::jsonb,
                    vehicle_finance_rules_text=%s,
                    vehicle_age_rules_text=%s,

                    -- POSTGRES_SHOPPING_WRITER_COMPLETENESS_V2
                    shopping_general_limit_amount=%s,
                    shopping_general_max_maturity_months=%s,
                    shopping_finance_rules_text=%s,
                    shopping_phone_rule_text=%s,
                    shopping_tablet_max_maturity_months=%s,
                    shopping_computer_max_maturity_months=%s,

                    finance_rules=%s::jsonb
                WHERE legacy_live_id=%s
            """, (
                source_page_id,
                r["minimum_financing_amount"], r["maximum_financing_amount"],
                r["maximum_maturity_months"], r["profit_share_rate"],
                r["profit_share_rate_text"], bool(r["interest_free"]) if r["interest_free"] is not None else None,
                r["interest_free_text"], r["maturity_rules_text"],
                r["financing_ratio_rules_text"], r["maximum_financing_ratio"],
                r["housing_first_home_rules_text"], r["housing_additional_home_rules_text"],
                r["housing_finance_rules_json"],
                r["vehicle_finance_rules_text"], r["vehicle_age_rules_text"],

                r["shopping_general_limit_amount"],
                r["shopping_general_max_maturity_months"],
                r["shopping_finance_rules_text"],
                r["shopping_phone_rule_text"],
                r["shopping_tablet_max_maturity_months"],
                r["shopping_computer_max_maturity_months"],

                r["finance_rules_json"], int(r["legacy_live_id"]),
            ))
    pg.commit()

    product_map = {}
    with pg.cursor() as cur:
        cur.execute("SELECT id,legacy_live_id FROM standard_products WHERE legacy_live_id IS NOT NULL")
        product_map = {int(legacy): int(pid) for pid, legacy in cur.fetchall()}

    specs = [
        ("live_product_amount_maturity_rules", "product_amount_maturity_rules",
         ["min_amount","max_amount","min_inclusive","max_inclusive","max_maturity_months","source_text","updated_at"]),
        ("live_product_category_rules", "product_category_rules",
         ["category_key","category_label","min_amount","max_amount","min_inclusive","max_inclusive","max_installments","max_maturity_months","condition_text","source_text","updated_at"]),
        ("live_product_pricing_tiers", "product_pricing_tiers",
         ["financing_amount","maturity_months","profit_share_rate","allocation_fee_rate","monthly_total_cost_rate","annual_total_cost_rate","pricing_variant","value_type","source_type","conditions","source_url","source_text","updated_at"]),
        ("live_product_fee_rules", "product_fee_rules",
         ["fee_type","fee_label","waived","amount","rate","note","updated_at"]),
        ("live_product_offer_rules", "product_offer_rules",
         ["rule_type","rule_label","min_amount","max_amount","min_inclusive","max_inclusive","max_installments","max_maturity_months","interest_free","condition_text","source_text","updated_at"]),
        ("live_product_features", "product_features",
         ["feature_key","feature_label","feature_value","source_text","extraction_method","updated_at"]),
        ("live_finance_fact_evidence", "finance_fact_evidence",
         ["fact_key","value_text","value_numeric","value_type","source_type","conditions","source_url","source_text","verification_status","updated_at"]),
    ]

    with pg.cursor() as cur:
        for legacy_id, pg_id in product_map.items():
            # Sadece SQLite'ta mevcut ürünleri yeniden yaz.
            exists = sq.execute("SELECT 1 FROM live_standard_product_details WHERE product_id=?", (legacy_id,)).fetchone()
            if not exists:
                continue
            for _, dst, _ in specs:
                cur.execute(f"DELETE FROM {dst} WHERE product_id=%s", (pg_id,))
        pg.commit()

        for src, dst, cols in specs:
            source_cols = {r[1] for r in sq.execute(f"PRAGMA table_info({src})").fetchall()}
            if not source_cols:
                continue
            select_cols = ["id","product_id"] + [c for c in cols if c in source_cols]
            for r in sq.execute(f"SELECT {','.join(select_cols)} FROM {src}"):
                pg_id = product_map.get(int(r["product_id"]))
                if not pg_id:
                    continue
                present_cols = [c for c in cols if c in source_cols]
                insert_cols = ["legacy_id","product_id"] + present_cols
                vals = [int(r["id"]), pg_id]
                for c in present_cols:
                    v = r[c]
                    if c in {"min_inclusive","max_inclusive","waived","interest_free"} and v is not None:
                        v = bool(v)
                    vals.append(v)
                placeholders = ",".join(["%s"] * len(vals))
                cur.execute(
                    f"INSERT INTO {dst}({','.join(insert_cols)}) VALUES ({placeholders})",
                    vals,
                )
        pg.commit()

    sq.close(); pg.close()
    print(f"PostgreSQL Finansman Veri Doğruluk V2 senkronu tamamlandı: {len(product_map)} eşleşen ürün.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
