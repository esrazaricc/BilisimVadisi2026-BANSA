from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError as exc:
    raise SystemExit(
        'psycopg kurulu değil. Önce: pip install "psycopg[binary]"'
    ) from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = PROJECT_ROOT / "data" / "campaigns.db"
DEFAULT_SCHEMA = PROJECT_ROOT / "postgresql" / "schema.sql"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BANSA SQLite -> PostgreSQL migration")
    p.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    p.add_argument("--dsn", default=os.getenv("POSTGRES_DSN"))
    p.add_argument(
        "--replace",
        action="store_true",
        help="Yalnızca PostgreSQL bansa şemasındaki verileri temizleyip yeniden taşır.",
    )
    return p.parse_args()


def slugify(value: str) -> str:
    trans = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    value = value.translate(trans).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "bank"


def boolv(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(int(value))


def dt(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
    return None


def d(value: Any) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def json_obj(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {"raw": str(value)}


def has_table(con: sqlite3.Connection, name: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def rows(con: sqlite3.Connection, table: str):
    if not has_table(con, table):
        return []
    return con.execute(f'SELECT * FROM "{table}"').fetchall()


def pg_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def run_schema(pg, schema_file: Path, replace: bool) -> None:
    with pg.cursor() as cur:
        if replace:
            cur.execute("DROP SCHEMA IF EXISTS bansa CASCADE")
        cur.execute(schema_file.read_text(encoding="utf-8"))
    pg.commit()


def main() -> int:
    args = parse_args()
    if not args.dsn:
        raise SystemExit("POSTGRES_DSN tanımlı değil veya --dsn verilmedi.")

    sqlite_path = Path(args.sqlite).resolve()
    schema_path = Path(args.schema).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite bulunamadı: {sqlite_path}")
    if not schema_path.exists():
        raise SystemExit(f"Schema bulunamadı: {schema_path}")

    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = psycopg.connect(args.dsn)

    try:
        run_schema(pg, schema_path, args.replace)
        with pg.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                "INSERT INTO migration_runs(source_kind, source_path) VALUES ('sqlite', %s) RETURNING id",
                (str(sqlite_path),),
            )
            migration_id = cur.fetchone()[0]
        pg.commit()

        # ------------------------------------------------------------------
        # Banks
        # ------------------------------------------------------------------
        bank_names = set()
        for table in (
            "live_campaigns",
            "live_campaign_changes",
            "live_standard_product_changes",
            "live_sync_runs",
            "campaign_classification_override_log",
        ):
            if not has_table(sq, table):
                continue
            cols = {r[1] for r in sq.execute(f'PRAGMA table_info("{table}")')}
            if "bank_name" in cols:
                bank_names.update(
                    r[0]
                    for r in sq.execute(
                        f'SELECT DISTINCT bank_name FROM "{table}" WHERE bank_name IS NOT NULL AND TRIM(bank_name) <> ""'
                    )
                )

        bank_ids: dict[str, int] = {}
        with pg.cursor() as cur:
            for name in sorted(bank_names):
                cur.execute(
                    """
                    INSERT INTO banks(name, slug)
                    VALUES (%s, %s)
                    ON CONFLICT(name) DO UPDATE SET updated_at=NOW()
                    RETURNING id
                    """,
                    (name, slugify(name)),
                )
                bank_ids[name] = cur.fetchone()[0]
        pg.commit()

        # ------------------------------------------------------------------
        # Source pages - campaign/product records share these.
        # ------------------------------------------------------------------
        source_ids: dict[tuple[str, str], int] = {}
        live_records = rows(sq, "live_campaigns")
        best_source: dict[tuple[str, str], sqlite3.Row] = {}
        for r in live_records:
            key = (r["bank_name"], r["source_url"])
            old = best_source.get(key)
            if old is None or len(r["clean_text"] or "") > len(old["clean_text"] or ""):
                best_source[key] = r

        with pg.cursor() as cur:
            for (bank_name, url), r in best_source.items():
                cur.execute(
                    """
                    INSERT INTO source_pages(
                        bank_id,url,page_title,source_group,clean_text,content_hash,
                        fetch_status,listing_status,first_seen_at,last_seen_at,last_checked_at,
                        is_current,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(bank_id,url) DO UPDATE SET
                        page_title=EXCLUDED.page_title,
                        source_group=EXCLUDED.source_group,
                        clean_text=EXCLUDED.clean_text,
                        content_hash=EXCLUDED.content_hash,
                        fetch_status=EXCLUDED.fetch_status,
                        listing_status=EXCLUDED.listing_status,
                        last_seen_at=EXCLUDED.last_seen_at,
                        last_checked_at=EXCLUDED.last_checked_at,
                        is_current=EXCLUDED.is_current,
                        updated_at=EXCLUDED.updated_at
                    RETURNING id
                    """,
                    (
                        bank_ids[bank_name], url, r["title"], r["source_group"], r["clean_text"],
                        r["content_hash"], r["fetch_status"], r["listing_status"],
                        dt(r["first_seen_at"]), dt(r["last_seen_at"]), dt(r["last_checked_at"]),
                        boolv(r["is_current"]), dt(r["created_at"]), dt(r["updated_at"]),
                    ),
                )
                source_ids[(bank_name, url)] = cur.fetchone()[0]
                if r["content_hash"]:
                    cur.execute(
                        """
                        INSERT INTO source_page_snapshots(source_page_id,content_hash,clean_text,fetch_status,captured_at)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT(source_page_id,content_hash) DO NOTHING
                        """,
                        (source_ids[(bank_name,url)], r["content_hash"], r["clean_text"], r["fetch_status"], dt(r["last_checked_at"]) or datetime.now()),
                    )
        pg.commit()

        # ------------------------------------------------------------------
        # Campaigns
        # ------------------------------------------------------------------
        campaign_ids: dict[int, int] = {}
        with pg.cursor() as cur:
            for r in live_records:
                if r["record_kind"] != "campaign":
                    continue
                cur.execute(
                    """
                    INSERT INTO campaigns(
                        legacy_live_id,bank_id,source_page_id,campaign_name,source_group,
                        campaign_category,start_date,end_date,current_status,listing_status,
                        fetch_status,comparison_eligible,classification_confidence,
                        classification_reason,is_current,first_seen_at,last_seen_at,
                        last_checked_at,removed_at,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(legacy_live_id) DO UPDATE SET
                        campaign_name=EXCLUDED.campaign_name,
                        campaign_category=EXCLUDED.campaign_category,
                        current_status=EXCLUDED.current_status,
                        listing_status=EXCLUDED.listing_status,
                        fetch_status=EXCLUDED.fetch_status,
                        is_current=EXCLUDED.is_current,
                        updated_at=EXCLUDED.updated_at
                    RETURNING id
                    """,
                    (
                        r["id"], bank_ids[r["bank_name"]], source_ids.get((r["bank_name"],r["source_url"])),
                        r["title"], r["source_group"], r["campaign_category"], d(r["start_date"]), d(r["end_date"]),
                        r["current_status"], r["listing_status"], r["fetch_status"], boolv(r["comparison_eligible"]),
                        r["classification_confidence"], r["classification_reason"], boolv(r["is_current"]),
                        dt(r["first_seen_at"]), dt(r["last_seen_at"]), dt(r["last_checked_at"]), dt(r["removed_at"]),
                        dt(r["created_at"]), dt(r["updated_at"]),
                    ),
                )
                campaign_ids[int(r["id"])] = cur.fetchone()[0]
        pg.commit()

        # Campaign child tables
        with pg.cursor() as cur:
            for r in rows(sq, "live_campaign_finance_details"):
                cid = campaign_ids.get(int(r["campaign_id"]))
                if not cid: continue
                cur.execute(
                    """
                    INSERT INTO campaign_finance_details(
                        campaign_id,finance_type,profit_share_rate_min,profit_share_rate_max,
                        profit_share_rate_text,financing_amount_min,financing_amount_max,
                        financing_amount_text,maturity_min_months,maturity_max_months,maturity_text,
                        installment_count,allocation_fee_amount,allocation_fee_rate,allocation_fee_status,
                        expense_status,expense_details,campaign_advantage,evidence_text,extraction_confidence,
                        grace_period_months,extracted_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(campaign_id) DO UPDATE SET
                        finance_type=EXCLUDED.finance_type,
                        profit_share_rate_min=EXCLUDED.profit_share_rate_min,
                        profit_share_rate_max=EXCLUDED.profit_share_rate_max,
                        financing_amount_min=EXCLUDED.financing_amount_min,
                        financing_amount_max=EXCLUDED.financing_amount_max,
                        maturity_max_months=EXCLUDED.maturity_max_months,
                        extracted_at=EXCLUDED.extracted_at
                    """,
                    (cid,r["finance_type"],r["profit_share_rate_min"],r["profit_share_rate_max"],r["profit_share_rate_text"],
                     r["financing_amount_min"],r["financing_amount_max"],r["financing_amount_text"],r["maturity_min_months"],
                     r["maturity_max_months"],r["maturity_text"],r["installment_count"],r["allocation_fee_amount"],
                     r["allocation_fee_rate"],r["allocation_fee_status"],r["expense_status"],r["expense_details"],
                     r["campaign_advantage"],r["evidence_text"],r["extraction_confidence"],r["grace_period_months"],dt(r["extracted_at"])),
                )

            for r in rows(sq, "live_campaign_benefits"):
                cid = campaign_ids.get(int(r["campaign_id"]))
                if not cid: continue
                cur.execute(
                    """
                    INSERT INTO campaign_benefits(legacy_id,campaign_id,benefit_type,amount,rate,points,minimum_spending,maximum_benefit,description,evidence,extracted_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (r["id"],cid,r["benefit_type"],r["amount"],r["rate"],r["points"],r["minimum_spending"],r["maximum_benefit"],r["description"],r["evidence"],dt(r["extracted_at"])),
                )

            for r in rows(sq, "live_campaign_audiences"):
                cid = campaign_ids.get(int(r["campaign_id"]))
                if not cid: continue
                cur.execute(
                    """
                    INSERT INTO campaign_audiences(legacy_id,campaign_id,audience_type,audience_label,details,extracted_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(campaign_id,audience_type,audience_label) DO UPDATE SET details=EXCLUDED.details, extracted_at=EXCLUDED.extracted_at
                    """,
                    (r["id"],cid,r["audience_type"],r["audience_label"],r["details"],dt(r["extracted_at"])),
                )

            for r in rows(sq, "live_campaign_installment_terms"):
                cid = campaign_ids.get(int(r["campaign_id"]))
                if not cid: continue
                cur.execute(
                    """
                    INSERT INTO campaign_installment_terms(campaign_id,minimum_transaction_amount,maximum_transaction_amount,installment_count,installment_cost_rate,installment_cost_text,evidence_text,extracted_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (cid,r["minimum_transaction_amount"],r["maximum_transaction_amount"],r["installment_count"],r["installment_cost_rate"],r["installment_cost_text"],r["evidence_text"],dt(r["extracted_at"])),
                )

            for r in rows(sq, "live_campaign_changes"):
                cid = campaign_ids.get(int(r["campaign_id"]))
                cur.execute(
                    """
                    INSERT INTO campaign_change_events(legacy_id,campaign_id,bank_id,source_url,change_type,old_content_hash,new_content_hash,old_status,new_status,details,changed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    """,
                    (r["id"],cid,bank_ids[r["bank_name"]],r["source_url"],r["change_type"],r["old_content_hash"],r["new_content_hash"],r["old_status"],r["new_status"],pg_json(json_obj(r["details_json"])),dt(r["changed_at"]) or datetime.now()),
                )
        pg.commit()

        # ------------------------------------------------------------------
        # Product families + standard products
        # ------------------------------------------------------------------
        details_rows = rows(sq, "live_standard_product_details")
        family_ids: dict[str, int] = {}
        with pg.cursor() as cur:
            for r in details_rows:
                key = r["product_family_key"]
                if key in family_ids: continue
                cur.execute(
                    """
                    INSERT INTO product_families(family_key,family_name)
                    VALUES (%s,%s)
                    ON CONFLICT(family_key) DO UPDATE SET family_name=EXCLUDED.family_name
                    RETURNING id
                    """,
                    (key,r["product_family"]),
                )
                family_ids[key] = cur.fetchone()[0]
        pg.commit()

        live_by_id = {int(r["id"]): r for r in live_records}
        product_ids: dict[int, int] = {}
        with pg.cursor() as cur:
            for r in details_rows:
                legacy_id = int(r["product_id"])
                base = live_by_id.get(legacy_id)
                if not base:
                    continue
                cur.execute(
                    """
                    INSERT INTO standard_products(
                        legacy_live_id,bank_id,source_page_id,family_id,product_name,scope,
                        minimum_financing_amount,maximum_financing_amount,minimum_maturity_months,
                        maximum_maturity_months,profit_share_rate,profit_share_rate_text,interest_free,
                        interest_free_text,maturity_rules_text,maturity_reference_upper_amount,
                        financing_ratio_rules_text,maximum_financing_ratio,housing_first_home_rules_text,
                        housing_additional_home_rules_text,housing_finance_rules,vehicle_finance_rules_text,
                        vehicle_age_rules_text,shopping_general_limit_amount,shopping_general_max_maturity_months,
                        shopping_finance_rules_text,fee_waiver_text,insurance_fee_waived,allocation_fee_waived,
                        commission_fee_waived,shopping_phone_rule_text,shopping_tablet_max_maturity_months,
                        shopping_computer_max_maturity_months,finance_rules,current_status,fetch_status,is_current,
                        content_hash,first_seen_at,last_seen_at,last_checked_at,checked_at,extracted_at,created_at,updated_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(legacy_live_id) DO UPDATE SET
                        product_name=EXCLUDED.product_name,
                        minimum_financing_amount=EXCLUDED.minimum_financing_amount,
                        maximum_financing_amount=EXCLUDED.maximum_financing_amount,
                        maximum_maturity_months=EXCLUDED.maximum_maturity_months,
                        profit_share_rate=EXCLUDED.profit_share_rate,
                        is_current=EXCLUDED.is_current,
                        updated_at=EXCLUDED.updated_at
                    RETURNING id
                    """,
                    (
                        legacy_id,bank_ids[r["bank_name"]],source_ids.get((base["bank_name"],base["source_url"])),family_ids[r["product_family_key"]],
                        r["product_name"],r["scope"],r["minimum_financing_amount"],r["maximum_financing_amount"],r["minimum_maturity_months"],
                        r["maximum_maturity_months"],r["profit_share_rate"],r["profit_share_rate_text"],boolv(r["interest_free"]),r["interest_free_text"],
                        r["maturity_rules_text"],r["maturity_reference_upper_amount"],r["financing_ratio_rules_text"],r["maximum_financing_ratio"],
                        r["housing_first_home_rules_text"],r["housing_additional_home_rules_text"],pg_json(json_obj(r["housing_finance_rules_json"])),
                        r["vehicle_finance_rules_text"],r["vehicle_age_rules_text"],r["shopping_general_limit_amount"],r["shopping_general_max_maturity_months"],
                        r["shopping_finance_rules_text"],r["fee_waiver_text"],boolv(r["insurance_fee_waived"]),boolv(r["allocation_fee_waived"]),
                        boolv(r["commission_fee_waived"]),r["shopping_phone_rule_text"],r["shopping_tablet_max_maturity_months"],r["shopping_computer_max_maturity_months"],
                        pg_json(json_obj(r["finance_rules_json"])),base["current_status"],base["fetch_status"],boolv(base["is_current"]),base["content_hash"],
                        dt(base["first_seen_at"]),dt(base["last_seen_at"]),dt(base["last_checked_at"]),dt(r["checked_at"]),dt(r["extracted_at"]),dt(base["created_at"]),dt(base["updated_at"]),
                    ),
                )
                product_ids[legacy_id] = cur.fetchone()[0]
        pg.commit()

        # Product child tables
        product_table_specs = [
            ("live_product_amount_maturity_rules", "product_amount_maturity_rules",
             ["id","product_id","min_amount","max_amount","min_inclusive","max_inclusive","max_maturity_months","source_text","updated_at"]),
            ("live_product_category_rules", "product_category_rules",
             ["id","product_id","category_key","category_label","min_amount","max_amount","min_inclusive","max_inclusive","max_installments","max_maturity_months","condition_text","source_text","updated_at"]),
            ("live_product_pricing_tiers", "product_pricing_tiers",
             ["id","product_id","maturity_months","profit_share_rate","allocation_fee_rate","monthly_total_cost_rate","annual_total_cost_rate","source_text","updated_at","pricing_variant"]),
            ("live_product_fee_rules", "product_fee_rules",
             ["id","product_id","fee_type","fee_label","waived","amount","rate","note","updated_at"]),
            ("live_product_offer_rules", "product_offer_rules",
             ["id","product_id","rule_type","rule_label","min_amount","max_amount","min_inclusive","max_inclusive","max_installments","max_maturity_months","interest_free","condition_text","source_text","updated_at"]),
            ("live_product_features", "product_features",
             ["id","product_id","feature_key","feature_label","feature_value","source_text","extraction_method","updated_at"]),
        ]

        with pg.cursor() as cur:
            for src_table, dst_table, cols in product_table_specs:
                for r in rows(sq, src_table):
                    pid = product_ids.get(int(r["product_id"]))
                    if not pid: continue
                    data = dict(r)
                    data["product_id"] = pid
                    data["legacy_id"] = data.pop("id")
                    for k in ("min_inclusive","max_inclusive","waived","interest_free"):
                        if k in data: data[k] = boolv(data[k])
                    if "updated_at" in data: data["updated_at"] = dt(data["updated_at"])
                    insert_cols = ["legacy_id"] + [c for c in cols if c != "id"]
                    placeholders = ",".join(["%s"] * len(insert_cols))
                    values = [data[c] for c in insert_cols]
                    if dst_table == "product_features":
                        cur.execute(
                            f"INSERT INTO {dst_table}({','.join(insert_cols)}) VALUES ({placeholders}) ON CONFLICT(product_id,feature_key) DO UPDATE SET feature_label=EXCLUDED.feature_label, feature_value=EXCLUDED.feature_value, source_text=EXCLUDED.source_text, extraction_method=EXCLUDED.extraction_method, updated_at=EXCLUDED.updated_at",
                            values,
                        )
                    else:
                        cur.execute(f"INSERT INTO {dst_table}({','.join(insert_cols)}) VALUES ({placeholders})", values)

            for r in rows(sq, "live_standard_product_changes"):
                pid = product_ids.get(int(r["product_id"])) if r["product_id"] is not None else None
                cur.execute(
                    """
                    INSERT INTO product_change_events(legacy_id,product_id,bank_id,product_family,product_name,source_url,change_type,changed_fields,before_data,after_data,detected_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)
                    """,
                    (r["id"],pid,bank_ids[r["bank_name"]],r["product_family"],r["product_name"],r["source_url"],r["change_type"],
                     pg_json(json_obj(r["changed_fields_json"])),pg_json(json_obj(r["before_json"])),pg_json(json_obj(r["after_json"])),dt(r["detected_at"]) or datetime.now()),
                )

            for r in rows(sq, "live_standard_product_scan_state"):
                pid = product_ids.get(int(r["product_id"]))
                if not pid: continue
                cur.execute(
                    """
                    INSERT INTO product_scan_state(product_id,consecutive_missing_count,last_seen_scan_at,last_missing_scan_at,possible_removed)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(product_id) DO UPDATE SET
                        consecutive_missing_count=EXCLUDED.consecutive_missing_count,
                        last_seen_scan_at=EXCLUDED.last_seen_scan_at,
                        last_missing_scan_at=EXCLUDED.last_missing_scan_at,
                        possible_removed=EXCLUDED.possible_removed
                    """,
                    (pid,r["consecutive_missing_count"],dt(r["last_seen_scan_at"]),dt(r["last_missing_scan_at"]),boolv(r["possible_removed"])),
                )
        pg.commit()

        # Sync + override logs
        with pg.cursor() as cur:
            for r in rows(sq, "live_sync_runs"):
                cur.execute(
                    """
                    INSERT INTO sync_runs(legacy_id,bank_id,pipeline_kind,started_at,finished_at,discovered_count,processed_count,created_count,content_changed_count,status_changed_count,reactivated_count,removed_count,unchanged_count,unavailable_count,error_count,removal_skipped,details)
                    VALUES (%s,%s,'campaign',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (r["id"],bank_ids[r["bank_name"]],dt(r["started_at"]) or datetime.now(),dt(r["finished_at"]),r["discovered_count"],r["processed_count"],r["created_count"],r["content_changed_count"],r["status_changed_count"],r["reactivated_count"],r["removed_count"],r["unchanged_count"],r["unavailable_count"],r["error_count"],boolv(r["removal_skipped"]),pg_json(json_obj(r["details_json"]))),
                )

            for r in rows(sq, "campaign_classification_override_log"):
                cur.execute(
                    """
                    INSERT INTO classification_override_log(legacy_id,bank_id,source_url,before_data,after_data,reason,applied_at)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                    """,
                    (r["id"],bank_ids[r["bank_name"]],r["source_url"],pg_json(json_obj(r["before_json"])),pg_json(json_obj(r["after_json"])),r["reason"],dt(r["applied_at"]) or datetime.now()),
                )
        pg.commit()

        # Migration summary
        summary = {
            "banks": len(bank_ids),
            "source_pages": len(source_ids),
            "campaigns": len(campaign_ids),
            "standard_products": len(product_ids),
            "sqlite": str(sqlite_path),
        }
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE migration_runs SET finished_at=NOW(), status='success', details=%s::jsonb WHERE id=%s",
                (pg_json(summary), migration_id),
            )
        pg.commit()

        print("=" * 88)
        print("BANSA SQLITE -> POSTGRESQL MIGRATION TAMAMLANDI")
        print("=" * 88)
        for k, v in summary.items():
            print(f"{k}: {v}")
        print("PostgreSQL schema: bansa")
        return 0
    except Exception as exc:
        pg.rollback()
        try:
            with pg.cursor() as cur:
                cur.execute("SET search_path TO bansa, public")
                if 'migration_id' in locals():
                    cur.execute(
                        "UPDATE migration_runs SET finished_at=NOW(), status='failed', details=%s::jsonb WHERE id=%s",
                        (pg_json({"error": str(exc)}), migration_id),
                    )
                    pg.commit()
        except Exception:
            pass
        raise
    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
