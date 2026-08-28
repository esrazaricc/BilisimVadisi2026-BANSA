from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "data" / "verified_catalog"


@lru_cache(maxsize=1)
def load_finance_catalog() -> pd.DataFrame:
    path = CATALOG_DIR / "finance_products.csv"
    frame = pd.read_csv(path, dtype={"product_id": "Int64"})
    return frame.fillna("")


@lru_cache(maxsize=1)
def load_verified_scenarios() -> pd.DataFrame:
    path = CATALOG_DIR / "verified_scenarios.csv"
    frame = pd.read_csv(path)
    return frame


@lru_cache(maxsize=1)
def load_active_campaign_catalog() -> pd.DataFrame:
    path = CATALOG_DIR / "campaigns_active.csv"
    frame = pd.read_csv(path, dtype={"campaign_id": "Int64"})
    return frame.fillna("")


def clear_verified_catalog_cache() -> None:
    load_finance_catalog.cache_clear()
    load_verified_scenarios.cache_clear()
    load_active_campaign_catalog.cache_clear()
