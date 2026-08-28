from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_discovery import (
    canonicalize_url,
    discover_all_pages,
    write_discovery_results,
)
from src.scraping.campaign_page_fetcher import (
    fetch_campaign_pages,
    write_fetch_results,
)



_DUNYA_GENERIC_TITLES = {
    "",
    "kampanya detayları",
    "kampanya detaylari",
    "diğer kampanyalar",
    "diger kampanyalar",
    "kampanyalar",
}


def _title_key(value: str) -> str:
    return (
        " ".join(str(value or "").split())
        .casefold()
        .replace("ı", "i")
        .replace("i̇", "i")
    )


def _apply_dunya_listing_overrides(
    snapshots,
    pages,
):
    """
    Dünya Katılım için aktif GetCampaigns kartını kaynak kabul eder.

    Detay sayfasındaki genel başlıklar ve eski kampanya tarihleri yerine
    API kartındaki gerçek başlık/tarih bilgileri kullanılır. Endpoint
    ``showHistory=false`` olduğu için bu akıştaki bütün kayıtlar aktiftir.
    """
    page_by_url = {
        canonicalize_url(page.url): page
        for page in pages
        if page.bank_name == "Dünya Katılım"
    }

    corrected = []
    title_corrections = 0
    date_corrections = 0
    status_corrections = 0

    for snapshot in snapshots:
        if snapshot.bank_name != "Dünya Katılım":
            corrected.append(snapshot)
            continue

        key = canonicalize_url(
            snapshot.requested_url or snapshot.url
        )
        page = page_by_url.get(key)
        if page is None:
            raise RuntimeError(
                "Dünya Katılım snapshot'ı discovery kaydında yok: "
                + key
            )

        listing_title = " ".join(
            str(page.listing_text or "").split()
        )
        if _title_key(listing_title) in _DUNYA_GENERIC_TITLES:
            raise RuntimeError(
                "Dünya Katılım API kart başlığı genel veya boş: "
                f"{listing_title!r} | {key}"
            )

        new_start_date = (
            page.listing_start_date
            or snapshot.campaign_start_date
        )
        # Aktif API kartındaki bitiş tarihi tek otoritedir. Kartta '-' varsa
        # boş bırakılır; detay metnindeki eski tarih tekrar kullanılmaz.
        new_end_date = page.listing_end_date or ""

        if listing_title != snapshot.title:
            title_corrections += 1
        if (
            new_start_date != snapshot.campaign_start_date
            or new_end_date != snapshot.campaign_end_date
        ):
            date_corrections += 1
        if snapshot.current_status != "active":
            status_corrections += 1

        snapshot = replace(
            snapshot,
            title=listing_title,
            listing_status="active",
            listing_status_evidence=page.status_evidence,
            campaign_start_date=new_start_date,
            campaign_end_date=new_end_date,
            current_status="active",
            status_reason=(
                "Dünya Katılım GetCampaigns aktif listesinde "
                "showHistory=false ile bulundu."
            ),
            status_evidence=page.status_evidence,
            status_checked_at=page.status_checked_at,
        )
        corrected.append(snapshot)

    return (
        corrected,
        title_corrections,
        date_corrections,
        status_corrections,
    )


def _validate_dunya_snapshots(snapshots, pages) -> None:
    dunya_pages = [
        page for page in pages
        if page.bank_name == "Dünya Katılım"
    ]
    dunya_snapshots = [
        snapshot for snapshot in snapshots
        if snapshot.bank_name == "Dünya Katılım"
    ]

    if len(dunya_snapshots) != len(dunya_pages):
        raise RuntimeError(
            "Dünya Katılım fetch sayısı keşif sayısıyla eşleşmedi: "
            f"discovery={len(dunya_pages)}, fetch={len(dunya_snapshots)}"
        )

    urls = {
        canonicalize_url(
            snapshot.requested_url or snapshot.url
        )
        for snapshot in dunya_snapshots
    }
    if len(urls) != len(dunya_snapshots):
        raise RuntimeError(
            "Dünya Katılım fetch sonuçlarında mükerrer URL var."
        )

    invalid_titles = [
        snapshot
        for snapshot in dunya_snapshots
        if _title_key(snapshot.title) in _DUNYA_GENERIC_TITLES
    ]
    if invalid_titles:
        raise RuntimeError(
            "Dünya Katılım fetch sonuçlarında genel başlık kaldı: "
            + ", ".join(
                snapshot.url for snapshot in invalid_titles
            )
        )

    non_active = [
        snapshot
        for snapshot in dunya_snapshots
        if snapshot.current_status != "active"
    ]
    if non_active:
        raise RuntimeError(
            "Dünya Katılım aktif API sonucunda active olmayan kayıt var: "
            + ", ".join(
                snapshot.url for snapshot in non_active
            )
        )

