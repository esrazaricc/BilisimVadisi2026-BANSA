from __future__ import annotations

import json
from pathlib import Path


CONFIG = Path("config") / "standard_product_sources.json"


def find_tf(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).strip().casefold() == "türkiye finans".casefold():
                print("=" * 100)
                print("BULUNDU:", f"{path}.{key}")
                print("=" * 100)
                print(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                print()

            find_tf(value, f"{path}.{key}")

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            if isinstance(item, dict):
                bank_values = [
                    item.get("bank"),
                    item.get("bank_name"),
                    item.get("name"),
                ]

                if any(
                    str(value or "").strip().casefold()
                    == "türkiye finans".casefold()
                    for value in bank_values
                ):
                    print("=" * 100)
                    print("BULUNDU:", f"{path}[{index}]")
                    print("=" * 100)
                    print(
                        json.dumps(
                            item,
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    print()

            find_tf(item, f"{path}[{index}]")


def main():
    if not CONFIG.exists():
        raise SystemExit(
            f"Config bulunamadı: {CONFIG}"
        )

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    print("Config:", CONFIG)
    find_tf(data)


if __name__ == "__main__":
    main()
