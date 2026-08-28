from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FinanceCategory:
    key: str
    label: str
    order: int
    scope: str
    description: str


SCOPE_LABELS = {
    "bireysel": "Bireysel Finansman",
    "ticari": "İş / Ticari Finansman",
}

SCOPE_ORDER = {
    "bireysel": 10,
    "ticari": 20,
}


CATEGORIES: tuple[FinanceCategory, ...] = (
    # Bireysel karşılaştırma kategorileri
    FinanceCategory(
        "konut_finansmani",
        "Konut Finansmanı",
        10,
        "bireysel",
        "Konut, ilk ev, yeşil/çevreci konut ve benzeri konut edinim ürünleri.",
    ),
    FinanceCategory(
        "tasit_finansmani",
        "Taşıt Finansmanı",
        20,
        "bireysel",
        "Otomobil ve bankanın araç finansmanı ailesinde yayımladığı taşıt ürünleri.",
    ),
    FinanceCategory(
        "ihtiyac_finansmani",
        "İhtiyaç Finansmanı",
        30,
        "bireysel",
        "Genel ihtiyaç ile eğitim, sağlık, kira, hac/umre ve benzeri bireysel ihtiyaç ürünleri.",
    ),
    FinanceCategory(
        "gayrimenkul_finansmani",
        "Gayrimenkul Finansmanı",
        40,
        "bireysel",
        "Arsa, iş yeri, 2B ve konut dışındaki bireysel gayrimenkul ürünleri.",
    ),
    FinanceCategory(
        "alisveris_finansmani",
        "Alışveriş Finansmanı",
        50,
        "bireysel",
        "Bayide, mağazada, QR/online veya limit bazlı alışveriş finansmanı ürünleri.",
    ),
    FinanceCategory(
        "diger_bireysel_finansman",
        "Diğer Bireysel Finansman",
        90,
        "bireysel",
        "Beş ana kategoriye güvenle yerleştirilemeyen bireysel finansman ürünleri.",
    ),
    # İş / ticari karşılaştırma kategorileri. Bunlar yalnız scope=ticari
    # kayıtlarından oluşur; ürün adında 'ticari' geçmesi tek başına yeterli değildir.
    FinanceCategory(
        "ticari_finansman",
        "Ticari Finansman",
        110,
        "ticari",
        "Bankanın ticari/KOBİ/kurumsal kapsamda yayımladığı nakdi ticari finansman ürünleri.",
    ),
    FinanceCategory(
        "gayri_nakdi_finansman",
        "Gayri Nakdi Finansman",
        120,
        "ticari",
        "Teminat mektubu, akreditif ve benzeri gayri nakdi finansman ürünleri.",
    ),
    FinanceCategory(
        "tarim_finansmani",
        "Tarım Finansmanı",
        130,
        "ticari",
        "Bankanın iş/ticari kapsamda yayımladığı tarım finansmanı ürünleri.",
    ),
    FinanceCategory(
        "leasing_finansal_kiralama",
        "Leasing / Finansal Kiralama",
        140,
        "ticari",
        "Bankanın iş/ticari kapsamda yayımladığı leasing veya finansal kiralama ürünleri.",
    ),
    FinanceCategory(
        "diger_ticari_finansman",
        "Diğer İş / Ticari Finansman",
        190,
        "ticari",
        "Dört ana ticari kategoriye güvenle yerleştirilemeyen doğrulanmış iş/ticari ürünleri.",
    ),
)

CATEGORY_BY_KEY = {item.key: item for item in CATEGORIES}
CATEGORY_BY_LABEL = {item.label: item for item in CATEGORIES}


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold().replace("ı", "i")).strip("_")


def normalize_scope(value: Any) -> str:
    key = _key(value)
    if key in {"bireysel", "individual", "retail", "personal"}:
        return "bireysel"
    if key in {"ticari", "commercial", "business", "kobi", "kurumsal", "isim_icin", "isimicin"}:
        return "ticari"
    return key or "belirsiz"


def scope_label(scope: Any) -> str:
    normalized = normalize_scope(scope)
    return SCOPE_LABELS.get(normalized, str(scope or "Belirsiz"))


def scope_order(scope: Any) -> int:
    return SCOPE_ORDER.get(normalize_scope(scope), 999)


