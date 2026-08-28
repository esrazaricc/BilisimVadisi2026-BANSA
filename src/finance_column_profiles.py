from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd


@dataclass(frozen=True)
class FinanceColumnProfile:
    scope: str
    category_label: str
    preferred_columns: tuple[str, ...]
    always_show_columns: tuple[str, ...] = ()
    description: str = ""


# Ana karşılaştırma tablosu için kategoriye özel sütun politikaları.
# Buradaki amaç her finansman türünü aynı generic şablona zorlamak değil,
# müşterinin o ürün ailesinde gerçekten karar vermesini sağlayan alanları
# göstermek ve yayımlanmayan alanları tahmin etmemektir.
PROFILES: dict[tuple[str, str], FinanceColumnProfile] = {
    # ---------------- BİREYSEL ----------------
    ("bireysel", "Konut Finansmanı"): FinanceColumnProfile(
        scope="bireysel",
        category_label="Konut Finansmanı",
        preferred_columns=(
            "Kâr Payı / Fiyatlama",
            "Devlet Desteği / Sübvansiyon",
            "Azami Vade",
            "Finansman Oranı",
            "Tahsis Ücreti",
            "Ekspertiz Ücreti",
            "İpotek Tesis Ücreti",
        ),
        always_show_columns=(
            "Kâr Payı / Fiyatlama",
            "Azami Vade",
            "Finansman Oranı",
            "Tahsis Ücreti",
            "Ekspertiz Ücreti",
            "İpotek Tesis Ücreti",
        ),
        description="Konut karşılaştırmasında fiyatlama, vade, finansman oranı ve temel gayrimenkul masrafları esastır.",
    ),
    ("bireysel", "Taşıt Finansmanı"): FinanceColumnProfile(
        scope="bireysel",
        category_label="Taşıt Finansmanı",
        preferred_columns=(
            "Araç / Yaş Kapsamı",
            "Tutar / Değer Bazlı Koşullar",
            "Kâr Payı / Fiyatlama",
            "Vade / Ödeme",
            "Finansman Oranı",
            "Tahsis Ücreti",
            "Masraf / Ücretler",
        ),
        description="Taşıtta araç kapsamı ile araç değerine göre oran-vade kuralları önceliklidir.",
    ),
    ("bireysel", "İhtiyaç Finansmanı"): FinanceColumnProfile(
        scope="bireysel",
        category_label="İhtiyaç Finansmanı",
        preferred_columns=(
            "Limit / Finansman Tutarı",
            "Vade / Ödeme",
            "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti",
            "Teminat / Güvence",
            "Ödeme / Kullanım",
        ),
        description="İhtiyaç finansmanında limit, tutara göre vade, fiyatlama ve tahsis ücreti temel karşılaştırma alanlarıdır.",
    ),
    ("bireysel", "Gayrimenkul Finansmanı"): FinanceColumnProfile(
        scope="bireysel",
        category_label="Gayrimenkul Finansmanı",
        preferred_columns=(
            "Kullanım Amacı",
            "Limit / Finansman Tutarı",
            "Vade / Ödeme",
            "Finansman Oranı",
            "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti",
            "Ekspertiz Ücreti",
            "İpotek Tesis Ücreti",
            "Masraf / Ücretler",
        ),
        description="Arsa, iş yeri ve benzeri ürünlerde varlık türü, vade, finansman oranı ile ekspertiz/ipotek masrafları öne çıkar.",
    ),
    ("bireysel", "Alışveriş Finansmanı"): FinanceColumnProfile(
        scope="bireysel",
        category_label="Alışveriş Finansmanı",
        preferred_columns=(
            "Kullanım / Kanal",
            "Limit / Finansman Tutarı",
            "Vade / Ödeme",
            "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti",
            "Ürün Koşulları",
            "Maliyet / Avantaj",
        ),
        description="Alışveriş finansmanında kullanım kanalı, limit, taksit/vade ve fiyatlama esastır.",
    ),
    ("bireysel", "Diğer Bireysel Finansman"): FinanceColumnProfile(
        scope="bireysel",
        category_label="Diğer Bireysel Finansman",
        preferred_columns=(
            "Alt Tür",
            "Kullanım Amacı",
            "Finansman Yapısı",
            "Limit / Finansman Tutarı",
            "Vade / Ödeme",
            "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti",
            "Teminat / Güvence",
            "Kullanım / Kanal",
        ),
        description="Ana bireysel kategorilere girmeyen ürünlerde yalnız resmî kaynakta doğrulanan karar alanları gösterilir.",
    ),
    # ---------------- İŞ / TİCARİ ----------------
    ("ticari", "Ticari Finansman"): FinanceColumnProfile(
        scope="ticari",
        category_label="Ticari Finansman",
        preferred_columns=(
            "Kullanım Amacı",
            "Finansman Yapısı",
            "Finansman Limiti",
            "İşlem / Kanal Limiti",
            "Vade / Ödeme",
            "Para Birimi",
            "Teminat / Güvence",
            "Kullanım / Kanal",
        ),
        description="Ticari nakdi finansmanda finansman üst limiti ile işlem/kanal limiti birbirinden ayrılır; amaç, yapı, vade, teminat ve para birimi ayrıca karşılaştırılır.",
    ),
    ("ticari", "Gayri Nakdi Finansman"): FinanceColumnProfile(
        scope="ticari",
        category_label="Gayri Nakdi Finansman",
        preferred_columns=(
            "Enstrüman Türü",
            "Kullanım Alanı",
            "İşlem / Limit",
            "Para Birimi",
            "Vade / Ödeme",
            "Komisyon / Ücret",
            "Kullanım / Kanal",
        ),
        description="Gayri nakdi ürünlerde kâr oranından çok enstrüman türü, işlem limiti, para birimi, dış ticaret kullanımı ve güvence yapısı önemlidir.",
    ),
    ("ticari", "Tarım Finansmanı"): FinanceColumnProfile(
        scope="ticari",
        category_label="Tarım Finansmanı",
        preferred_columns=(
            "Kullanım Amacı",
            "Hedef Kitle",
            "Finansman Yapısı",
            "Ürün Koşulu",
            "Devlet Desteği / Sübvansiyon",
            "Finansman Limiti",
            "Finansman Oranı",
            "Kâr Payı / Fiyatlama",
            "Ödeme / Hasat Yapısı",
            "Teminat / Güvence",
        ),
        description="Tarım finansmanında faaliyet amacı, hedef kitle, finansman yapısı, limit/oran, fiyatlama ve hasat-ödeme koşulları öncelikli karşılaştırma alanlarıdır.",
    ),
    ("ticari", "Leasing / Finansal Kiralama"): FinanceColumnProfile(
        scope="ticari",
        category_label="Leasing / Finansal Kiralama",
        preferred_columns=(
            "Varlık / Yatırım Türü",
            "Finansman Oranı",
            "Vade / Kira Planı",
            "Para Birimi",
            "Maliyet / KDV Yapısı",
            "Kullanım / Kanal",
        ),
        description="Leasing karşılaştırmasında varlık amacı, finansman oranı, kira/vade yapısı ve resmî maliyet avantajları öne çıkar.",
    ),
    ("ticari", "Diğer İş / Ticari Finansman"): FinanceColumnProfile(
        scope="ticari",
        category_label="Diğer İş / Ticari Finansman",
        preferred_columns=(
            "Kullanım Amacı",
            "Finansman Yapısı",
            "Finansman Limiti",
            "Vade / Ödeme",
            "Teminat / Güvence",
            "Para Birimi",
            "Kullanım / Kanal",
        ),
        description="Diğer ticari ürünlerde finansman limiti ile işlem/kanal limiti ayrılır; yalnız doğrulanabilir karar alanları gösterilir.",
    ),
}


