from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

import pandas as pd


_EXACT_MISSING = {
    "", "-", "—", "none", "nan", "null", "n/a", "na",
    "belirtilmedi", "doğrulanmadı", "bilinmiyor",
}

_NON_VALUE_PATTERNS = (
    r"^bilgi yok",
    r"^resm[iî] kaynakta yay[ıi]mlanmam[ıi]ş",
    r"^resm[iî] kaynakta yayınlanmam[ıi]ş",
    r"^sayısal fiyatlama (?:yayımlanmamış|doğrulanmamış)",
    r"^sayısal (?:değer|oran|koşul).*(?:yayımlanmamış|doğrulanmamış)",
    r"^kaynakta .*?(?:yayımlanmamış|yer almıyor|bulunmuyor)",
    r"^yüzdesel .*?(?:yayımlanmamış|doğrulanmamış)",
    r"^resm[iî].*sayısal.*(?:yayımlanmamış|yer almıyor)",
)


def clean_cell(value: object) -> str:
    """Return a UI-safe cell value without NaN/None/placeholder noise.

    This is presentation-only cleanup. It never creates a fact; it only hides
    strings that explicitly mean "no data" and normalizes whitespace.
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    key = text.casefold()
    if key in _EXACT_MISSING:
        return ""
    if any(re.search(pattern, key, flags=re.IGNORECASE) for pattern in _NON_VALUE_PATTERNS):
        return ""
    return text


def sanitize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Make every public table safe from NaN/None/Belirtilmedi cells."""
    if frame is None:
        return pd.DataFrame()
    out = frame.copy()
    for column in out.columns:
        if str(column).startswith("__"):
            continue
        out[column] = out[column].map(clean_cell)
    return out


def fill_ratio(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    values = frame[column].map(clean_cell)
    return float(values.ne("").mean())


def select_dense_columns(
    frame: pd.DataFrame,
    *,
    preferred: Sequence[str],
    mandatory: Sequence[str] = ("Banka", "Ürün"),
    trailing: Sequence[str] = (),
    min_fill: float = 0.25,
    min_optional: int = 4,
    max_optional: int = 10,
) -> list[str]:
    """Select an information-dense, category-specific table schema.

    Columns with little verified content are hidden instead of filling the
    dashboard with placeholder text. If the category is intrinsically sparse,
    the best-filled available columns are kept so the table still remains useful.
    """
    if frame is None or frame.empty:
        return []

    result: list[str] = []
    for column in mandatory:
        if column in frame.columns and column not in result:
            result.append(column)

    scored: list[tuple[str, float, int]] = []
    for idx, column in enumerate(preferred):
        if column not in frame.columns or column in result or column in trailing:
            continue
        ratio = fill_ratio(frame, column)
        if ratio > 0:
            scored.append((column, ratio, idx))

    selected = [item for item in scored if item[1] >= min_fill]
    if len(selected) < min_optional:
        # Keep profile order after choosing the strongest sparse columns.
        strongest = sorted(scored, key=lambda x: (-x[1], x[2]))[:min_optional]
        selected_names = {x[0] for x in selected}
        selected.extend(x for x in strongest if x[0] not in selected_names)

    selected = sorted(selected, key=lambda x: x[2])[:max_optional]
    for column, _, _ in selected:
        if column not in result:
            result.append(column)

    for column in trailing:
        if column in frame.columns and fill_ratio(frame, column) > 0 and column not in result:
            result.append(column)
    return result


def nonempty_records(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Convenience helper for CSV/detail surfaces."""
    cols = [c for c in columns if c in frame.columns]
    return sanitize_frame(frame[cols].copy())


def display_frame_with_missing_label(
    frame: pd.DataFrame,
    *,
    missing_label: str = "Belirtilmedi",
    preserve_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """Fill selected visible empty cells with a user-facing missing label.

    Column selection/density is performed before this helper is called, so
    this does not artificially make sparse columns look complete. It only
    prevents NaN/None/visual holes in columns that were already selected for
    display. URL/link columns can be preserved to keep them clickable.
    """
    out = sanitize_frame(frame)
    preserved = set(preserve_columns)
    for column in out.columns:
        if str(column).startswith("__") or column in preserved:
            continue
        out[column] = out[column].map(lambda value: clean_cell(value) or missing_label)
    return out