def _has_incomplete_discovery(diagnostics) -> bool:
    """
    Sabit referans sayısının altına düşmek tek başına hata değildir.

    Kampanyalar zamanla sona erdiği için canlı aktif kampanya sayısı
    geçmişte doğrulanmış reference_visible_count değerinden düşük olabilir.
    Teknik olarak tamamlanmamış sayfalama/tıklama ise hâlâ bloklayıcıdır.
    """
    return any(
        item.completeness_status == "CLICK_LIMIT_REACHED"
        for item in diagnostics
    )


def _reference_drop_diagnostics(diagnostics):
    return [
        item
        for item in diagnostics
        if item.completeness_status == "BELOW_REFERENCE_COUNT"
    ]

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kampanya bağlantılarını ve metinlerini tek akışta "
            "yeniler; aktif/yaklaşan/sona ermiş durumunu hesaplar."
        )
    )
    parser.add_argument("--bank")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    pages, discovery_errors, diagnostics = discover_all_pages(
        bank_name=args.bank,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )
    write_discovery_results(
        pages,
        discovery_errors,
        diagnostics,
    )

    reference_drops = _reference_drop_diagnostics(diagnostics)
    if reference_drops:
        print("\nUYARI: Canlı kampanya sayısı geçmiş referansın altında.")
        print(
            "Bu durum kampanyaların sona ermesi nedeniyle normal olabilir; "
            "tek başına senkronizasyonu durdurmaz."
        )
        for item in reference_drops:
            print(
                f"  [{item.bank_name}] "
                f"bulunan={item.discovered_count}, "
                f"eski_referans={item.reference_visible_count}"
            )

    incomplete = _has_incomplete_discovery(diagnostics)
    if discovery_errors or incomplete:
        print("\nCanlı yenileme keşif aşamasında durduruldu.")
        print(f"Keşif hatası: {len(discovery_errors)}")
        print(f"Eksik keşif: {incomplete}")
        for item in diagnostics:
            print(
                f"  [{item.bank_name}] "
                f"bulunan={item.discovered_count}, "
                f"referans={item.reference_visible_count}, "
                f"durum={item.completeness_status}"
            )
        return 1

    snapshots, fetch_errors = fetch_campaign_pages(
        bank_name=args.bank,
        limit=args.limit,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )
    if fetch_errors:
        print("\nFetch hatası bulundu; sonuçlar yazılmadı.")
        for item in fetch_errors:
            print(
                f"  [{item.get('bank_name', '')}] "
                f"{item.get('url', item.get('requested_url', ''))}: "
                f"{item.get('message', item.get('error', ''))}"
            )
        return 1

    (
        snapshots,
        corrected_title_count,
        corrected_date_count,
        corrected_status_count,
    ) = _apply_dunya_listing_overrides(
        snapshots,
        pages,
    )

    if (
        args.bank
        and args.bank.casefold() == "dünya katılım".casefold()
    ):
        _validate_dunya_snapshots(snapshots, pages)

    write_fetch_results(snapshots, fetch_errors)

    print("\nCanlı kampanya yenilemesi tamamlandı.")
    print(f"Bulunan bağlantı: {len(pages)}")
    print(f"İşlenen kampanya: {len(snapshots)}")
    print(
        "Dünya Katılım başlık düzeltmesi: "
        f"{corrected_title_count}"
    )
    print(
        "Dünya Katılım tarih düzeltmesi: "
        f"{corrected_date_count}"
    )
    print(
        "Dünya Katılım durum düzeltmesi: "
        f"{corrected_status_count}"
    )
    print(
        "Toplam hata: "
        f"{len(discovery_errors) + len(fetch_errors)}"
    )

    return 1 if discovery_errors or fetch_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
