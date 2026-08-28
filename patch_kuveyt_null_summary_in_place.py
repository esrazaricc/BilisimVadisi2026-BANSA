from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
TARGET = (
    PROJECT_ROOT
    / "scripts"
    / "apply_campaign_classification_overrides.py"
)


OLD = (
    '    kind_counts = Counter(\n'
    '        row["record_kind"] for row in rows\n'
    '    )\n'
    '    category_counts = Counter(\n'
    '        row["campaign_category"] for row in rows\n'
    '    )\n'
)

NEW = (
    '    # NULL değerler rapor özetinde None ile str karşılaştırmasına\n'
    '    # yol açmamalı. Henüz sınıflandırılmamış kayıtları raporda\n'
    '    # "unclassified" etiketiyle gösteriyoruz.\n'
    '    kind_counts = Counter(\n'
    '        str(row["record_kind"] or "unclassified")\n'
    '        for row in rows\n'
    '    )\n'
    '    category_counts = Counter(\n'
    '        str(row["campaign_category"] or "unclassified")\n'
    '        for row in rows\n'
    '    )\n'
)


def main() -> int:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    text = TARGET.read_text(encoding="utf-8")

    if NEW in text:
        print("Dosya zaten düzeltilmiş.")
        print("Hedef:", TARGET)
        return 0

    if OLD not in text:
        raise RuntimeError(
            "Beklenen eski kod bloğu bulunamadı. "
            "Dosya farklı bir sürüm olabilir."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(
        f"{TARGET.stem}_before_null_fix_{stamp}{TARGET.suffix}"
    )
    shutil.copy2(TARGET, backup)

    text = text.replace(OLD, NEW, 1)
    TARGET.write_text(text, encoding="utf-8")

    import py_compile
    py_compile.compile(str(TARGET), doraise=True)

    print("Kuveyt Türk NULL raporlama düzeltmesi uygulandı.")
    print("Hedef:", TARGET)
    print("Yedek:", backup)
    print()
    print("Kontrol:")
    print('  row["record_kind"] or "unclassified"')
    print('  row["campaign_category"] or "unclassified"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
