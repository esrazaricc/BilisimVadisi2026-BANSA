from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.postgres_repository import (  # noqa: E402
    get_standard_product_changes,
    get_standard_product_rule_sets,
    get_standard_products,
    postgres_health,
)


def main() -> int:
    print("=" * 88)
    print("BANSA — POSTGRESQL STREAMLIT READ AUDIT")
    print("=" * 88)

    if not os.getenv("POSTGRES_DSN"):
        print("POSTGRES_DSN: EKSİK")
        print("SONUÇ: KONTROL GEREKİYOR")
        return 2

    health = postgres_health()
    products = get_standard_products()
    product_ids = products["id"].astype(int).tolist() if not products.empty else []
    rules = get_standard_product_rule_sets(product_ids)
    changes = get_standard_product_changes(10)

    warnings: list[str] = []
    expected_products = int(health.get("current_products") or 0)
    if len(products) != expected_products:
        warnings.append(
            f"Ürün sayısı farklı: health={expected_products}, repository={len(products)}"
        )

    required_columns = {
        "id",
        "bank_name",
        "product_family",
        "product_name",
        "source_url",
    }
    missing = required_columns - set(products.columns)
    if missing:
        warnings.append("Eksik ürün kolonları: " + ", ".join(sorted(missing)))

    print(f"Database: {health.get('database_name')}")
    print(f"Schema: {health.get('schema_name')}")
    print(f"PostgreSQL güncel ürün: {expected_products}")
    print(f"Repository ürün: {len(products)}")
    print(f"Kategori kuralı: {len(rules['category'])}")
    print(f"Tutar-vade kuralı: {len(rules['amount_maturity'])}")
    print(f"Fiyatlama satırı: {len(rules['pricing'])}")
    print(f"Masraf kuralı: {len(rules['fee'])}")
    print(f"Özel koşul: {len(rules['offer'])}")
    print(f"Nitel özellik: {len(rules['feature'])}")
    print(f"Son değişiklik örneği: {len(changes)}")
    print(f"Uyarı: {len(warnings)}")
    for warning in warnings:
        print(" -", warning)
    print("SONUÇ: OK" if not warnings else "SONUÇ: KONTROL GEREKİYOR")
    return 0 if not warnings else 2


if __name__ == "__main__":
    raise SystemExit(main())
