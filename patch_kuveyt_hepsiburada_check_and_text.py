from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent
CHECKER = ROOT / "scripts" / "check_kuveyt_third_fixes.py"
EXTRACTOR = ROOT / "scripts" / "extract_comparison_fields.py"


def backup(path: Path, stamp: str) -> Path:
    dst = path.with_name(
        f"{path.stem}_before_hepsiburada_live_fix_{stamp}{path.suffix}"
    )
    shutil.copy2(path, dst)
    return dst


def patch_checker(stamp: str) -> Path:
    if not CHECKER.exists():
        raise FileNotFoundError(CHECKER)

    text = CHECKER.read_text(encoding="utf-8")

    old = 'hepsi["profit_share_rate_text"] != "%0"'
    new = 'hepsi["profit_share_rate_text"] is not None'

    if new in text:
        print("Checker zaten güncel:", CHECKER)
        return CHECKER

    if old not in text:
        raise RuntimeError(
            "Checker içinde beklenen eski Hepsiburada %0 kontrolü bulunamadı."
        )

    b = backup(CHECKER, stamp)
    text = text.replace(old, new, 1)
    CHECKER.write_text(text, encoding="utf-8")
    py_compile.compile(str(CHECKER), doraise=True)

    print("Checker güncellendi:", CHECKER)
    print("Checker yedeği:", b)
    return CHECKER


def patch_extractor(stamp: str) -> Path:
    if not EXTRACTOR.exists():
        raise FileNotFoundError(EXTRACTOR)

    text = EXTRACTOR.read_text(encoding="utf-8")
    original = text

    replacements = {
        "Hepsiburada al??veri?lerinde ": "Hepsiburada alışverişlerinde ",
        "50.000 TL'ye kadar vade farks?z 9 taksit.": "50.000 TL'ye kadar vade farksız 9 taksit.",
        "Kampanya metninde 50.000 TL'ye kadar 9 taksit avantaj? belirtilmektedir; ": "Kampanya metninde 50.000 TL'ye kadar 9 taksit avantajı belirtilmektedir; ",
        "say?sal k?r pay? oran? a??k?a belirtilmemi?tir.": "sayısal kâr payı oranı açıkça belirtilmemiştir.",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    if text == original:
        print("Extractor metinleri zaten güncel veya eşleşen bozuk metin yok:", EXTRACTOR)
        return EXTRACTOR

    b = backup(EXTRACTOR, stamp)
    EXTRACTOR.write_text(text, encoding="utf-8")
    py_compile.compile(str(EXTRACTOR), doraise=True)

    print("Extractor Türkçe metinleri düzeltildi:", EXTRACTOR)
    print("Extractor yedeği:", b)
    return EXTRACTOR


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    patch_checker(stamp)
    patch_extractor(stamp)

    print()
    print("Kuveyt Türk Hepsiburada canlı kontrol düzeltmesi tamamlandı.")
    print("Beklenen doğrulama:")
    print("  - 50.000 TL")
    print("  - 9 taksit")
    print("  - Kâr payı: Belirtilmemiş (DB'de NULL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
