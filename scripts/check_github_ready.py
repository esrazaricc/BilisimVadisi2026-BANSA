from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_GITHUB_FILE = 100 * 1024 * 1024

forbidden = [
    ROOT / ".env",
    ROOT / "data" / "runtime" / "chat_history.sqlite",
]
problems: list[str] = []

for path in forbidden:
    if path.exists():
        problems.append(f"Yayınlanmaması gereken dosya mevcut: {path.relative_to(ROOT)}")

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    try:
        size = path.stat().st_size
    except OSError:
        continue
    if size >= MAX_GITHUB_FILE:
        problems.append(f"GitHub 100 MB sınırını aşıyor: {path.relative_to(ROOT)} ({size} byte)")

required = [
    ROOT / "Ana_Sayfa.py",
    ROOT / "requirements.txt",
    ROOT / "data" / "campaigns.db",
    ROOT / "data" / "runtime" / "finance_snapshot.sqlite",
    ROOT / "data" / "rag" / "rag_dense_vectors.npy",
    ROOT / "src" / "source_link_resolver.py",
]
for path in required:
    if not path.exists():
        problems.append(f"Gerekli dosya eksik: {path.relative_to(ROOT)}")

if problems:
    print("GITHUB READY CHECK: FAIL")
    for item in problems:
        print(f"- {item}")
    sys.exit(1)

print("GITHUB READY CHECK: PASS")
