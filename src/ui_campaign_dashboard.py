from __future__ import annotations

import pandas as pd

from src.ui_table_density import sanitize_frame, select_dense_columns


CAMPAIGN_COLUMN_PROFILES: dict[str, tuple[str, ...]] = {
    "Kart / Taksit Kampanyası": (
        "Ana Fayda", "Taksit", "Hedef Kitle", "Min. Harcama", "Maks. Fayda",
        "Ödül", "Puan", "Başlangıç", "Bitiş", "Koşullar",
    ),
    "İndirim Kampanyası": (
        "Ana Fayda", "İndirim / İade", "Maks. Fayda", "Min. Harcama", "Ödül",
        "Hedef Kitle", "Başlangıç", "Bitiş", "Koşullar",
    ),
    "Puan Kampanyası": (
        "Ana Fayda", "Puan", "Ödül", "Min. Harcama", "Maks. Fayda", "Taksit",
        "Hedef Kitle", "Başlangıç", "Bitiş", "Koşullar",
    ),
    "Yeni Müşteri Kampanyası": (
        "Ana Fayda", "Ödül", "İndirim / İade", "Maks. Fayda", "Hedef Kitle",
        "Başlangıç", "Bitiş", "Koşullar",
    ),
    "Sigorta Kampanyası": (
        "Ana Fayda", "İndirim / İade", "Ödül", "Maks. Fayda", "Hedef Kitle", "Koşullar",
    ),
    "Alışveriş Finansmanı": (
        "Ana Fayda", "Finansman Tutarı", "Vade", "Kâr Payı", "Taksit",
        "Min. İşlem", "Maks. İşlem", "Hedef Kitle", "Başlangıç", "Bitiş", "Koşullar",
    ),
    "İhtiyaç Finansmanı": (
        "Ana Fayda", "Finansman Tutarı", "Vade", "Kâr Payı", "Taksit",
        "Min. İşlem", "Maks. İşlem", "Hedef Kitle", "Başlangıç", "Bitiş", "Koşullar",
    ),
    "Umre Finansmanı": (
        "Ana Fayda", "Finansman Tutarı", "Vade", "Kâr Payı", "Taksit", "Bitiş", "Koşullar",
    ),
    "Togg Taşıt Finansmanı": (
        "Ana Fayda", "Finansman Tutarı", "Vade", "Kâr Payı", "Hedef Kitle", "Bitiş", "Koşullar",
    ),
}

_FINANCE_HINTS = (
    "finansman", "leasing", "taksitlendirme",
)


def preferred_campaign_columns(category: str) -> tuple[str, ...]:
    if category in CAMPAIGN_COLUMN_PROFILES:
        return CAMPAIGN_COLUMN_PROFILES[category]
    key = str(category or "").casefold()
    if any(token in key for token in _FINANCE_HINTS):
        return (
            "Ana Fayda", "Finansman Tutarı", "Vade", "Kâr Payı", "Taksit",
            "Hedef Kitle", "Başlangıç", "Bitiş", "Koşullar",
        )
    if category == "Tümü":
        return (
            "Tür", "Ana Fayda", "Hedef Kitle", "Taksit", "İndirim / İade", "Puan",
            "Ödül", "Min. Harcama", "Maks. Fayda", "Bitiş", "Koşullar",
        )
    return (
        "Ana Fayda", "Hedef Kitle", "İndirim / İade", "Ödül", "Taksit", "Puan",
        "Min. Harcama", "Maks. Fayda", "Başlangıç", "Bitiş", "Koşullar",
    )


def public_campaign_columns(frame: pd.DataFrame, category: str) -> list[str]:
    if frame is None or frame.empty:
        return []
    # Large campaign universes need a slightly stronger threshold so the main
    # table stays full rather than becoming a sparse spreadsheet.
    threshold = 0.22 if category == "Tümü" else 0.18
    return select_dense_columns(
        sanitize_frame(frame),
        preferred=preferred_campaign_columns(category),
        mandatory=("Banka", "Kampanya"),
        trailing=("Resmî Kaynak",),
        min_fill=threshold,
        min_optional=5,
        max_optional=10,
    )
