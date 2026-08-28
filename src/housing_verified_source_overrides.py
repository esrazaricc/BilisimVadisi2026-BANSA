from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from src.pricing_guardrails import authoritative_pricing_rows


STANDARD_HOME_RULES = [
    {"max_value": 5_000_000, "ab": 90.0, "c": 80.0, "other": 70.0},
    {"min_value": 5_000_000, "max_value": 7_000_000, "ab": 80.0, "c": 70.0, "other": 60.0},
    {"min_value": 7_000_000, "max_value": 10_000_000, "ab": 70.0, "c": 60.0, "other": 50.0},
    {"min_value": 10_000_000, "max_value": 20_000_000, "ab": 50.0, "c": 40.0, "other": 30.0},
    {"min_value": 20_000_000, "ab": 40.0, "c": 30.0, "other": 20.0},
]

ADDITIONAL_HOME_RULES = [
    {"max_value": 5_000_000, "ab": 22.5, "c": 20.0, "other": 17.5},
    {"min_value": 5_000_000, "max_value": 7_000_000, "ab": 20.0, "c": 17.5, "other": 15.0},
    {"min_value": 7_000_000, "max_value": 10_000_000, "ab": 17.5, "c": 15.0, "other": 12.5},
    {"min_value": 10_000_000, "max_value": 20_000_000, "ab": 12.5, "c": 10.0, "other": 7.5},
    {"min_value": 20_000_000, "ab": 10.0, "c": 7.5, "other": 5.0},
]

ALBARAKA_PRODUCT_URL = (
    "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/"
    "konut-finansmani/konut-finansmani"
)
ALBARAKA_FEE_URL = "https://www.albaraka.com.tr/tr/urun-ve-hizmet-ucretleri"
ALBARAKA_COST_PDF = (
    "https://www.albaraka.com.tr/documents/urun-ve-hizmet-ucretleri/"
    "web-site-%28yillik-maliyet-hesaplama%29.pdf"
)
DUNYA_PRODUCT_URL = (
    "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/konut-finansmani"
)
DUNYA_FEE_PDF = (
    "https://dunyakatilim.com.tr/content/files/uploads/2516/"
    "dk-bireysel-ucrt11-180526.pdf"
)

KUVEYT_REGULAR_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/konut-finansmani"
)
KUVEYT_FIRST_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/ilk-evim-konut-finansmani"
)
KUVEYT_GREEN_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "surdurulebilir-finansmanlar/yesil-konut-finansmani"
)
KUVEYT_GURBET_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/gurbetten-silaya-gayrimenkul-finansmani"
)
KUVEYT_FEE_PDF = (
    "https://www.kuveytturk.com.tr/medium/"
    "finansal-tuketici-urun-ve-hizmet-ucret-tablosu-4015.pdf"
)

TURKIYE_FINANS_URL = (
    "https://www.turkiyefinans.com.tr/tr-tr/bireysel/"
    "konut-finansmani/sayfalar/konut-finansmani.aspx"
)

KUVEYT_GREEN_3M_TEXT = (
    "Web sitesi aylık kâr oranları 3.000.000 TL'ye kadar olan finansman "
    "talepleri için geçerlidir. 3.000.000 TL ve üzeri finansman taleplerinde "
    "şube ile iletişime geçilmelidir. Bu tutar ekspertiz değeri değildir."
)

TF_PRICING_BUNDLE_TEXT = (
    "Maliyet tablosundaki kâr oranları; Yedek Hesap, DASK, Finansman Ferdi "
    "Kaza Sigortası, Konut Sigortası ve Otomatik Fatura Ödeme Talimatı "
    "ürünlerinin tamamının finansman başvurusu ile birlikte alınması şartıyla uygulanır."
)
TF_APPRAISAL_TEXT = (
    "100.000 TL örnek ödeme tablosunda ekspertiz/değerleme ücreti 16.500 TL'dir. "
    "Bu tutar minimum maliyetler üzerinden hesaplanır; resmî harç, taşınmaz alanı, "
    "mevcut durum ve lokasyona göre değişebilir. Ekspertiz maliyetinin 1,5 katı "
    "hesapta bloke edilir, işlem sonrasında gerçek maliyet tahsil edilip kalan bloke çözülür."
)
TF_INSURANCE_TEXT = (
    "Konut sigortası ve DASK primleri lokasyon ve m²'ye; finansman güvence "
    "sigortası müşterinin cinsiyeti, yaşı vb. kriterlere göre değişir ve bu "
    "sigorta primleri yıllık maliyet hesaplamasına dahil edilmez."
)


