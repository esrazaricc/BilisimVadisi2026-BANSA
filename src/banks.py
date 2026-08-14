import json
from pathlib import Path

from src.config import BASE_DIR

BANKS_FILE = Path(BASE_DIR) / "config" / "banks.json"


def load_banks():
    if not BANKS_FILE.exists():
        return []

    with BANKS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data if isinstance(data, list) else []


def get_bank(bank_name):
    for bank in load_banks():
        if bank.get("name") == bank_name:
            return bank
    return None
