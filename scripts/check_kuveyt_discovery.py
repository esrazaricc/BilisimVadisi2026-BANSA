from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


DISCOVERY_PATH = Path("data") / "discovered_campaign_pages.json"
REPORT_PATH = Path("data") / "campaign_discovery_report.json"
ERROR_PATH = Path("data") / "campaign_discovery_errors.json"


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    pages = load_json(DISCOVERY_PATH)
    report = load_json(REPORT_PATH)
    errors = load_json(ERROR_PATH)

    bank_counts = Counter(
        str(item.get("bank_name", "")).strip()
        for item in pages
    )
    source_counts = Counter(
        str(item.get("source_group", "")).strip()
        for item in pages
        if item.get("bank_name") == "Kuveyt Türk"
    )

    kuveyt_urls = [
        str(item.get("url", "")).strip()
        for item in pages
        if item.get("bank_name") == "Kuveyt Türk"
    ]
    duplicate_counts = Counter(kuveyt_urls)
    duplicate_urls = {
        url: count
        for url, count in duplicate_counts.items()
        if url and count > 1
    }

    report_by_bank = defaultdict(list)
    for item in report:
        report_by_bank[str(item.get("bank_name", "")).strip()].append(item)

    print("Toplam keşif kaydı:", len(pages))
    print("\nBanka dağılımı:")
    for bank, count in sorted(bank_counts.items()):
        print(f"  - {bank}: {count}")

    print("\nKuveyt Türk benzersiz URL:", len(set(kuveyt_urls)))
    print("Kuveyt Türk tekrar eden URL:", len(duplicate_urls))

    print("\nKuveyt Türk kaynak grupları:")
    for source_group, count in sorted(
        source_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"  - {source_group}: {count}")

    print("\nKuveyt Türk tarama raporu:")
    for item in report_by_bank.get("Kuveyt Türk", []):
        print(
            "  - kaynak=",
            item.get("source_page"),
            " | bulunan=",
            item.get("discovered_count"),
            " | tıklama=",
            item.get("load_more_clicks"),
            " | yöntem=",
            item.get("render_mode"),
            sep="",
        )

    kuveyt_errors = [
        item
        for item in errors
        if item.get("bank_name") == "Kuveyt Türk"
    ]
    print("\nKuveyt Türk hata sayısı:", len(kuveyt_errors))

    expected_albaraka = bank_counts.get("Albaraka Türk", 0)
    expected_kuveyt = bank_counts.get("Kuveyt Türk", 0)

    print("\nKontrol sonucu:")
    if expected_albaraka == 86:
        print("  ✓ Albaraka Türk 86 kayıt korunmuş.")
    else:
        print(
            "  ! Albaraka Türk beklenen 86 yerine",
            expected_albaraka,
            "kayıt görünüyor.",
        )

    if expected_kuveyt == 111:
        print("  ✓ Kuveyt Türk 111 benzersiz kayıt bulundu.")
    else:
        print(
            "  ! Kuveyt Türk beklenen 111 yerine",
            expected_kuveyt,
            "kayıt görünüyor.",
        )

    if duplicate_urls:
        print("  ! Kuveyt Türk içinde tekrar eden URL bulundu.")
    else:
        print("  ✓ Kuveyt Türk URL tekrarları temizlenmiş.")

    if kuveyt_errors:
        print("  ! Kuveyt Türk keşif hatası bulunuyor.")
    else:
        print("  ✓ Kuveyt Türk keşif hatası yok.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