def _fee(
    fee_type: str,
    fee_label: str,
    *,
    rate: float | None = None,
    amount: float | None = None,
    waived: bool = False,
    note: str,
) -> dict[str, Any]:
    return {
        "fee_type": fee_type,
        "fee_label": fee_label,
        "waived": waived,
        "amount": amount,
        "rate": rate,
        "note": note,
    }


def _offer(
    rule_type: str,
    label: str,
    condition: str,
    source: str,
    *,
    max_amount: float | None = None,
) -> dict[str, Any]:
    return {
        "rule_type": rule_type,
        "rule_label": label,
        "min_amount": None,
        "max_amount": max_amount,
        "min_inclusive": False,
        "max_inclusive": True,
        "max_installments": None,
        "max_maturity_months": None,
        "interest_free": False,
        "condition_text": condition,
        "source_text": source,
    }


def _ownership_offer(source: str) -> dict[str, Any]:
    return _offer(
        "ownership_condition",
        "Mevcut Konut Sahipliği Koşulu",
        (
            "Kendisinin/eşinin/18 yaş altı çocuklarının malik olduğu en az bir "
            "konut varsa kullanılabilecek finansman tutarı %75 oranında azalır."
        ),
        source,
    )


VERIFIED_FEES: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("Albaraka Türk", "Konut Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Albaraka Ürün ve Hizmet Ücretleri sayfasında Konut Finansmanı "
                "tahsis ücreti %0,50 olarak yayımlanır. BSMV muaftır. "
                f"Kaynak: {ALBARAKA_FEE_URL}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            note=(
                "3. kişilere ödenen gerçek maliyet tutarı kadar tahsil edilir; "
                f"BSMV muaftır. Kaynak: {ALBARAKA_FEE_URL}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek / Taşınmaz Rehin Ücreti",
            note=(
                "Taşınır ve taşınmaz rehin işlemlerinde 3. kişilere ödenen "
                "gerçek maliyet tutarı kadar tahsil edilir; BSMV muaftır. "
                f"Kaynak: {ALBARAKA_FEE_URL}"
            ),
        ),
    ],
    ("Dünya Katılım", "Konut Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Dünya Katılım Finansal Tüketiciler Ürün ve Hizmet Ücret "
                f"Tablosunda Konut Finansmanı tahsis ücreti %0,50. Kaynak: {DUNYA_FEE_PDF}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            amount=20_778.0,
            note=(
                "Ürün sayfasında bu sayısal ücret yayımlanmıyor. Ayrı resmî ücret "
                "tablosunda ekspertiz için asgari 20.778 TL yayımlanıyor. Hizmet üçüncü "
                "kişiden alınırsa üçüncü kişiye ödenen gerçek tutar tahsil edilir; "
                "varlığın değeri, brüt alanı ve resmî tarifelere göre değişebilir. "
                f"Ürün kaynağı: {DUNYA_PRODUCT_URL} | Ücret kaynağı: {DUNYA_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=3_000.0,
            note=(
                "Ürün sayfasında bu sayısal ücret yayımlanmıyor. Ayrı resmî ücret "
                "tablosunda ipotek tesis için asgari 3.000 TL yayımlanıyor. Hizmet "
                "üçüncü kişiden alınırsa üçüncü kişiye ödenen gerçek tutar tahsil "
                "edilir; taşınmaz adedine göre değişebilir. "
                f"Ürün kaynağı: {DUNYA_PRODUCT_URL} | Ücret kaynağı: {DUNYA_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_release",
            "İpotek Fek Ücreti",
            amount=3_000.0,
            note=(
                "Resmî ücret tablosunda asgari 3.000 TL'dir; ipoteğin fekkine "
                "konu taşınmaz adedine göre değişebilir. "
                f"Kaynak: {DUNYA_FEE_PDF}"
            ),
        ),
    ],
    ("Kuveyt Türk", "Konut Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Resmî ürün sayfasında tahsis ücreti finansman tutarının %0,5'i "
                "olarak belirtilir. 2026 genel ücret tarifesi de Konut Finansmanı "
                f"için %0,50 oranını doğrular. Kaynaklar: {KUVEYT_REGULAR_URL} | {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            amount=23_645.0,
            note=(
                "Resmî kaynaklar birbiriyle farklı değer yayımlıyor. Güncel ürün "
                "sayfasında ekspertiz ücreti asgari 23.203 TL ve lokasyona göre değişken "
                "olarak açıklanıyor. Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri "
                "tablosunda ise ekspertiz için asgari 23.645 TL (29.07.2026) yer alıyor "
                "ve gerçek masraf tutarı kadar tahsil edildiği belirtiliyor. Bu nedenle "
                "tek bir tutar kesin ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_REGULAR_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=4_500.0,
            note=(
                "Ürün sayfası ipotek tesis işlemlerinde maliyet kadar ücret tahsil "
                "edildiğini belirtir ancak sayısal bir ipotek tesis tutarı yayımlamaz. "
                "Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri tablosunda Konut "
                "Finansmanı için asgari 4.500 TL yer alır ve gerçek masraf tutarı kadar "
                "tahsil edildiği belirtilir. Bu tutar ürün sayfasında yayımlanan sabit "
                "bir ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_REGULAR_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
    ],
    ("Kuveyt Türk", "İlk Evim Konut Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Resmî ürün sayfasında tahsis ücreti finansman tutarının %0,5'i "
                "olarak belirtilir. 2026 genel ücret tarifesi de Konut Finansmanı "
                f"için %0,50 oranını doğrular. Kaynaklar: {KUVEYT_FIRST_URL} | {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            amount=23_645.0,
            note=(
                "Resmî kaynaklar birbiriyle farklı değer yayımlıyor. İlk Evim ürün "
                "sayfasında ekspertiz ücreti asgari 23.203 TL ve lokasyona göre değişken "
                "olarak açıklanıyor. Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri "
                "tablosunda ise ekspertiz için asgari 23.645 TL (29.07.2026) yer alıyor "
                "ve gerçek masraf tutarı kadar tahsil edildiği belirtiliyor. Bu nedenle "
                "tek bir tutar kesin ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_FIRST_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=4_500.0,
            note=(
                "İlk Evim ürün sayfası ipotek tesis işlemlerinde maliyet kadar ücret "
                "tahsil edildiğini belirtir ancak sayısal bir ipotek tesis tutarı yayımlamaz. "
                "Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri tablosunda Konut "
                "Finansmanı için asgari 4.500 TL yer alır ve gerçek masraf tutarı kadar "
                "tahsil edildiği belirtilir. Bu tutar İlk Evim sayfasında yayımlanan "
                "sabit bir ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_FIRST_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
    ],
    ("Kuveyt Türk", "Yeşil Konut Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Yeşil Konut ürün sayfası tahsis ücretinin peşin tahsil edildiğini "
                "belirtir; sayfada yüzdesi ayrıca yazılmadığı için oran Kuveyt Türk'ün "
                "2026 genel Konut Finansmanı ücret tarifesindeki %0,50 kaydından alınır. "
                f"Kaynaklar: {KUVEYT_GREEN_URL} | {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            amount=23_645.0,
            note=(
                "Resmî kaynaklar birbiriyle farklı değer yayımlıyor. Yeşil Konut ürün "
                "sayfasında ekspertiz ücreti asgari 23.203 TL ve lokasyona göre değişken "
                "olarak açıklanıyor. Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri "
                "tablosunda ise ekspertiz için asgari 23.645 TL (29.07.2026) yer alıyor "
                "ve gerçek masraf tutarı kadar tahsil edildiği belirtiliyor. Bu nedenle "
                "tek bir tutar kesin ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_GREEN_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=4_500.0,
            note=(
                "Yeşil Konut ürün sayfası ipotek tesis işlemlerinde maliyet kadar ücret "
                "tahsil edildiğini belirtir ancak sayısal bir ipotek tesis tutarı yayımlamaz. "
                "Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri tablosunda Konut "
                "Finansmanı için asgari 4.500 TL yer alır ve gerçek masraf tutarı kadar "
                "tahsil edildiği belirtilir. Bu tutar Yeşil Konut sayfasında yayımlanan "
                "sabit bir ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_GREEN_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
    ],
    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            note=(
                "Resmî ürün sayfasında tahsis ücreti finansman tutarının %0,5'i "
                "olarak belirtilir. 2026 genel ücret tarifesi de Konut Finansmanı "
                f"için %0,50 oranını doğrular. Kaynaklar: {KUVEYT_GURBET_URL} | {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz Ücreti",
            amount=23_645.0,
            note=(
                "Resmî kaynaklar birbiriyle farklı değer yayımlıyor. Gurbetten Sılaya "
                "ürün sayfasında ekspertiz ücreti asgari 23.203 TL ve lokasyona göre "
                "değişken olarak açıklanıyor. Ayrı Finansal Tüketici Ürün ve Hizmet "
                "Ücretleri tablosunda ise ekspertiz için asgari 23.645 TL (29.07.2026) "
                "yer alıyor ve gerçek masraf tutarı kadar tahsil edildiği belirtiliyor. "
                "Bu nedenle tek bir tutar kesin ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_GURBET_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=4_500.0,
            note=(
                "Gurbetten Sılaya ürün sayfası ipotek tesis işlemlerinde maliyet kadar "
                "ücret tahsil edildiğini belirtir ancak sayısal bir ipotek tesis tutarı yayımlamaz. "
                "Ayrı Finansal Tüketici Ürün ve Hizmet Ücretleri tablosunda Konut "
                "Finansmanı için asgari 4.500 TL yer alır ve gerçek masraf tutarı kadar "
                "tahsil edildiği belirtilir. Bu tutar Gurbetten Sılaya sayfasında yayımlanan "
                "sabit bir ürün ücreti gibi gösterilmemelidir. "
                f"Ürün kaynağı: {KUVEYT_GURBET_URL} | Ücret kaynağı: {KUVEYT_FEE_PDF}"
            ),
        ),
    ],
    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"): [
        _fee(
            "allocation",
            "Tahsis Ücreti",
            rate=0.50,
            amount=500.0,
            note=(
                "Tahsis ücreti vergiler hariç finansman tutarının binde 5'i (%0,50). "
                "100.000 TL örnek ödeme tablosunda 500 TL'dir. "
                f"Kaynak: {TURKIYE_FINANS_URL}"
            ),
        ),
        _fee(
            "appraisal",
            "Ekspertiz (Değerleme) Ücreti",
            amount=16_500.0,
            note=(
                "100.000 TL örnek ödeme tablosundaki minimum maliyet 16.500 TL'dir; "
                "resmî harç, taşınmaz alanı, mevcut durum ve lokasyona göre değişebilir. "
                "Ekspertiz maliyetinin 1,5 katı kadar hesaba bloke tesis edilir; işlem "
                "sonrasında gerçek maliyet tahsil edilip kalan bloke çözülür. "
                f"Kaynak: {TURKIYE_FINANS_URL}"
            ),
        ),
        _fee(
            "mortgage_establishment",
            "İpotek Tesis Ücreti",
            amount=3_000.0,
            note=(
                "100.000 TL örnek ödeme tablosunda ipotek tesis ücreti 3.000 TL'dir. "
                "Gerçek tutar ipoteği tesis eden firmanın bankaya faturalandırdığı "
                f"tutar kadardır. Kaynak: {TURKIYE_FINANS_URL}"
            ),
        ),
    ],
}

VERIFIED_OFFERS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("Kuveyt Türk", "Konut Finansmanı"): [
        _ownership_offer(KUVEYT_REGULAR_URL),
    ],
    ("Kuveyt Türk", "Yeşil Konut Finansmanı"): [
        _ownership_offer(KUVEYT_GREEN_URL),
        _offer(
            "pricing_validity",
            "Web Kâr Oranı Geçerlilik Sınırı",
            KUVEYT_GREEN_3M_TEXT,
            KUVEYT_GREEN_URL,
            max_amount=3_000_000.0,
        ),
    ],
    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"): [
        _ownership_offer(KUVEYT_GURBET_URL),
    ],
    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"): [
        _offer(
            "pricing_bundle",
            "Maliyet Tablosu Fiyatlama Koşulu",
            TF_PRICING_BUNDLE_TEXT,
            TURKIYE_FINANS_URL,
        ),
        _offer(
            "appraisal_cost_condition",
            "Ekspertiz Ücreti ve Bloke Koşulu",
            TF_APPRAISAL_TEXT,
            TURKIYE_FINANS_URL,
        ),
        _offer(
            "insurance_cost_condition",
            "Sigorta Primlerinin Değişkenliği",
            TF_INSURANCE_TEXT,
            TURKIYE_FINANS_URL,
        ),
    ],
}


def normalize_product_name(value: object) -> str:
    return str(value or "").strip().rstrip("*").strip()


def _load_rules(raw: object) -> dict[str, list[dict[str, Any]]]:
    if isinstance(raw, dict):
        value = deepcopy(raw)
    else:
        try:
            value = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            value = {}
    if not isinstance(value, dict):
        value = {}
    for key in (
        "category_rules",
        "amount_maturity_rules",
        "pricing_tiers",
        "fee_rules",
        "offer_rules",
    ):
        if not isinstance(value.get(key), list):
            value[key] = []
    return value


def _compact_housing_rules(rows: list[dict[str, Any]]) -> str:
    def band(row: dict[str, Any]) -> str:
        lo, hi = row.get("min_value"), row.get("max_value")
        if lo is None and hi is not None:
            return f"≤{int(hi / 1_000_000)}M"
        if lo is not None and hi is not None:
            return f"{int(lo / 1_000_000)}–{int(hi / 1_000_000)}M"
        if lo is not None:
            return f">{int(lo / 1_000_000)}M"
        return "Tüm değerler"

    def fmt(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value).replace(".", ",")

    return " · ".join(
        f"{band(row)} {fmt(row['ab'])}/{fmt(row['c'])}/{fmt(row['other'])}"
        for row in rows
    )


def canonical_housing_json(*, standard: bool, additional: bool) -> str:
    return json.dumps(
        {
            "standard_home": deepcopy(STANDARD_HOME_RULES) if standard else [],
            "additional_home": deepcopy(ADDITIONAL_HOME_RULES) if additional else [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def canonical_housing_text(*, standard: bool, additional: bool) -> tuple[str | None, str | None]:
    return (
        _compact_housing_rules(STANDARD_HOME_RULES) if standard else None,
        _compact_housing_rules(ADDITIONAL_HOME_RULES) if additional else None,
    )


def apply_verified_housing_product_overrides(row: dict[str, Any]) -> dict[str, Any]:
    """
    Generic extractor'ın eksik/yanlış çıkarabileceği ve resmî kaynakla
    doğrulanmış konut bilgilerini düzeltir.

    Bilinmeyen bir oran/vade kesinlikle uydurulmaz.
    """
    out = dict(row)
    bank = str(out.get("bank_name") or "").strip()
    product = normalize_product_name(out.get("product_name"))
    key = (bank, product)

    rules = _load_rules(out.get("finance_rules_json"))

    # EMLAK_HOUSING_VERIFIED_V1
    _emlak_products = {
        "Birlikte Konut Finansman\u0131",
        "G\u00f6nl\u00fcne G\u00f6re Konut Finansman\u0131",
        "Kentsel D\u00f6n\u00fc\u015f\u00fcm Finansman\u0131",
        "Konut Finansman\u0131",
        "Memlekette Konut Finansman\u0131",
        "Tamamlay\u0131c\u0131 Konut Finansman\u0131 | T\u00fcrkiye Emlak Kat\u0131l\u0131m Bankas\u0131",
        "\u00c7evreci Konut Finansman\u0131",
    }

    if (
        bank == "T\u00fcrkiye Emlak Kat\u0131l\u0131m"
        and product in _emlak_products
    ):
        _emlak_fee_url = (
            "https://asset.emlakkatilim.com.tr/documents/"
            "urun-ve-hizmet-ucretleri/"
            "breysel-bankacilik-urun-ve-hzmet-ucretler-2026-tr.pdf"
        )

        rules["fee_rules"] = [
            _fee(
                "allocation",
                "Tahsis \u00dccreti",
                rate=0.50,
                note=(
                    "2026 Bireysel Bankac\u0131l\u0131k \u00dcr\u00fcn ve Hizmet "
                    "\u00dccretleri tablosunda Konut Finansman\u0131 tahsis "
                    "\u00fccreti i\u015flem tutar\u0131n\u0131n %0,50'sidir; "
                    "BSMV'den muaft\u0131r. "
                    f"Kaynak: {_emlak_fee_url}"
                ),
            ),
            _fee(
                "appraisal",
                "Ekspertiz \u00dccreti",
                amount=16500.0,
                note=(
                    "Resmi 2026 ucret tarifesinde asgari 16.500 TL'dir. "
                    "Tas\u0131nmazin niteligi, adedi ve alanina gore degisebilir; "
                    "fiili maliyet kadar tahsil edilir. "
                    f"Kaynak: {_emlak_fee_url}"
                ),
            ),
            _fee(
                "mortgage_establishment",
                "Tas\u0131n\u0131r / Tas\u0131nmaz Rehin \u00dccreti",
                amount=3684.0,
                note=(
                    "Resmi 2026 ucret tarifesinde 3.684 TL yayimlanmistir; "
                    "ucuncu kisi/kurum maliyeti aynen yansitilir. "
                    f"Kaynak: {_emlak_fee_url}"
                ),
            ),
        ]

        _display = rules.setdefault("display_metadata", {})

        if not isinstance(_display, dict):
            _display = {}
            rules["display_metadata"] = _display

        if product == "Konut Finansman\u0131":
            out["maximum_maturity_months"] = 120
            out["maximum_financing_ratio"] = 80.0
            out["maturity_rules_text"] = "Azami 120 aya kadar"
            out["financing_ratio_rules_text"] = (
                "Ekspertiz de\u011ferinin %80'ine kadar"
            )

        elif product == "Memlekette Konut Finansman\u0131":
            out["maximum_maturity_months"] = 120
            out["maximum_financing_ratio"] = 80.0
            out["maturity_rules_text"] = (
                "TL: 120 aya kadar \u00b7 USD/EUR: azami 60 ay"
            )
            out["financing_ratio_rules_text"] = (
                "Ekspertiz de\u011ferinin %80'ine kadar"
            )
            _display["currency_maturity_note"] = (
                "TL: 120 aya kadar \u00b7 USD/EUR: azami 60 ay"
            )
            _display["eligibility_condition"] = (
                "Finansman kullanacak ki\u015finin yurtd\u0131\u015f\u0131nda "
                "yerle\u015fik olmas\u0131 gerekir."
            )

        elif product == "Kentsel D\u00f6n\u00fc\u015f\u00fcm Finansman\u0131":
            out["maximum_maturity_months"] = 120
            out["maturity_rules_text"] = (
                "G\u00fc\u00e7lendirme / Konut: 120 aya kadar \u00b7 "
                "\u0130\u015fyeri: 84 aya kadar"
            )

        elif product == (
            "Tamamlay\u0131c\u0131 Konut Finansman\u0131 | "
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m Bankas\u0131"
        ):
            out["maximum_maturity_months"] = 120
            out["maturity_rules_text"] = (
                "Yaln\u0131z TL \u00b7 azami 120 ay"
            )
            _display["financing_condition"] = (
                "BDDK konut finansman\u0131 s\u0131n\u0131rlamalar\u0131na tabi"
            )
            _display["collateral_condition"] = (
                "Tas\u0131nmaz uzerinde banka lehine birinci derece ipotek"
            )
            _display["currency"] = "TL"

        elif product == "G\u00f6nl\u00fcne G\u00f6re Konut Finansman\u0131":
            out["maximum_maturity_months"] = None
            out["maximum_financing_ratio"] = None
            out["profit_share_rate"] = None
            out["profit_share_rate_text"] = (
                "S\u0131f\u0131r veya daha uygun kar oran\u0131 imkani; "
                "nihai oran guncel piyasa kosullarina gore degisir"
            )
            out["maturity_rules_text"] = (
                "Vade guncel piyasa kosullarina gore degisir"
            )
            _display["pricing_condition"] = (
                "Finansman orani ve vadesi guncel piyasa "
                "kosullarina gore degiskenlik gosterebilir."
            )

        elif product == "\u00c7evreci Konut Finansman\u0131":
            out["profit_share_rate"] = None
            out["profit_share_rate_text"] = (
                "Mevcut konut finansman\u0131 fiyatlar\u0131ndan 2 puan indirim"
            )
            _display["eligibility_condition"] = (
                "Enerji Kimlik Belgesi bulunan A veya B enerji "
                "performans sinifindaki konutlar"
            )
            _display["pricing_advantage"] = (
                "Mevcut fiyatlardan 2 puan kar payi indirimi"
            )

        elif product == "Birlikte Konut Finansman\u0131":
            _display["joint_financing_structure"] = (
                "En az 2, en fazla 5 ortak; her musteri icin "
                "tapu hissesi oraninda ayri finansman"
            )
            _display["comparison_note"] = (
                "Urun bolumunde ayri sabit azami vade veya "
                "finansman orani yayimlanmamistir."
            )

        out["finance_rules_json"] = json.dumps(
            rules,
            ensure_ascii=False,
            sort_keys=True,
        )

    if key in VERIFIED_FEES:
        rules["fee_rules"] = deepcopy(
            VERIFIED_FEES[key]
        )

    if key in VERIFIED_OFFERS:
        verified_labels = {
            item["rule_label"]
            for item in VERIFIED_OFFERS[key]
        }
        rules["offer_rules"] = [
            item
            for item in rules["offer_rules"]
            if str(item.get("rule_label") or "")
            not in verified_labels
        ]
        rules["offer_rules"].extend(
            deepcopy(VERIFIED_OFFERS[key])
        )

    if key == ("Albaraka Türk", "Konut Finansmanı"):
        out["maximum_maturity_months"] = 120
        first, additional = canonical_housing_text(
            standard=True,
            additional=True,
        )
        out["housing_first_home_rules_text"] = first
        out["housing_additional_home_rules_text"] = additional
        out["housing_finance_rules_json"] = canonical_housing_json(
            standard=True,
            additional=True,
        )
        # Resmî maliyet/ödeme örnekleri güncel ürün kâr payı değildir.
        # Bu nedenle fiyatlama tablosuna kesinlikle eklenmez. Eski/stale
        # kayıtlarda örnek satır varsa da burada temizlenir.
        rules["pricing_tiers"] = authoritative_pricing_rows(
            rules["pricing_tiers"]
        )
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = "Güncel oran hesaplama aracında belirlenir"

    elif key == ("Dünya Katılım", "Konut Finansmanı"):
        # Güncel ürün sayfasında sayısal azami vade güvenilir şekilde
        # yayımlanmadığı için None korunur.
        out["maximum_maturity_months"] = None
        first, additional = canonical_housing_text(
            standard=True,
            additional=True,
        )
        out["housing_first_home_rules_text"] = first
        out["housing_additional_home_rules_text"] = additional
        out["housing_finance_rules_json"] = canonical_housing_json(
            standard=True,
            additional=True,
        )

    elif key == ("Kuveyt Türk", "Konut Finansmanı"):
        out["maximum_maturity_months"] = 120
        first, additional = canonical_housing_text(
            standard=False,
            additional=True,
        )
        out["housing_first_home_rules_text"] = first
        out["housing_additional_home_rules_text"] = additional
        out["housing_finance_rules_json"] = canonical_housing_json(
            standard=False,
            additional=True,
        )

    elif key == ("Kuveyt Türk", "İlk Evim Konut Finansmanı"):
        out["maximum_maturity_months"] = 120
        first, additional = canonical_housing_text(
            standard=True,
            additional=False,
        )
        out["housing_first_home_rules_text"] = first
        out["housing_additional_home_rules_text"] = additional
        out["housing_finance_rules_json"] = canonical_housing_json(
            standard=True,
            additional=False,
        )

    elif key == ("Kuveyt Türk", "Yeşil Konut Finansmanı"):
        out["maximum_maturity_months"] = 120
        out["maximum_financing_ratio"] = None
        out["housing_first_home_rules_text"] = None
        out["housing_additional_home_rules_text"] = None
        out["housing_finance_rules_json"] = None
        out["financing_ratio_rules_text"] = (
            "Finansman tutarı ekspertiz değeri, konutun sıfır/2. el durumu, "
            "enerji sınıfı ve mevcut konut sahipliğine göre değişir; mevcut "
            "konut varsa kullanılabilir finansman tutarı %75 azalır."
        )

    elif key == ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"):
        # Resmî sayfada özel şartlı bir KONUT finansmanı türü olduğu açık.
        out["maximum_financing_ratio"] = 50.0
        out["financing_ratio_rules_text"] = (
            "Ekspertiz değerinin %50'si tutarında finansman kullanılabilir."
        )
        out["housing_first_home_rules_text"] = None
        out["housing_additional_home_rules_text"] = None
        out["housing_finance_rules_json"] = None

    elif key == ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"):
        out["maximum_maturity_months"] = 120
        first, additional = canonical_housing_text(
            standard=True,
            additional=True,
        )
        out["housing_first_home_rules_text"] = first
        out["housing_additional_home_rules_text"] = additional
        out["housing_finance_rules_json"] = canonical_housing_json(
            standard=True,
            additional=True,
        )

    out["finance_rules_json"] = json.dumps(
        rules,
        ensure_ascii=False,
        sort_keys=True,
    )
    return out
