from __future__ import annotations

from pathlib import Path
import py_compile
import shutil
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parent
TARGET = PROJECT_ROOT / "scripts" / "extract_comparison_fields.py"

OLD = '                    finance = extract_finance_fields(\n                        title,\n                        clean_text,\n                    )\n                    finance, override_applied = (\n                        apply_finance_override(\n                            finance,\n                            bank_name=row["bank_name"],\n                            source_url=row["source_url"],\n                        )\n                    )\n                    if override_applied:\n                        finance_override_count += 1\n'
NEW = '                    extracted_finance = extract_finance_fields(\n                        title,\n                        clean_text,\n                    )\n                    finance, override_applied = (\n                        apply_finance_override(\n                            extracted_finance,\n                            bank_name=row["bank_name"],\n                            source_url=row["source_url"],\n                        )\n                    )\n\n                    # Doğrulanmış override oran/tutar/vade gibi alanları\n                    # korur. Override\'ın boş bıraktığı masraf bilgisini\n                    # ise resmî kampanya metninden çıkarılan değerle\n                    # tamamlarız.\n                    if override_applied:\n                        finance = replace(\n                            finance,\n                            expense_status=(\n                                finance.expense_status\n                                or extracted_finance.expense_status\n                            ),\n                            expense_details=(\n                                finance.expense_details\n                                or extracted_finance.expense_details\n                            ),\n                        )\n                        finance_override_count += 1\n'


def main() -> int:
    if not TARGET.exists():
        raise FileNotFoundError(
            f"Hedef dosya bulunamadı: {TARGET}"
        )

    text = TARGET.read_text(encoding="utf-8")

    if NEW in text:
        print("Patch zaten uygulanmış.")
        py_compile.compile(str(TARGET), doraise=True)
        print("Syntax kontrolü: OK")
        return 0

    if OLD not in text:
        raise RuntimeError(
            "Beklenen extraction/override bloğu bulunamadı. "
            "Dosyanın güncel sürümünü kontrol edin."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(
        f"{TARGET.stem}_before_expense_preserve_{stamp}.py"
    )
    shutil.copy2(TARGET, backup)

    TARGET.write_text(
        text.replace(OLD, NEW, 1),
        encoding="utf-8",
    )

    py_compile.compile(str(TARGET), doraise=True)

    print("Patch uygulandı.")
    print("Hedef:", TARGET)
    print("Yedek:", backup)
    print("Syntax kontrolü: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