def classify_finance_category(
    product_family: Any,
    product_name: Any = None,
    scope: Any = None,
) -> str:
    """Return BANSA's normalized comparison category key.

    Sınıflandırma muhafazakârdır. Önce ``scope`` belirlenir. İş/ticari kayıtlar
    asla bireysel kategoriye, bireysel kayıtlar da yalnız ürün adında ``ticari``
    geçtiği için iş/ticari kategoriye taşınmaz. Bankanın resmî product_family
    değeri birincil sınıflandırma kanıtıdır; ürün adı yalnız belirsiz şemsiye
    ailelerde yardımcı sinyal olarak kullanılır.
    """
    family = _key(product_family)
    product = _key(product_name)
    normalized_scope = normalize_scope(scope)

    # ------------------------------------------------------------
    # İŞ / TİCARİ
    # ------------------------------------------------------------
    # Scope=ticari ise önce ticari taksonomi uygulanır. Bu kritik kural,
    # ürün adındaki kelimelerin müşteriye yanlış alan göstermesini engeller.
    if normalized_scope == "ticari":
        if "gayri_nakdi" in family or "gayrinakdi" in family:
            return "gayri_nakdi_finansman"
        if "tarim" in family:
            return "tarim_finansmani"
        if any(token in family for token in ("leasing", "finansal_kiralama", "kiralama")):
            return "leasing_finansal_kiralama"
        if any(token in family for token in ("ticari", "nakdi_finansman", "kobi", "kurumsal")):
            return "ticari_finansman"

        # Belirsiz ticari şemsiye ailelerinde ürün adı yalnız yardımcıdır.
        if "gayri_nakdi" in product or "gayrinakdi" in product:
            return "gayri_nakdi_finansman"
        if "tarim" in product:
            return "tarim_finansmani"
        if any(token in product for token in ("leasing", "finansal_kiralama")):
            return "leasing_finansal_kiralama"

        return "diger_ticari_finansman"

    # ------------------------------------------------------------
    # BİREYSEL
    # ------------------------------------------------------------
    # Primary explicit families.
    if "konut" in family:
        return "konut_finansmani"
    if any(token in family for token in ("arac", "tasit")):
        return "tasit_finansmani"
    if "ihtiyac" in family:
        return "ihtiyac_finansmani"
    if "alisveris" in family:
        return "alisveris_finansmani"
    if any(token in family for token in ("arsa", "isyeri", "is_yeri", "gayrimenkul")):
        return "gayrimenkul_finansmani"

    # Ambiguous umbrella families can only be normalized when the product name
    # itself makes the target category explicit.
    if "surdurulebilir" in family or family in {"", "finansman"}:
        if "konut" in product:
            return "konut_finansmani"
        if any(token in product for token in ("arac", "tasit", "togg", "otomobil")):
            return "tasit_finansmani"
        if any(token in product for token in ("arsa", "is_yeri", "isyeri", "2b", "gayrimenkul")):
            return "gayrimenkul_finansmani"
        if any(token in product for token in ("alisveris", "bayide", "veresiye", "taksitli_urun", "bana_bunu_al")):
            return "alisveris_finansmani"
        if any(token in product for token in ("ihtiyac", "egitim", "saglik", "kira", "umre", "hac")):
            return "ihtiyac_finansmani"

    return "diger_bireysel_finansman"


def category_label(category_key: str) -> str:
    item = CATEGORY_BY_KEY.get(category_key)
    if item:
        return item.label
    return str(category_key or "Belirsiz")


def category_order(category_key: str) -> int:
    item = CATEGORY_BY_KEY.get(category_key)
    if item:
        return item.order
    return 999


def category_scope(category_key: str) -> str:
    item = CATEGORY_BY_KEY.get(category_key)
    return item.scope if item else "belirsiz"


def categories_for_scope(scope: Any) -> tuple[FinanceCategory, ...]:
    normalized = normalize_scope(scope)
    return tuple(item for item in CATEGORIES if item.scope == normalized)


def is_primary_retail_category(category_key: str) -> bool:
    return category_key in {
        "konut_finansmani",
        "tasit_finansmani",
        "ihtiyac_finansmani",
        "gayrimenkul_finansmani",
        "alisveris_finansmani",
    }


def is_business_category(category_key: str) -> bool:
    return category_scope(category_key) == "ticari"
