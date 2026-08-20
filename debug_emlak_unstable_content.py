from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parent
BANK = "Türkiye Emlak Katılım"
INDEX = PROJECT_ROOT / "data" / "campaign_page_index.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower().replace("www.", ""),
            path,
            "",
            "",
        )
    )


def text_hash(title: str, clean_text: str) -> str:
    payload = (
        (title or "").strip()
        + "\n"
        + (clean_text or "").strip()
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def capture() -> dict[str, dict]:
    rows = load_json(INDEX, [])
    if not isinstance(rows, list):
        raise RuntimeError("campaign_page_index.json liste değil.")

    result = {}

    for row in rows:
        if (
            not isinstance(row, dict)
            or str(row.get("bank_name") or "") != BANK
        ):
            continue

        raw_snapshot = str(row.get("snapshot_file") or "").strip()
        if not raw_snapshot:
            continue

        snapshot_path = Path(raw_snapshot)
        if not snapshot_path.is_absolute():
            snapshot_path = PROJECT_ROOT / snapshot_path

        snapshot = load_json(snapshot_path, {})
        if not isinstance(snapshot, dict):
            continue

        url = canonical_url(
            str(
                snapshot.get("requested_url")
                or snapshot.get("final_url")
                or row.get("requested_url")
                or row.get("url")
                or ""
            )
        )
        if not url:
            continue

        title = str(
            snapshot.get("title")
            or row.get("title")
            or ""
        ).strip()

        clean_text = str(
            snapshot.get("clean_text")
            or ""
        ).strip()

        result[url] = {
            "url": url,
            "title": title,
            "clean_text": clean_text,
            "hash": text_hash(title, clean_text),
            "snapshot_file": str(snapshot_path),
        }

    return result


def refresh(label: str) -> None:
    print("\n" + "=" * 78)
    print(label)
    print("=" * 78)

    command = [
        sys.executable,
        "scripts/refresh_live_campaigns.py",
        "--bank",
        BANK,
        "--delay",
        "0.35",
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"refresh_live_campaigns.py başarısız: "
            f"{completed.returncode}"
        )


def compact_diff(before: str, after: str) -> list[str]:
    before_lines = [
        line.strip()
        for line in (before or "").splitlines()
        if line.strip()
    ]
    after_lines = [
        line.strip()
        for line in (after or "").splitlines()
        if line.strip()
    ]

    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="FETCH-1",
            tofile="FETCH-2",
            lineterm="",
            n=2,
        )
    )

    # Terminali boğmamak için ilk 80 satır yeterli.
    return diff[:80]


def main() -> int:
    print("=" * 78)
    print("TÜRKİYE EMLAK KATILIM — DEĞİŞKEN İÇERİK TEŞHİSİ")
    print("=" * 78)
    print("Bu script DB senkronizasyonu yapmaz.")
    print("Sadece iki kez discovery/fetch yapıp snapshot karşılaştırır.")

    # İlk yeni fetch
    refresh("1/2 — İlk canlı fetch")
    first = capture()

    # İkinci yeni fetch
    refresh("2/2 — İkinci canlı fetch")
    second = capture()

    all_urls = sorted(set(first) | set(second))

    changed = []
    added = []
    missing = []

    for url in all_urls:
        a = first.get(url)
        b = second.get(url)

        if a is None:
            added.append(url)
            continue

        if b is None:
            missing.append(url)
            continue

        if a["hash"] != b["hash"]:
            changed.append((url, a, b))

    print("\n" + "=" * 78)
    print("SONUÇ")
    print("=" * 78)
    print("Fetch-1 kayıt:", len(first))
    print("Fetch-2 kayıt:", len(second))
    print("Her fetch'te değişen:", len(changed))
    print("İkinci fetch'te yeni:", len(added))
    print("İkinci fetch'te kayıp:", len(missing))

    if not changed:
        print("\nİki fetch arasında değişen snapshot bulunmadı.")
        print(
            "Bu durumda DB content_hash hesabı ile snapshot hash hesabı "
            "arasında fark olabilir; sonraki adım sync hash katmanını "
            "incelemek olacak."
        )
        return 0

    for index, (url, before, after) in enumerate(changed, 1):
        print("\n" + "-" * 78)
        print(f"DEĞİŞEN #{index}")
        print("-" * 78)
        print("Başlık-1:", before["title"])
        print("Başlık-2:", after["title"])
        print("URL:", url)
        print("Hash-1:", before["hash"])
        print("Hash-2:", after["hash"])
        print("Snapshot:", after["snapshot_file"])

        diff = compact_diff(
            before["clean_text"],
            after["clean_text"],
        )

        print("\nMETİN FARKI:")
        if not diff:
            if before["title"] != after["title"]:
                print(
                    "- clean_text aynı; yalnızca başlık değişiyor."
                )
            else:
                print(
                    "- Satır bazlı fark görünmedi; whitespace veya "
                    "karakter düzeyinde dinamik fark olabilir."
                )
        else:
            for line in diff:
                print(line)

    if added:
        print("\nİKİNCİ FETCH'TE YENİ URL:")
        for url in added:
            print("-", url)

    if missing:
        print("\nİKİNCİ FETCH'TE KAYIP URL:")
        for url in missing:
            print("-", url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
