import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.db import init_db


if __name__ == "__main__":
    init_db()
    print("Veritabanı hazır: data/campaigns.db")
