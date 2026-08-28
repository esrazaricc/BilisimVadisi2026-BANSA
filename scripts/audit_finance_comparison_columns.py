from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.finance_column_profiles import PROFILES
from src.finance_taxonomy import CATEGORIES


def main() -> int:
    failures: list[str] = []

    for category in CATEGORIES:
        key = (category.scope, category.label)
        if key not in PROFILES:
            failures.append(f"Eksik sütun profili: {category.scope} / {category.label}")
            continue

        profile = PROFILES[key]
        banned = {"Hedef Kitle", "Dijital"}
        # Bunlar ana tabloya generic olarak zorlanmamalı; ihtiyaç varsa
        # Kullanım/Kanal ve kategoriye özel alanlarda normalize edilir.
        bad = banned.intersection(profile.preferred_columns)
        if bad:
            failures.append(f"Generic sütun profilde kaldı: {key} -> {sorted(bad)}")

    if failures:
        print("FAIL")
        for item in failures:
            print(" -", item)
        return 1

    print(f"PASS: {len(PROFILES)} finansman kategorisi için kategoriye özel sütun profili hazır.")
    print("Kural: doğrulanmış verisi olmayan sütun ana karşılaştırmada gösterilmez; tahmin yapılmaz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