_PLACEHOLDERS = {
    "",
    "none",
    "nan",
    "belirtilmedi",
    "—",
    "-",
    "kaynakta yayımlanmamış",
    "kaynakta sayısal değer yayımlanmamış",
    "kaynakta sayısal değer yok",
    "uygulanamaz",
}


def is_missing_display_value(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value).strip()
    if text.casefold() in _PLACEHOLDERS:
        return True
    if text.casefold().startswith("sayısal koşullar kaynakta yayımlanmamış"):
        return True
    return False


def join_verified_values(*values: object, separator: str = " · ") -> str:
    """Yalnız doğrulanmış/gösterilebilir değerleri birleştirir.

    Eksik alan için tahmin üretmez. Aynı metni iki kez eklemez.
    """
    result: list[str] = []
    for value in values:
        if is_missing_display_value(value):
            continue
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return separator.join(result) if result else "—"


def get_profile(scope: str, category_label: str) -> FinanceColumnProfile:
    key = (str(scope or "").strip().casefold(), str(category_label or "").strip())
    profile = PROFILES.get(key)
    if profile:
        return profile

    # Güvenli fallback: generic ve çoğu boş sütun oluşturmak yerine yalnız
    # ortak, resmî kaynaktan doğrulanabilir alanları değerlendirmeye al.
    return FinanceColumnProfile(
        scope=key[0] or "belirsiz",
        category_label=key[1] or "Belirsiz",
        preferred_columns=(
            "Kullanım Amacı",
            "Finansman Yapısı",
            "Limit / Finansman Tutarı",
            "Vade / Ödeme",
            "Teminat / Güvence",
            "Para Birimi",
            "Kullanım / Kanal",
        ),
        description="Yalnız doğrulanmış ortak karar alanları gösterilir.",
    )


def column_has_meaningful_data(frame: pd.DataFrame, column: str) -> bool:
    if column not in frame.columns:
        return False
    return any(not is_missing_display_value(value) for value in frame[column].tolist())


def select_main_table_columns(
    frame: pd.DataFrame,
    scope: str,
    category_label: str,
    *,
    include_fee_source: bool = True,
) -> list[str]:
    """Kategoriye uygun ana karşılaştırma sütunlarını döndürür.

    - Banka/Ürün her zaman gösterilir.
    - Bir sütunda hiçbir doğrulanmış değer yoksa sütun gizlenir.
    - ``always_show_columns`` yalnız konut gibi kullanıcı tarafından özellikle
      sabitlenmiş alanlarda kullanılır.
    - Ürün Kaynağı ve varsa Ücret Kaynağı sona eklenir. Fiyatlama Kaynağı ana tabloda gösterilmez.
    """
    profile = get_profile(scope, category_label)
    columns: list[str] = ["Banka", "Ürün"]

    for column in profile.preferred_columns:
        if column not in frame.columns:
            continue
        if column in profile.always_show_columns or column_has_meaningful_data(frame, column):
            if column not in columns:
                columns.append(column)

    if "Ürün Kaynağı" in frame.columns:
        columns.append("Ürün Kaynağı")

    if (
        include_fee_source
        and "Ücret Kaynağı" in frame.columns
        and column_has_meaningful_data(frame, "Ücret Kaynağı")
    ):
        columns.append("Ücret Kaynağı")

    return columns
