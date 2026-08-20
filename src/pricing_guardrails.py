from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


# Bir fiyatlama satırı bu ifadelerden biriyle açıkça "örnek/temsili"
# olarak etiketlenmişse müşteri karşılaştırmasında güncel ürün fiyatı gibi
# kullanılmamalıdır. Bu satırlar kaynak incelemesi için saklanabilir; fakat
# product_pricing_tiers / karşılaştırma katmanına giremez.
EXAMPLE_ONLY_MARKERS = (
    "örnek",
    "ornek",
    "örneğ",
    "orneg",
    "sample",
    "example",
    "temsili",
    "temsilî",
    "representative example",
)


def _fold(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # Türkçe dotless-i NFKD/casefold sonrasında ayrı kalabilir.
    return text.replace("ı", "i")


def text_marks_example_only(value: object) -> bool:
    key = _fold(value)
    if not key:
        return False
    return any(_fold(marker) in key for marker in EXAMPLE_ONLY_MARKERS)


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key)
    try:
        return row[key]
    except Exception:
        return None


def is_example_only_pricing_row(row: Mapping[str, Any]) -> bool:
    """True ise satır headline/güncel ürün fiyatı olarak kullanılamaz.

    Yeni veri modelinde ``value_type=example`` birincil kanıttır. Eski kayıtlarda
    metadata henüz yoksa pricing_variant/source_text içindeki açık örnek
    işaretleri geriye dönük koruma sağlar.
    """

    value_type = str(_row_value(row, "value_type") or "").strip().casefold()
    if value_type:
        return value_type == "example"

    return text_marks_example_only(_row_value(row, "pricing_variant")) or text_marks_example_only(
        _row_value(row, "source_text")
    )


def is_headline_pricing_row(row: Mapping[str, Any]) -> bool:
    """Ana karşılaştırma tablosunda kullanılabilecek fiyatlama satırı mı?"""
    return not is_example_only_pricing_row(row)

def authoritative_pricing_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if not is_example_only_pricing_row(row)]


def sanitize_product_rate_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Ürün seviyesindeki örnek oranı sayısal güncel oran olmaktan çıkarır.

    Eğer açıklama alanı oranı açıkça örnek/temsili olarak niteliyorsa sayısal
    `profit_share_rate` temizlenir. Açıklama metni korunur; kullanıcı arayüzü
    bunu güncel oran olarak sıralayamaz/karşılaştıramaz.
    """

    out = dict(row)
    if text_marks_example_only(out.get("profit_share_rate_text")):
        out["profit_share_rate"] = None
    return out


def filter_authoritative_pricing_frame(frame):
    """Pandas DataFrame için UI/read-side son savunma katmanı.

    pandas modülünü burada import etmiyoruz; çağıran tarafın DataFrame'ini
    `.copy()` ile döndürmek yeterli ve modülü düşük bağımlılıklı tutuyor.
    """

    if frame is None or getattr(frame, "empty", True):
        return frame.copy() if hasattr(frame, "copy") else frame

    def _safe_value(value: object) -> object:
        try:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return None
        except Exception:
            pass
        return value

    mask = frame.apply(
        lambda item: not is_example_only_pricing_row(
            {
                "pricing_variant": _safe_value(item.get("pricing_variant")),
                "source_text": _safe_value(item.get("source_text")),
                "value_type": _safe_value(item.get("value_type")),
            }
        ),
        axis=1,
    )
    return frame.loc[mask].copy()


def sanitize_product_rate_frame(frame):
    """DataFrame üzerindeki ürün seviyeli örnek oranları sayısal alandan temizler."""
    if frame is None or getattr(frame, "empty", True):
        return frame.copy() if hasattr(frame, "copy") else frame

    out = frame.copy()
    if "profit_share_rate_text" not in out.columns or "profit_share_rate" not in out.columns:
        return out

    mask = out["profit_share_rate_text"].apply(text_marks_example_only)
    if mask.any():
        out.loc[mask, "profit_share_rate"] = None
    return out
