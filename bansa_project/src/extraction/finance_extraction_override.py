from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.extraction.comparison_field_extractor import (
    FinanceExtraction,
)


DEFAULT_OVERRIDE_PATH = (
    Path("config") / "finance_extraction_overrides.json"
)


def load_finance_overrides(
    path: str | Path = DEFAULT_OVERRIDE_PATH,
) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    value = json.loads(
        file_path.read_text(encoding="utf-8")
    )
    return value if isinstance(value, list) else []


def apply_finance_override(
    extraction: FinanceExtraction,
    *,
    bank_name: str,
    source_url: str,
    path: str | Path = DEFAULT_OVERRIDE_PATH,
) -> tuple[FinanceExtraction, bool]:
    bank_key = str(bank_name or "").strip().casefold()
    url_key = str(source_url or "").strip().casefold()

    for row in load_finance_overrides(path):
        if str(
            row.get("bank_name", "")
        ).strip().casefold() != bank_key:
            continue

        contains = str(
            row.get("source_url_contains", "")
        ).strip().casefold()
        if not contains or contains not in url_key:
            continue

        fields = row.get("fields", {})
        if not isinstance(fields, dict):
            return extraction, False

        allowed = set(
            FinanceExtraction.__dataclass_fields__.keys()
        )
        updates = {
            key: value
            for key, value in fields.items()
            if key in allowed
        }
        return replace(extraction, **updates), True

    return extraction, False