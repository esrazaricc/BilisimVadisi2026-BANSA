from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    repo = (root / "src" / "postgres_repository.py").read_text(encoding="utf-8")
    page_files = list((root / "pages").glob("4_Finansman_*.py"))
    if len(page_files) != 1:
        raise SystemExit(f"Finansman sayfası bulunamadı/tekil değil: {page_files}")
    page = page_files[0].read_text(encoding="utf-8")

    checks = {
        "PostgreSQL ürün kaynağı ayrı alias": "s.url AS product_source_url" in repo,
        "PostgreSQL source fallback": 'frame["source_url"] = frame["product_source_url"]' in repo,
        "UI güvenli kaynak helper": "def first_rule_source_url(" in page,
        "Eski kırılgan tolist kalmadı": '"source_url",\n                        ].dropna().tolist()' not in page,
    }

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(("PASS" if ok else "FAIL"), "-", name)
    if failed:
        print("FAILURES:", failed)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
