from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from src.finance_evidence import annotate_pricing_rows


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("ı", "i")).strip()


def _same(value: object, expected: str) -> bool:
    return _fold(value) == _fold(expected)


def _contains(value: object, token: str) -> bool:
    return _fold(token) in _fold(value)


def _load_rules(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")




ZIRAAT_PRODUCT_PATH_MAP: dict[str, tuple[str, str, str]] = {
    # Bireysel — konut/gayrimenkul
    "/konut-finansmani": ("Konut Finansmanı", "konut_finansmani", "Konut Finansmanı"),
    "/kentsel-donusum-finansmani": ("Kentsel Dönüşüm Finansmanı", "konut_finansmani", "Konut Finansmanı"),
    "/bireysel-arsa-finansmani": ("Bireysel Arsa Finansmanı", "arsa_finansmani", "Arsa Finansmanı"),
    "/bireysel-is-yeri-finansmani": ("Bireysel İş Yeri Finansmanı", "isyeri_finansmani", "İş Yeri Finansmanı"),
    # Bireysel — taşıt
    "/tasit-finansmani/tasit-finansmani": ("Taşıt Finansmanı", "arac_finansmani", "Araç Finansmanı"),
    "/togg-finansmani": ("TOGG Finansmanı", "arac_finansmani", "Araç Finansmanı"),
    # Bireysel — ihtiyaç
    "/egitim-finansmani": ("Eğitim Finansmanı", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/dogalgaz-donusum-finansmani": ("Doğalgaz Dönüşüm Finansmanı", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/hac-ve-umre-finansmani": ("Hac ve Umre Finansmanı", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/ipotekli-bireysel-finansman": ("İpotekli Bireysel Finansman", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/yasa-kapsaminda-ipotekli-bireysel-finansman": ("Yasa Kapsamında İpotekli Bireysel Finansman", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/dayanikli-tuketim-finansmani": ("Dayanıklı Tüketim Finansmanı", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/kolay-fon-finansmani": ("Kolay Fon Finansmanı", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    "/aninda-finansman": ("Anında Finansman", "ihtiyac_finansmani", "İhtiyaç Finansmanı"),
    # Bireysel — sürdürülebilir
    "/bireysel-enerji-verimliligi-finansmani": ("Bireysel Enerji Verimliliği Finansmanı", "surdurulebilir_finansman", "Sürdürülebilir Finansman"),
    "/enerji-verimliligi-yonetim-finansmani": ("Enerji Verimliliği Yönetim Finansmanı", "surdurulebilir_finansman", "Sürdürülebilir Finansman"),
    "/yesil-ev-konut-finansmani": ("Yeşil Ev Konut Finansmanı", "konut_finansmani", "Konut Finansmanı"),
    "/yesil-tasit-finansmani": ("Yeşil Taşıt Finansmanı", "arac_finansmani", "Araç Finansmanı"),
    # Ticari — nakdi
    "/kurumsal-finansman": ("Kurumsal Finansman", "ticari_finansman", "Ticari Finansman"),
    "/mobil-finansman": ("Mobil Finansman", "ticari_finansman", "Ticari Finansman"),
    "/taksitli-ticari-finansman": ("Taksitli Ticari Finansman", "ticari_finansman", "Ticari Finansman"),
    "/doviz-finansmani": ("Döviz Finansmanı", "ticari_finansman", "Ticari Finansman"),
    # Ticari — gayri nakdi
    "/teminat-mektuplari": ("Teminat Mektupları", "gayri_nakdi_finansman", "Gayri Nakdi Finansman"),
    "/referans-mektuplari": ("Referans Mektupları", "gayri_nakdi_finansman", "Gayri Nakdi Finansman"),
    "/kabul-aval-finansmani": ("Kabul/Aval Finansmanı", "gayri_nakdi_finansman", "Gayri Nakdi Finansman"),
    "/akreditif": ("Akreditif", "gayri_nakdi_finansman", "Gayri Nakdi Finansman"),
    # Ticari — finansman iş birlikleri
    "/kfk-teminatli-finansmanlar": ("KFK Teminatlı Finansmanlar", "ticari_finansman", "Ticari Finansman"),
    "/kosgeb-destekli-finansmanlar": ("KOSGEB Destekli Finansmanlar", "ticari_finansman", "Ticari Finansman"),
    "/eximbank-destekli-finansmanlar": ("Eximbank Destekli Finansmanlar", "ticari_finansman", "Ticari Finansman"),
    "/yatirim-tesvik-belgesi-kapsaminda-kar-payi-destegi": ("Yatırım Teşvik Belgesi Kapsamında Kâr Payı Desteği", "ticari_finansman", "Ticari Finansman"),
    # Ticari — sürdürülebilir
    "/atik-su-aritma-ve-geri-kazanimi-yatirim-ve-isletme-finansmani": ("Atık Su Arıtma ve Geri Kazanımı Yatırım ve İşletme Finansmanı", "ticari_finansman", "Ticari Finansman"),
    "/enerji-verimliligi-yatirim-isletme-finansmanlari": ("Enerji Verimliliği Yatırım ve İşletme Finansmanları", "ticari_finansman", "Ticari Finansman"),
    "/ges-cati-ges-ges-yatirim-ve-isletme-finansmani": ("GES / Çatı GES / GES Yatırım ve İşletme Finansmanı", "ticari_finansman", "Ticari Finansman"),
    "/yenilenebilir-enerji-kapsamindaki-yatirim-ve-isletme-finansmanlari": ("Yenilenebilir Enerji Kapsamındaki Yatırım ve İşletme Finansmanları", "ticari_finansman", "Ticari Finansman"),
    # Ticari — dış ticaret
    "/ithalat-finansmani": ("İthalat Finansmanı", "ticari_finansman", "Ticari Finansman"),
    "/ihracat-finansmani": ("İhracat Finansmanı", "ticari_finansman", "Ticari Finansman"),
    "/vadeli-ihracat-finansmani": ("Vadeli İhracat Finansmanı", "ticari_finansman", "Ticari Finansman"),
    "/ihracata-hazirlik-destek-finansman": ("İhracata Hazırlık Destek Finansmanı", "ticari_finansman", "Ticari Finansman"),
    # Leasing
    "/finansal-kiralama-leasing/finansal-kiralama-leasing": ("Finansal Kiralama (Leasing)", "leasing", "Leasing"),
    "/eximbank-finansal-kiralama-programi": ("EXIMBANK Finansal Kiralama Programı", "leasing", "Leasing"),
    # Tarım
    "/bitkiseluretim": ("Bitkisel Üretim Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/hayvansal-uretim-finansmani": ("Hayvansal Üretim Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/su-urunleri-finansmani": ("Su Ürünleri Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/basinclisulama": ("Basınçlı Sulama Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/yenilenebilir-enerji-yatirimlari-finansmani": ("Yenilenebilir Enerji Yatırımları Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/tarimsal-urunlerin-islenmesi-finansmani": ("Tarımsal Ürünlerin İşlenmesi Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/arazi-alimi-finansmani": ("Arazi Alımı Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/tarimsal-mekanizasyon-finansmani": ("Tarımsal Mekanizasyon Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/kucuk-ekipman-finansmani": ("Küçük Ekipman Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/tarim-makineleri-parki-finansmani": ("Tarım Makineleri Parkı Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/soguk-hava-deposu-finansmani": ("Soğuk Hava Deposu Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/lisansli-depoculuk-finansmani": ("Lisanslı Depoculuk Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/biyo-tarim-yatirimlari-finansmani": ("Biyo-Tarım Yatırımları Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
    "/tarimsal-ar-ge-yatirimlari-finansmani": ("Tarımsal AR-GE Yatırımları Finansmanı", "tarim_finansmani", "Tarım Finansmanı"),
}


def is_generic_ziraat_product_name(value: object) -> bool:
    folded = _fold(value)
    return folded in {
        "ziraat katilim",
        "ziraat katilim bankasi",
        "ziraat katilim bankasi a.s.",
        "ziraat katilim bankasi as",
    }


def canonicalize_ziraat_product_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if not _same(out.get("bank_name"), "Ziraat Katılım"):
        return out

    source_url = str(out.get("url") or out.get("source_page") or "")
    folded_url = _fold(source_url).replace(" ", "-")
    # URL encoding farklarını karşılaştırma öncesinde normalize et.
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(source_url).path).casefold().replace("ı", "i")

    # En uzun suffix önce: ör. ana taşıt sayfası ile ürün detail yolu karışmasın.
    for suffix, (name, family_key, family_label) in sorted(
        ZIRAAT_PRODUCT_PATH_MAP.items(), key=lambda item: len(item[0]), reverse=True
    ):
        normalized_suffix = unquote(suffix).casefold().replace("ı", "i")
        if path.endswith(normalized_suffix) or normalized_suffix in path:
            out["product_name"] = name
            out["product_family_key"] = family_key
            out["product_family"] = family_label
            return out

    return out


def apply_finance_data_quality_overrides(row: Mapping[str, Any]) -> dict[str, Any]:
    """Kaynakta doğrulanmış ürün-özel veri kalitesi düzeltmeleri.

    Bu katman yeni finansal değer tahmin etmez. Yalnız daha önce resmî ürün
    sayfalarından doğrulanmış ürün-özel kuralları canonical forma getirir ve
    her fiyatlama satırını evidence metadata'sıyla etiketler.
    """

    out = dict(row)
    out = canonicalize_ziraat_product_identity(out)
    bank = str(out.get("bank_name") or "")
    product = str(out.get("product_name") or "")
    # Doğrudan ürün URL'si varsa katalog/source_page yerine onu esas al.
    # Bazı keşif kayıtlarında source_page ana katalog sayfasını gösterirken
    # url alanı gerçek ürün sayfasını taşır. Ürün-özel guardrail'ler bu
    # nedenle önce final ürün URL'sine bakmalıdır.
    source_url = str(out.get("url") or out.get("source_page") or "")
    rules = _load_rules(out.get("finance_rules_json"))

    # Fiyatlama metadata'sı proje genelinde zorunlu hale gelir.
    rules["pricing_tiers"] = annotate_pricing_rows(
        rules.get("pricing_tiers", []),
        bank_name=bank,
        product_name=product,
        source_url=source_url,
    )

    display_metadata = rules.get("display_metadata")
    if not isinstance(display_metadata, dict):
        display_metadata = {}


    # ------------------------------------------------------------
    # Kalan BDDK katılım bankaları — kaynak güvenliği guardrail'leri.
    # Bu kurallar resmi sayfada bulunmayan bir finansal değer üretmez;
    # yalnız yanlış bağlamdan sızabilecek örnek/default değerleri bastırır.
    # ------------------------------------------------------------
    if _same(bank, "Adil Katılım"):
        # Adil Katılım'ın kamuya açık sayfası bireysel ve ticari finansmanı
        # genel olarak tanımlar; sayısal limit/vade/oran yayımlamaz. Sayfa
        # footer'ındaki %99,8 hizmet sürekliliği gibi ilgisiz sayılar asla
        # finansman metriğine dönüşemez.
        for key in (
            "minimum_financing_amount", "maximum_financing_amount",
            "minimum_maturity_months", "maximum_maturity_months",
            "profit_share_rate", "maximum_financing_ratio",
            "maturity_reference_upper_amount", "shopping_general_limit_amount",
            "shopping_general_max_maturity_months", "shopping_tablet_max_maturity_months",
            "shopping_computer_max_maturity_months",
        ):
            out[key] = None
        out["profit_share_rate_text"] = "Resmî genel tanıtım sayfasında sayısal güncel oran yayımlanmamış"
        out["maturity_rules_text"] = None
        out["financing_ratio_rules_text"] = None
        out["housing_first_home_rules_text"] = None
        out["housing_additional_home_rules_text"] = None
        out["housing_finance_rules_json"] = None
        out["vehicle_finance_rules_text"] = None
        out["vehicle_age_rules_text"] = None
        out["shopping_finance_rules_text"] = None
        rules["amount_maturity_rules"] = []
        rules["pricing_tiers"] = []
        rules["fee_rules"] = []
        rules["offer_rules"] = []
        rules["category_rules"] = []
        display_metadata["source_precision_note"] = "Yalnız resmî genel ürün tanımı gösterilir; sayısal koşul yayımlanmadığı için tahmin yapılmaz."

    # TOM Bank sayfa <title> değerleri zaman zaman encoding/suffix nedeniyle
    # "AlÄ±Å... | TOM Bank" biçiminde gelebiliyor. Ürün kimliğini görünür
    # başlıktan tahmin etmek yerine resmî final ürün URL'siyle sabitle.
    # Böylece hem kullanıcıya bozuk ürün adı gitmez hem de ürün-özel
    # doğruluk kuralları katalog source_page yüzünden atlanmaz.
    if _same(bank, "T.O.M. Katılım"):
        tom_name_by_path = {
            "/veresiye.html": "Veresiye Alışveriş Kredisi",
            "/taksitle.html": "Taksitli Alışveriş Kredisi",
            "/magazadan-alisveris-kredisi.html": "Mağazadan Alışveriş Kredisi",
        }
        for tom_path, canonical_name in tom_name_by_path.items():
            if _contains(source_url, tom_path):
                product = canonical_name
                out["product_name"] = canonical_name
                # Kullanıcıya gösterilen Ürün Kaynağı doğrudan ürün sayfası olsun.
                out["source_page"] = source_url
                break

    if _same(bank, "T.O.M. Katılım") and (_same(product, "Veresiye Alışveriş Kredisi") or _contains(source_url, "/veresiye.html")):
        # %3,99 bir sabit genel oran değil, resmi sayfada '...dan başlayan'
        # alt sınır niteliğindedir. Örnek 1.000 TL/60 gün senaryosu da genel
        # fiyatlama olarak kullanılamaz.
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = "Aylık %3,99'dan başlayan · koşullara göre"
        rules["pricing_tiers"] = []
        display_metadata["pricing_value_type"] = "minimum"
        display_metadata["pricing_condition_note"] = "Resmî sayfa aylık %3,99'dan başlayan oran ifadesini kullanır; örnek senaryo genel oran değildir."

    if _same(bank, "T.O.M. Katılım") and (_same(product, "Mağazadan Alışveriş Kredisi") or _contains(source_url, "/magazadan-alisveris-kredisi.html")):
        # Resmî ürün sayfasında doğrudan yayımlanan ürün-özel sınırlar.
        out["minimum_financing_amount"] = 1000.0
        out["maximum_financing_amount"] = 200000.0
        out["maximum_maturity_months"] = 36
        out["maturity_rules_text"] = "36 aya kadar"
        display_metadata["product_specific_limit_text"] = "1.000 TL – 200.000 TL"
        display_metadata["product_specific_maturity_text"] = "36 aya kadar"
        display_metadata["verified_channel"] = "Anlaşmalı mağaza · Hadi uygulaması / QR"

    if _same(bank, "Ziraat Katılım"):
        # Ziraat Katılım sayfalarında ortak hesaplama aracında varsayılan
        # %0,99 yer alıyor ve banka bunun bilgi amaçlı, bağlayıcı fiyat
        # olmadığını açıkça belirtiyor. Bu default değer headline olamaz.
        try:
            numeric_rate = float(out.get("profit_share_rate")) if out.get("profit_share_rate") is not None else None
        except (TypeError, ValueError):
            numeric_rate = None
        if numeric_rate is not None and abs(numeric_rate - 0.99) < 1e-9:
            out["profit_share_rate"] = None
            out["profit_share_rate_text"] = "Hesaplama aracı bilgi amaçlı; bağlayıcı güncel oran yayımlanmamış"
        kept = []
        for tier in rules.get("pricing_tiers", []) or []:
            try:
                rate = float(tier.get("profit_share_rate"))
            except (TypeError, ValueError, AttributeError):
                rate = None
            if rate is not None and abs(rate - 0.99) < 1e-9:
                continue
            kept.append(tier)
        rules["pricing_tiers"] = kept

        # Tarımsal ürün sayfalarındaki %25/%50/%65/%75/%100 ifadeleri
        # "devlet destekli (sübvansiyonlu)" destek oranlarıdır; müşterinin
        # güncel kâr payı/fiyatlaması değildir. Bu oranları headline pricing
        # olarak kullanmak kesinlikle yasaktır.
        clean_text = str(out.get("clean_text") or "")
        if (
            str(out.get("product_family_key") or "") == "tarim_finansmani"
            or "/tarim/" in source_url.casefold()
        ) and ("devlet destekli" in _fold(clean_text) or "subvansiyon" in _fold(clean_text)):
            out["profit_share_rate"] = None
            out["profit_share_rate_text"] = None
            rules["pricing_tiers"] = []
            match = re.search(r"%(\d{1,3})(?:['\u2019]?[ea]\s+varan)?\s+devlet destekli", clean_text, flags=re.IGNORECASE)
            if match:
                display_metadata["state_support_note"] = f"Devlet destekli (s\u00fcbvansiyonlu) destek oran\u0131: %{match.group(1)}'e kadar; k\u00e2r pay\u0131 oran\u0131 de\u011fildir."
            else:
                display_metadata["state_support_note"] = "Devlet destekli (s\u00fcbvansiyonlu) finansman imk\u00e2n\u0131 belirtilmi\u015ftir; g\u00fcncel k\u00e2r pay\u0131 oran\u0131 resm\u00ee kaynakta ayr\u0131ca do\u011frulanmam\u0131\u015ft\u0131r."

    if _same(bank, "Vakıf Katılım") and _same(product, "Konut Finansmanı"):
        # Resmî sayfanın ana ürün açıklaması 120 ay ve %90'a kadar finansmanı
        # doğruluyor. Aynı sayfadaki 2. ev tablosunda %150 görünen bir hücre
        # vardır. Amaçlanan değer tahmin edilmez; şüpheli tablo BANSA ana
        # karşılaştırmasında kullanılmaz.
        out["maximum_maturity_months"] = 120
        out["maximum_financing_ratio"] = 90.0
        out["financing_ratio_rules_text"] = "Ekspertiz değeri, enerji sınıfı ve konut sahipliği koşullarına göre; azami %90"
        out["housing_first_home_rules_text"] = None
        out["housing_additional_home_rules_text"] = None
        out["housing_finance_rules_json"] = None
        display_metadata["source_anomaly_warning"] = "Resmî 2. ev tablosunda %100 üzeri (%150) görünen hücre karşılaştırmada kullanılmaz; amaçlanan değer tahmin edilmez."

    if _same(bank, "Türkiye Emlak Katılım") and _same(product, "Konut Finansmanı"):
        # Ana açıklama ekspertiz değerinin %80'ine kadar finansmanı açıkça
        # yayımlar. Sayfanın aşağısındaki kredi-değer tablosunda 0% ve tekrar
        # eden tutar bandı gibi tutarsız hücreler bulunduğundan o tabloyu
        # otomatik karar verisi olarak kullanmıyoruz.
        out["maximum_financing_ratio"] = 80.0
        out["financing_ratio_rules_text"] = "Ekspertiz değerinin %80'ine kadar (ana ürün açıklaması)"
        out["housing_first_home_rules_text"] = None
        out["housing_additional_home_rules_text"] = None
        out["housing_finance_rules_json"] = None
        display_metadata["source_anomaly_warning"] = "Resmî sayfadaki ayrıntılı kredi-değer tablosunda tutarsız hücreler bulunduğu için BANSA yalnız ana ürün açıklamasındaki doğrulanmış %80 üst sınırı kullanır."

    if _same(bank, "Türkiye Emlak Katılım") and _contains(source_url, "/tr/bireysel/finansmanlar/ihtiyac-finansmani"):
        # Alt ihtiyaç ürünleri ortak sayfanın sonunda yer alan 30.000 TL /
        # 12 ay / %1,69 'Örnek İhtiyaç Finansmanı Tablosu'ndan fiyatlama
        # devralamaz. Alt bölüm kendisi sayısal güncel fiyat yayımlamıyorsa
        # oran boş kalır.
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = "Resmî ürün bölümünde sabit güncel oran yayımlanmamış"
        rules["pricing_tiers"] = []
        display_metadata["pricing_example_excluded"] = "Ortak sayfanın örnek ihtiyaç tablosu ürün-özel güncel fiyatlama değildir."

    # ------------------------------------------------------------
    # Albaraka Türk — Dijital Araç: araç değer bantları tek kanonik
    # kaynaktan gelir. Tutarları binlik ayırıcı hatasıyla 1.200 / 2.000
    # olarak küçültme ve seçili varsayılan değerden %50 headline üretme.
    # ------------------------------------------------------------
    if _same(bank, "Albaraka Türk") and _same(product, "Dijital Araç Finansmanı"):
        canonical = [
            (None, 400000.0, 48, 70.0),
            (400000.0, 800000.0, 36, 50.0),
            (800000.0, 1200000.0, 24, 30.0),
            (1200000.0, 2000000.0, 12, 20.0),
        ]
        rules["amount_maturity_rules"] = [
            {
                "min_amount": lo, "max_amount": hi, "min_inclusive": False,
                "max_inclusive": True, "max_maturity_months": months,
                "source_text": ((f"Değer ≤ {_money(hi)} TL" if lo is None else f"{_money(lo)} TL < Değer ≤ {_money(hi)} TL") + f" → Azami %{ratio:g} · {months} ay"),
            }
            for lo, hi, months, ratio in canonical
        ]
        out["maximum_financing_ratio"] = 70.0
        out["maximum_maturity_months"] = 48
        out["maturity_rules_text"] = "≤ 400.000 TL → 48 ay | 400.001–800.000 TL → 36 ay | 800.001–1.200.000 TL → 24 ay | 1.200.001–2.000.000 TL → 12 ay | > 2.000.000 TL → kullandırım yok"
        out["vehicle_finance_rules_text"] = "≤ 400.000 TL: %70 / 48 ay · 400.001–800.000 TL: %50 / 36 ay · 800.001–1.200.000 TL: %30 / 24 ay · 1.200.001–2.000.000 TL: %20 / 12 ay · > 2.000.000 TL: Kullandırım yok"

    # Hac/Umre sayfasındaki 125/250 bin TL değerleri ürün limiti değil,
    # yalnız azami vade bantlarıdır.
    if _same(bank, "Albaraka Türk") and _same(product, "Hac ve Umre Finansmanı"):
        out["minimum_financing_amount"] = None
        out["maximum_financing_amount"] = None
        out["maximum_maturity_months"] = 36
        rules["amount_maturity_rules"] = [
            {"min_amount": None, "max_amount": 125000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 36, "source_text": "125.000 TL'ye kadar maksimum 36 ay"},
            {"min_amount": 125000.0, "max_amount": 250000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 24, "source_text": "125.001-250.000 TL maksimum 24 ay"},
            {"min_amount": 250000.0, "max_amount": None, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 12, "source_text": "250.000 TL üzeri maksimum 12 ay"},
        ]
        out["maturity_rules_text"] = "≤ 125.000 TL → 36 ay | 125.001–250.000 TL → 24 ay | > 250.000 TL → 12 ay"
        display_metadata["product_limit_note"] = "Hac/Umre bedelinin tamamı finanse edilebilir; resmî sayfada ayrıca sayısal azami ürün limiti yayımlanmamıştır."

        # HAC_UMRE_FINANCING_RATIO_FINAL_V1
        # Resmi urun ifadesindeki "hac ve umre bedelinin tamami"
        # normalize edilerek azami %100 finansman orani olarak tutulur.
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Hac/Umre bedelinin tamamına kadar"
        )
        display_metadata["financing_ratio_note"] = (
            "Hac/Umre bedelinin tamamı finanse edilebilir."
        )

    # Jet ürün limiti 1.000–60.000 TL olduğundan genel ihtiyaç vade
    # bantlarının 60.000 TL üzerindeki kısmı bu üründe gösterilmez.

    # ------------------------------------------------------------
    # TF_DIGITAL_TICARI_COMPLETENESS_FINAL_V1
    # Turkiye Finans'in urun-ozel resmi sayfasinda:
    # "1 milyon TL'ye varan finansman tutarina 12 ay vade"
    # ifadesi acikca yayimlanir.
    # ------------------------------------------------------------
    if (
        _same(bank, "Türkiye Finans")
        and _same(
            product,
            "Dijital Taksitli Ticari Finansman Desteği",
        )
        and _contains(
            source_url,
            "dijital-taksitli-ticari-finansman-destegi.aspx",
        )
    ):
        out["maximum_financing_amount"] = 1_000_000.0
        out["maximum_maturity_months"] = 12
        out["maturity_rules_text"] = "12 ay"

        display_metadata["product_specific_limit_text"] = (
            "1.000.000 TL'ye kadar"
        )
        display_metadata["product_specific_maturity_text"] = (
            "12 ay"
        )

    if _same(bank, "Albaraka Türk") and _same(product, "Jet Finansman"):
        out["minimum_financing_amount"] = 1000.0
        out["maximum_financing_amount"] = 60000.0
        out["maximum_maturity_months"] = 36
        rules["amount_maturity_rules"] = [
            {"min_amount": 1000.0, "max_amount": 50000.0, "min_inclusive": True, "max_inclusive": True, "max_maturity_months": 36, "source_text": "1.000-50.000 TL arası finansmanlarda 36 ay"},
            {"min_amount": 50000.0, "max_amount": 60000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 24, "source_text": "Ürün üst limiti 60.000 TL ile kesiştirilmiş 50.001-60.000 TL bandı; resmî genel bant 50.001-100.000 TL için 24 ay"},
        ]
        out["maturity_rules_text"] = "1.000–50.000 TL → 36 ay | 50.001–60.000 TL → 24 ay"

    # Türkiye Finans normal ihtiyaç ürününde aynı 24 ay bandının iki farklı
    # biçimde çoğalmasını engelle; fiyatlama koşullu tablo olarak kalır.
    if _same(bank, "Türkiye Finans") and _contains(product, "İhtiyaç Finansmanı") and not _contains(product, "Dijital"):
        rules["amount_maturity_rules"] = [
            {"min_amount": None, "max_amount": 125000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 36, "source_text": "125.000 TL'ye kadar maksimum 36 ay"},
            {"min_amount": 125000.0, "max_amount": 250000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 24, "source_text": "125.001-250.000 TL maksimum 24 ay"},
            {"min_amount": 250000.0, "max_amount": None, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 12, "source_text": "250.000 TL üzeri maksimum 12 ay"},
        ]
        out["maximum_maturity_months"] = 36
        out["maturity_rules_text"] = "≤ 125.000 TL → 36 ay | 125.001–250.000 TL → 24 ay | > 250.000 TL → 12 ay"

    # Trendyol'un ürün-özel limiti/vadesi genel ihtiyaç vade bandıyla
    # karışmaz.
    if _same(bank, "Türkiye Finans") and _contains(product, "Trendyol Alışveriş Finansmanı"):
        out["minimum_financing_amount"] = 1000.0
        out["maximum_financing_amount"] = 70000.0
        out["maximum_maturity_months"] = 36
        rules["amount_maturity_rules"] = []
        out["maturity_rules_text"] = "36 aya kadar"
        display_metadata["product_specific_limit_text"] = "1.000 TL – 70.000 TL"
        display_metadata["product_specific_maturity_text"] = "36 aya kadar"

    # LC Waikiki koşulu ana karşılaştırmada limit/vade alanlarına taşınır.
    if _same(bank, "Kuveyt Türk") and _contains(product, "LC Waikiki Alışveriş Finansmanı"):
        out["maximum_financing_amount"] = 5000.0
        out["maximum_maturity_months"] = 3
        out["maturity_rules_text"] = "3 ay"
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = None
        out["interest_free"] = True
        out["interest_free_text"] = "Vade farksız"
        display_metadata["product_specific_limit_text"] = "5.000 TL'ye kadar"
        display_metadata["product_specific_maturity_text"] = "3 ay"
        display_metadata["verified_channel"] = "LC Waikiki uygulaması / web sitesi"

    # Kuveyt Türk genel tarım ürünü ELÜS ürünü değildir. ELÜS ayrı ürün
    # sayfasında tutulur; genel üründe esnek ödeme ve TL/USD/EUR vardır.
    if _same(bank, "Kuveyt Türk") and _same(product, "Tarım ve Hayvancılık Finansmanı"):
        display_metadata["verified_usage_purpose"] = "Tarım ve hayvancılık faaliyetlerinde mal/hizmet, işletme ve yatırım finansmanı"
        display_metadata["verified_repayment_structure"] = "Nakit akışına / hasat dönemine uygun esnek ödeme"
        display_metadata["verified_currency"] = "TL / USD / EUR"
        display_metadata["remove_security_type"] = True

    # ------------------------------------------------------------
    # Türkiye Finans — Dijital İhtiyaç: parser'ın >250.000'i >0'a
    # dönüştürmesi ve 250.000'e kadar geniş kural üretmesi engellenir.
    # ------------------------------------------------------------
    if _same(bank, "Türkiye Finans") and _contains(product, "Dijital İhtiyaç Finansmanı"):
        rules["amount_maturity_rules"] = [
            {
                "min_amount": None,
                "max_amount": 125000.0,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_maturity_months": 36,
                "source_text": "125.000 TL'ye kadar olması durumunda maksimum vade 36 ay",
            },
            {
                "min_amount": 125000.0,
                "max_amount": 250000.0,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_maturity_months": 24,
                "source_text": "125.000 TL üzeri - 250.000 TL'ye kadar olması durumunda maksimum vade 24 ay",
            },
            {
                "min_amount": 250000.0,
                "max_amount": None,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_maturity_months": 12,
                "source_text": "250.000 TL'den fazla olması durumunda maksimum vade 12 ay",
            },
        ]
        out["maturity_rules_text"] = (
            "≤ 125.000 TL → 36 ay | 125.000 TL < Tutar ≤ 250.000 TL → 24 ay | "
            "Tutar > 250.000 TL → 12 ay"
        )
        out["maximum_maturity_months"] = 36

    # ------------------------------------------------------------
    # Hayat Finans — Bana Bunu Al: genel yasal ihtiyaç vade bantları ürünün
    # 50.000 TL / 18 ay gerçek ürün sınırlarının önüne geçemez.
    # ------------------------------------------------------------
    if _same(bank, "Hayat Finans") and _same(product, "Bana Bunu Al"):
        out["minimum_financing_amount"] = 500.0
        out["maximum_financing_amount"] = 50000.0
        out["maximum_maturity_months"] = 18
        out["maturity_rules_text"] = "Ürün azami vadesi 18 ay"
        # 125/250 bin TL bantları mevzuat/genel bilgi; bu ürünün gerçek limiti
        # 50 bin TL olduğundan ana ürün kuralı olarak saklanmaz.
        rules["amount_maturity_rules"] = []
        display_metadata["product_specific_limit_text"] = "500 TL – 50.000 TL"
        display_metadata["product_specific_maturity_text"] = "18 aya kadar"

    # ------------------------------------------------------------
    # Dünya Katılım — Araç: bütün değer/vade bantları detayda da tek tek
    # görünmeli ve ikinci el yaş sınırı kaybolmamalıdır.
    # ------------------------------------------------------------
    if _same(bank, "Dünya Katılım") and _same(product, "Araç Finansmanı"):
        canonical = [
            (None, 400000.0, 48, 70.0),
            (400000.0, 800000.0, 36, 50.0),
            (800000.0, 1200000.0, 24, 30.0),
            (1200000.0, 2000000.0, 12, 20.0),
        ]
        rules["amount_maturity_rules"] = [
            {
                "min_amount": lo,
                "max_amount": hi,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_maturity_months": months,
                "source_text": (
                    (f"Değer ≤ {_money(hi)} TL" if lo is None else f"{_money(lo)} TL < Değer ≤ {_money(hi)} TL")
                    + f" → Azami %{ratio:g} · {months} ay"
                ),
            }
            for lo, hi, months, ratio in canonical
        ]
        out["maturity_rules_text"] = " | ".join(
            [
                "≤ 400.000 TL → 48 ay",
                "400.000–800.000 TL → 36 ay",
                "800.000–1.200.000 TL → 24 ay",
                "1.200.000–2.000.000 TL → 12 ay",
            ]
        )
        out["vehicle_finance_rules_text"] = (
            "≤ 400.000 TL: %70 / 48 ay · 400.000–800.000 TL: %50 / 36 ay · "
            "800.000–1.200.000 TL: %30 / 24 ay · 1.200.000–2.000.000 TL: %20 / 12 ay · "
            "> 2.000.000 TL: kullandırım yok"
        )
        out["vehicle_age_rules_text"] = "0 km ve 2. el · ikinci elde 12 yaşa kadar"
        out["maximum_financing_ratio"] = 70.0
        out["maximum_maturity_months"] = 48
        display_metadata["vehicle_value_rules"] = [
            {"max_value": hi, "min_value": lo, "max_maturity_months": months, "max_financing_ratio": ratio}
            for lo, hi, months, ratio in canonical
        ]
        display_metadata["vehicle_blocked_above"] = 2000000.0

    # ------------------------------------------------------------
    # Standart araç değer bandı yayımlayan diğer ürünlerde de yüzde/vade
    # ilişkisinin varsayılan araç değerinden veya örnek fiyatlamadan
    # türetilmesini engelle.
    # ------------------------------------------------------------
    common_vehicle_products = (
        (_same(bank, "Albaraka Türk") and _same(product, "Taşıt Finansmanı")),
        (_same(bank, "Kuveyt Türk") and product in {"Araç Finansmanı", "Dijital Araç Finansmanı", "Sürdürülebilir Araç Finansmanı"}),
        (_same(bank, "Türkiye Finans") and product in {"Dijital Taşıt Finansmanı", "Taşıt Finansmanı (Taşıt Kredisi)*"}),
    )
    if any(common_vehicle_products):
        canonical_vehicle_text = (
            "≤ 400.000 TL: %70 / 48 ay · 400.001–800.000 TL: %50 / 36 ay · "
            "800.001–1.200.000 TL: %30 / 24 ay · 1.200.001–2.000.000 TL: %20 / 12 ay · "
            "> 2.000.000 TL: kullandırım yok"
        )
        out["vehicle_finance_rules_text"] = canonical_vehicle_text
        out["maximum_financing_ratio"] = 70.0
        out["maximum_maturity_months"] = 48
        canonical = [
            (None, 400000.0, 48, 70.0),
            (400000.0, 800000.0, 36, 50.0),
            (800000.0, 1200000.0, 24, 30.0),
            (1200000.0, 2000000.0, 12, 20.0),
        ]
        rules["amount_maturity_rules"] = [
            {
                "min_amount": lo, "max_amount": hi, "min_inclusive": False,
                "max_inclusive": True, "max_maturity_months": months,
                "source_text": ((f"Değer ≤ {_money(hi)} TL" if lo is None else f"{_money(lo)} TL < Değer ≤ {_money(hi)} TL") + f" → Azami %{ratio:g} · {months} ay"),
            }
            for lo, hi, months, ratio in canonical
        ]

    # ------------------------------------------------------------
    # Albaraka 2B: metin bir fiyat değildir. Ana hücre bunu güncel fiyatlama
    # sayfasına yönlendiren açık bir açıklama olarak göstermeli.
    # ------------------------------------------------------------
    if _same(bank, "Albaraka Türk") and _same(product, "2B Arazi Finansmanı"):
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = "Resmî fiyatlama sayfasından güncel olarak belirlenir"
        display_metadata["pricing_source_label"] = "Finansman Kâr Oranları ve Ücretleri"

    # Albaraka TOGG model/tutar/vade ilişkisi pricing tier metadata'sında
    # korunur; tek min-max oranına indirgenmemelidir.
    if _same(bank, "Albaraka Türk") and _same(product, "Togg Finansmanı"):
        display_metadata["pricing_display_mode"] = "model_amount_maturity_tiers"

    # Bireysel Çatı GES: top-level kategori oluşturmadan alt türü açıkça sakla.
    if _same(bank, "Kuveyt Türk") and _same(product, "Çatı GES Finansmanı") and _fold(out.get("scope")) == "bireysel":
        display_metadata["comparison_subtype"] = "Sürdürülebilir / Enerji"

    rules["display_metadata"] = display_metadata
    out["finance_rules_json"] = json.dumps(rules, ensure_ascii=False, sort_keys=True)
    

    # ============================================================
    # FINAL_COMPLETENESS_CANONICAL_V2
    #
    # Evidence-backed final completeness overrides.
    # Generic amount / maturity / ratio fields are populated only
    # where the official product evidence is product-specific.
    # Conditional/category values stay in their rule structures.
    # ============================================================

    # ------------------------------------------------------------
    # KUVEYT TURK - IHTIYAC KART
    # General repayment plan: 6-34 months.
    # Phone <=20k TL: max 10 installments.
    # ------------------------------------------------------------
    if (
        _same(bank, "Kuveyt T\u00fcrk")
        and _same(product, "\u0130htiya\u00e7 Kart")
    ):
        out["maximum_maturity_months"] = 34
        out["maturity_rules_text"] = (
            "Toplam harcama i\u00e7in 6\u201334 ay geri \u00f6deme"
        )
        out["shopping_general_max_maturity_months"] = 34

        out["shopping_phone_rule_text"] = (
            "\u226420.000 TL: en fazla 10 taksit"
        )

        _cr = [
            r
            for r in rules.get("category_rules", [])
            if str(r.get("category_key") or "") != "cep_telefonu"
        ]

        _cr.append(
            {
                "category_key": "cep_telefonu",
                "category_label": "Cep Telefonu",
                "condition_text": "\u2264 20.000 TL",
                "min_amount": None,
                "max_amount": 20000.0,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_installments": 10,
                "max_maturity_months": None,
                "source_text": (
                    "Cep Telefonu al\u0131\u015fveri\u015fleriniz "
                    "20.000 TL'ye kadar en fazla 10 taksit"
                ),
            }
        )

        rules["category_rules"] = _cr

        _parts = [
            "Genel geri \u00f6deme: 6\u201334 ay",
            "Cep telefonu: \u226420 bin TL: 10 taksit",
        ]

        if out.get("shopping_tablet_max_maturity_months"):
            _parts.append(
                "Tablet: "
                f"{int(out['shopping_tablet_max_maturity_months'])} ay"
            )

        if out.get("shopping_computer_max_maturity_months"):
            _parts.append(
                "Bilgisayar: "
                f"{int(out['shopping_computer_max_maturity_months'])} ay"
            )

        out["shopping_finance_rules_text"] = " \u00b7 ".join(_parts)

        display_metadata["product_specific_maturity_text"] = (
            "6\u201334 ay"
        )


    # ------------------------------------------------------------
    # KUVEYT TURK - HAC / UMRE
    # Entire Hac/Umre cost can be financed.
    # ------------------------------------------------------------
    if (
        _same(bank, "Kuveyt T\u00fcrk")
        and _same(product, "Hac-Umre Finansman\u0131")
    ):
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Hac/Umre bedelinin tamam\u0131na kadar"
        )
        display_metadata["financing_ratio_note"] = (
            "Hac veya umre bedelinin tamam\u0131 i\u00e7in "
            "finansman deste\u011fi."
        )


    # ------------------------------------------------------------
    # KUVEYT TURK - SSB SUPPORT PACKAGE
    # Leasing max 60 months; business finance max 12 months.
    # ------------------------------------------------------------
    if (
        _same(bank, "Kuveyt T\u00fcrk")
        and _same(
            product,
            "Savunma Sanayii Ba\u015fkanl\u0131\u011f\u0131 "
            "Finansman Destek Paketi",
        )
    ):
        out["maximum_maturity_months"] = 60
        out["maturity_rules_text"] = (
            "Leasing: azami 60 ay \u00b7 "
            "\u0130\u015fletme Finansman\u0131: azami 12 ay"
        )
        display_metadata["product_specific_maturity_text"] = (
            "Leasing 60 ay \u00b7 \u0130\u015fletme 12 ay"
        )


    # ------------------------------------------------------------
    # KUVEYT TURK - TEKNOSA
    # The verified tablet category rule is 6 months.
    # Fix stale top-level 36-month tablet value.
    # ------------------------------------------------------------
    if (
        _same(bank, "Kuveyt T\u00fcrk")
        and _same(product, "Teknosa Al\u0131\u015fveri\u015f Finansman\u0131")
    ):
        out["shopping_tablet_max_maturity_months"] = 6
        out["shopping_finance_rules_text"] = (
            "Genel: \u2264200 bin TL / 36 ay \u00b7 "
            "Cep telefonu: \u226420 bin TL: 12 taksit \u00b7 "
            ">20 bin TL: 3 taksit \u00b7 "
            "Tablet: 6 ay \u00b7 Bilgisayar: 12 ay"
        )


    # ------------------------------------------------------------
    # TURKIYE EMLAK KATILIM - PHONE FINANCE
    # Refurbished phone:
    # <=25k TL -> 12 months
    # >25k TL  -> 3 months
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Emlak Kat\u0131l\u0131m")
        and _same(product, "Cep Telefonu Finansman\u0131")
    ):
        out["maximum_maturity_months"] = 12
        out["maturity_rules_text"] = (
            "Yenilenmi\u015f cep telefonu: "
            "\u226425.000 TL \u2192 12 ay | "
            ">25.000 TL \u2192 3 ay"
        )

        _cr = [
            r
            for r in rules.get("category_rules", [])
            if str(r.get("category_key") or "")
            != "yenilenmis_cep_telefonu"
        ]

        _cr.extend(
            [
                {
                    "category_key": "yenilenmis_cep_telefonu",
                    "category_label": "Yenilenmi\u015f Cep Telefonu",
                    "condition_text": "\u2264 25.000 TL",
                    "min_amount": None,
                    "max_amount": 25000.0,
                    "min_inclusive": False,
                    "max_inclusive": True,
                    "max_installments": None,
                    "max_maturity_months": 12,
                    "source_text": (
                        "Fiyat\u0131 25.000 TL ve alt\u0131nda olan "
                        "yenilenmi\u015f cep telefonlar\u0131 i\u00e7in "
                        "12 ay vade"
                    ),
                },
                {
                    "category_key": "yenilenmis_cep_telefonu",
                    "category_label": "Yenilenmi\u015f Cep Telefonu",
                    "condition_text": "> 25.000 TL",
                    "min_amount": 25000.0,
                    "max_amount": None,
                    "min_inclusive": False,
                    "max_inclusive": True,
                    "max_installments": None,
                    "max_maturity_months": 3,
                    "source_text": (
                        "Fiyat\u0131 25.000 TL \u00fczerinde olan "
                        "yenilenmi\u015f cep telefonlar\u0131 i\u00e7in "
                        "3 ay vade"
                    ),
                },
            ]
        )

        rules["category_rules"] = _cr
        display_metadata["product_specific_maturity_text"] = (
            "\u226425.000 TL: 12 ay \u00b7 >25.000 TL: 3 ay"
        )


    # ------------------------------------------------------------
    # TURKIYE EMLAK KATILIM - LEASING
    # Official product statement: up to 100% financing.
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Emlak Kat\u0131l\u0131m")
        and _same(product, "Leasing")
    ):
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Sat\u0131n alma masraflar\u0131 dahil "
            "%100'e kadar finansman"
        )
        display_metadata["financing_ratio_note"] = (
            "\u0130\u015flemin sat\u0131n alma a\u015famas\u0131ndaki "
            "masraflar dahil %100 finansman imk\u00e2n\u0131."
        )


    # ------------------------------------------------------------
    # TURKIYE EMLAK KATILIM - WASTE MANAGEMENT
    # Product-specific: max 10m TL and max 24 months.
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Emlak Kat\u0131l\u0131m")
        and _same(product, "At\u0131k Y\u00f6netimi Finansman\u0131")
    ):
        out["maximum_financing_amount"] = 10_000_000.0
        out["maximum_maturity_months"] = 24
        out["maturity_rules_text"] = (
            "24 aya kadar \u00b7 "
            "3 ayda bir veya e\u015fit taksitli \u00f6deme"
        )
        display_metadata["product_specific_limit_text"] = (
            "10.000.000 TL'ye kadar"
        )
        display_metadata["product_specific_maturity_text"] = (
            "24 aya kadar"
        )


    # ------------------------------------------------------------
    # TURKIYE EMLAK KATILIM - KOSGEB EMPLOYMENT SUPPORT
    # Official table maturity: 36 months.
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Emlak Kat\u0131l\u0131m")
        and _same(
            product,
            "KOSGEB \u0130stihdam\u0131 Koruma Destek Finansman\u0131",
        )
    ):
        out["maximum_maturity_months"] = 36
        out["maturity_rules_text"] = (
            "36 ay \u00b7 5 ay anapara \u00f6demesiz d\u00f6nem"
        )
        display_metadata["product_specific_maturity_text"] = "36 ay"
        display_metadata["grace_period_note"] = (
            "5 ay anapara \u00f6demesiz d\u00f6nem"
        )


    # ------------------------------------------------------------
    # TURKIYE FINANS - HOUSING
    # Headline max is the maximum verified ratio in the
    # first-home matrix. Conditional matrices remain authoritative.
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Finans")
        and _contains(
            product,
            "Konut Finansman\u0131 (Konut Kredisi)",
        )
    ):
        out["maximum_financing_ratio"] = 90.0
        out["financing_ratio_rules_text"] = (
            "\u0130lk konut finansman matrisinde azami %90; "
            "oran ekspertiz de\u011feri, enerji s\u0131n\u0131f\u0131 "
            "ve konut sahipli\u011fine g\u00f6re de\u011fi\u015fir"
        )
        display_metadata["financing_ratio_note"] = (
            "Ana %90 de\u011feri genel sabit oran de\u011fil; "
            "do\u011frulanm\u0131\u015f ko\u015fullu konut matrisinin "
            "en y\u00fcksek oran\u0131d\u0131r."
        )


    # ------------------------------------------------------------
    # TURKIYE FINANS - ELUS
    # 24 months in the page is storage duration, NOT financing
    # maturity. Real finance ratio: up to 90% of ELUS amount.
    # ------------------------------------------------------------
    if (
        _same(bank, "T\u00fcrkiye Finans")
        and _contains(product, "Elektronik \u00dcr\u00fcn Senedi")
    ):
        out["maximum_maturity_months"] = None
        out["maturity_rules_text"] = None
        out["maximum_financing_ratio"] = 90.0
        out["financing_ratio_rules_text"] = (
            "EL\u00dcS tutar\u0131n\u0131n %90'\u0131na kadar"
        )
        display_metadata["storage_duration_note"] = (
            "24 aya kadar ifadesi finansman vadesi de\u011fil, "
            "lisansl\u0131 depoda saklama s\u00fcresidir."
        )
        display_metadata["financing_ratio_note"] = (
            "EL\u00dcS tutar\u0131n\u0131n %90'\u0131na kadar "
            "finansman."
        )


    # ------------------------------------------------------------
    # VAKIF KATILIM - LAND
    # ------------------------------------------------------------
    if (
        _same(bank, "Vak\u0131f Kat\u0131l\u0131m")
        and _same(product, "Arsa Finansman\u0131")
    ):
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Arsan\u0131n niteli\u011fine g\u00f6re ekspertiz "
            "bedelinin %100'\u00fcne kadar"
        )
        display_metadata["financing_ratio_note"] = (
            "Ekspertiz bedelinin %100'\u00fcne kadar finansman."
        )


    # ------------------------------------------------------------
    # VAKIF KATILIM - URBAN TRANSFORMATION
    # Overall max = 120 months; workplace variants max 84 months.
    # ------------------------------------------------------------
    if (
        _same(bank, "Vak\u0131f Kat\u0131l\u0131m")
        and _same(product, "Kentsel D\u00f6n\u00fc\u015f\u00fcm Finansman\u0131")
    ):
        out["maximum_maturity_months"] = 120
        out["maturity_rules_text"] = (
            "G\u00fc\u00e7lendirme / Konut: 120 aya kadar \u00b7 "
            "\u0130\u015fyeri: 84 aya kadar"
        )
        display_metadata["product_specific_maturity_text"] = (
            "Azami 120 ay"
        )


    # ------------------------------------------------------------
    # VAKIF KATILIM - FINANCIAL LEASING
    # ------------------------------------------------------------
    if (
        _same(bank, "Vak\u0131f Kat\u0131l\u0131m")
        and _same(product, "Finansal Kiralama")
    ):
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Yat\u0131r\u0131m\u0131n %100'\u00fcne kadar"
        )
        display_metadata["financing_ratio_note"] = (
            "Yat\u0131r\u0131mlar\u0131n %100'\u00fcne kadar "
            "finansman sa\u011flanabilir."
        )


    # ------------------------------------------------------------
    # VAKIF KATILIM - COMMERCIAL VEHICLE
    # ------------------------------------------------------------
    if (
        _same(bank, "Vak\u0131f Kat\u0131l\u0131m")
        and _same(product, "Ticari Ta\u015f\u0131t Finansman\u0131")
    ):
        out["maximum_financing_ratio"] = 100.0
        out["financing_ratio_rules_text"] = (
            "Fatura / kasko bedelinin %100'\u00fcne kadar"
        )
        display_metadata["financing_ratio_note"] = (
            "Ticari ta\u015f\u0131t i\u015flemlerinde fatura/kasko "
            "bedelinin %100'\u00fcne kadar finansman."
        )


    # ------------------------------------------------------------
    # VAKIF KATILIM - NEEDS / PHONE CATEGORY
    # 20k TL is NOT a generic financing limit.
    # It is a phone installment category threshold.
    # ------------------------------------------------------------
    if (
        _same(bank, "Vak\u0131f Kat\u0131l\u0131m")
        and _same(product, "\u0130htiya\u00e7 Finansman\u0131")
    ):
        out["shopping_phone_rule_text"] = (
            "\u226420.000 TL: en fazla 10 taksit"
        )

        _cr = [
            r
            for r in rules.get("category_rules", [])
            if str(r.get("category_key") or "") != "cep_telefonu"
        ]

        _cr.append(
            {
                "category_key": "cep_telefonu",
                "category_label": "Cep Telefonu",
                "condition_text": "\u2264 20.000 TL",
                "min_amount": None,
                "max_amount": 20000.0,
                "min_inclusive": False,
                "max_inclusive": True,
                "max_installments": 10,
                "max_maturity_months": None,
                "source_text": (
                    "Cep telefonu al\u0131\u015fveri\u015fleriniz "
                    "20.000 TL'ye kadar en fazla 10 taksit"
                ),
            }
        )

        rules["category_rules"] = _cr

        display_metadata["phone_installment_rule"] = (
            "\u226420.000 TL: en fazla 10 taksit"
        )



    # FINAL_COMPLETENESS_RULE_SERIALIZE_V2
    # FINAL_COMPLETENESS_CANONICAL_V2 blogu rules/display_metadata
    # nesnelerini degistirdigi icin finance_rules_json bu noktada
    # yeniden serialize edilmelidir.
    rules["display_metadata"] = display_metadata
    out["finance_rules_json"] = json.dumps(
        rules,
        ensure_ascii=False,
        sort_keys=True,
    )

    # ZIRAAT_KUCUK_EKIPMAN_VERIFIED_RULE
    # Resmi urun metni:
    # - 250.000 TL = finansman tutari limiti DEGIL,
    #   finansmana konu ekipmanin KDV dahil satis bedeli uygunluk siniri.
    # - Satis bedelinin tamamina kadar = azami %100 finansman orani.
    _ke_bank = str(out.get("bank_name") or "").casefold()
    _ke_name = str(out.get("product_name") or "").casefold()

    if (
        "ziraat kat\u0131l\u0131m" in _ke_bank
        and str(out.get("product_family_key") or "") == "tarim_finansmani"
        and _ke_name == "k\u00fc\u00e7\u00fck ekipman finansman\u0131"
    ):
        # Satis bedelinin tamamina kadar kredilendirme.
        out["maximum_financing_ratio"] = 100.0

        # 250.000 TL maximum_amount olarak YAZILMAZ.
        # Bu deger ekipmanin satis bedeli uygunluk kosuludur.
        try:
            _ke_rules = json.loads(
                out.get("finance_rules_json") or "{}"
            )
        except Exception:
            _ke_rules = {}

        if not isinstance(_ke_rules, dict):
            _ke_rules = {}

        _ke_display = _ke_rules.setdefault(
            "display_metadata",
            {},
        )

        if not isinstance(_ke_display, dict):
            _ke_display = {}
            _ke_rules["display_metadata"] = _ke_display

        _ke_display["eligibility_condition"] = (
            "KDV dahil sat\u0131\u015f bedeli \u2264 250.000 TL"
        )

        _ke_display["financing_ratio_note"] = (
            "Sat\u0131\u015f bedelinin %100'\u00fcne kadar"
        )

        out["finance_rules_json"] = json.dumps(
            _ke_rules,
            ensure_ascii=False,
        )

    # TARIM_STATE_SUPPORT_FINAL_GUARD
    try:
        _final_rules = json.loads(out.get("finance_rules_json") or "{}")
    except Exception:
        _final_rules = {}
    _final_display = (
        _final_rules.get("display_metadata", {})
        if isinstance(_final_rules, dict)
        else {}
    )
    if (
        str(out.get("product_family_key") or "") == "tarim_finansmani"
        and isinstance(_final_display, dict)
        and _final_display.get("state_support_note")
    ):
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = None


    # EMLAK_KENTSEL_STATE_SUPPORT_FINAL_GUARD
    # 480 / 600 / 840 degerleri kar payi orani DEGILDIR.
    # Bunlar 6306 kapsamindaki yillik devlet kar payi destegi baz puanlaridir.
    _ek_bank = str(out.get("bank_name") or "").casefold()
    _ek_name = str(out.get("product_name") or "").casefold()

    if (
        "emlak kat\u0131l\u0131m" in _ek_bank
        and _ek_name == "kentsel d\u00f6n\u00fc\u015f\u00fcm finansman\u0131"
    ):
        out["profit_share_rate"] = None
        out["profit_share_rate_text"] = None

        try:
            _ek_rules = json.loads(
                out.get("finance_rules_json") or "{}"
            )
        except Exception:
            _ek_rules = {}

        if not isinstance(_ek_rules, dict):
            _ek_rules = {}

        _ek_display = _ek_rules.setdefault(
            "display_metadata",
            {},
        )

        if not isinstance(_ek_display, dict):
            _ek_display = {}
            _ek_rules["display_metadata"] = _ek_display

        # Ana tabloda kullanilacak kisa karar verisi.
        _ek_display["state_support_display"] = (
            "Ayl\u0131k %0,40\u2013%0,70"
        )

        # Mevcut generic devlet-destegi mekanizmasi icin semantik isaret.
        _ek_display["state_support_note"] = (
            "6306 kapsam\u0131nda devlet k\u00e2r pay\u0131 deste\u011fi"
        )

        _ek_display["state_support_bps_range"] = (
            "480\u2013840 baz puan"
        )

        # Kaynakta yayinlanan dogrulanmis detaylar.
        _ek_display["state_support_rules"] = [
            {
                "finance_type": "G\u00fc\u00e7lendirme",
                "annual_support_bps": 600,
                "monthly_support_rate": 0.50,
                "max_maturity_months": 120,
                "financing_upper_limit": 320000,
            },
            {
                "finance_type": "Konut Yap\u0131m",
                "annual_support_bps": 840,
                "monthly_support_rate": 0.70,
                "max_maturity_months": 120,
                "financing_upper_limit": 1250000,
            },
            {
                "finance_type": "Konut Edinme",
                "annual_support_bps": 840,
                "monthly_support_rate": 0.70,
                "max_maturity_months": 120,
                "financing_upper_limit": 1250000,
            },
            {
                "finance_type": "\u0130\u015fyeri Yap\u0131m",
                "annual_support_bps": 480,
                "monthly_support_rate": 0.40,
                "max_maturity_months": 84,
                "financing_upper_limit": 800000,
            },
            {
                "finance_type": "\u0130\u015fyeri Edinme",
                "annual_support_bps": 480,
                "monthly_support_rate": 0.40,
                "max_maturity_months": 84,
                "financing_upper_limit": 350000,
            },
        ]

        # EMLAK_KENTSEL_PRICING_TIER_CLEANUP
        # 480 / 600 / 840 degerleri musteri kar payi fiyatlamasi degildir.
        # Bunlar devlet kar payi destegi baz puanlaridir ve
        # state_support_rules altinda saklanir.
        _ek_rules["pricing_tiers"] = []

        _ek_display["state_support_special_note"] = (
            "\u0130lk Konut Yap\u0131m finansman\u0131nda 840 baz puan; "
            "sonraki kentsel d\u00f6n\u00fc\u015f\u00fcm konutlar\u0131nda "
            "belirtilen ko\u015fullarda 720 baz puan destek."
        )

        out["finance_rules_json"] = json.dumps(
            _ek_rules,
            ensure_ascii=False,
        )



    # VAKIF_TASIT_ALLOCATION_FEE_FINAL_GUARD
    # Resmi kaynak:
    # - 100.000 TL ornek finansmanda 500 TL tahsis ucreti
    # - Genel tahsis orani finansman tutarinin %0,5'i
    # 500 TL asla %500 olarak yorumlanamaz.
    _vt_bank = str(out.get("bank_name") or "").casefold()
    _vt_name = str(out.get("product_name") or "").casefold()

    if (
        _vt_bank == "vak\u0131f kat\u0131l\u0131m"
        and _vt_name == "ta\u015f\u0131t finansman\u0131"
    ):
        try:
            _vt_rules = json.loads(
                out.get("finance_rules_json") or "{}"
            )
        except Exception:
            _vt_rules = {}

        if not isinstance(_vt_rules, dict):
            _vt_rules = {}

        # Pricing tablosunda 500 TL'nin rate olarak kalmasini engelle.
        _vt_pricing = _vt_rules.get("pricing_tiers") or []

        if isinstance(_vt_pricing, list):
            for _vt_row in _vt_pricing:
                if not isinstance(_vt_row, dict):
                    continue

                _vt_rate = _vt_row.get(
                    "allocation_fee_rate"
                )

                if _vt_rate is None:
                    continue

                try:
                    _vt_rate_num = float(_vt_rate)
                except (TypeError, ValueError):
                    _vt_rate_num = None

                if (
                    _vt_rate_num is None
                    or not 0 <= _vt_rate_num <= 100
                ):
                    _vt_row["allocation_fee_rate"] = None

        # Allocation fee kuralini resmi kaynaga gore yeniden kur.
        _vt_fee_rules = _vt_rules.get("fee_rules") or []

        if not isinstance(_vt_fee_rules, list):
            _vt_fee_rules = []

        _vt_fee_rules = [
            _vt_row
            for _vt_row in _vt_fee_rules
            if not (
                isinstance(_vt_row, dict)
                and (
                    str(
                        _vt_row.get("fee_type") or ""
                    ).casefold() == "allocation"
                    or "tahsis" in str(
                        _vt_row.get("fee_label") or ""
                    ).casefold()
                )
            )
        ]

        _vt_fee_rules.append(
            {
                "fee_type": "allocation",
                "fee_label": "Tahsis \u00dccreti",
                "waived": False,
                "amount": None,
                "rate": 0.5,
                "note": (
                    "Resm\u00ee kayna\u011fa g\u00f6re tahsis "
                    "\u00fccreti finansman tutar\u0131n\u0131n "
                    "%0,5'idir (BSMV hari\u00e7). "
                    "100.000 TL i\u00e7in 500 TL, "
                    "\u00f6rnek tahsis tutar\u0131d\u0131r."
                ),
            }
        )

        _vt_rules["fee_rules"] = _vt_fee_rules

        _vt_display = _vt_rules.setdefault(
            "display_metadata",
            {},
        )

        if isinstance(_vt_display, dict):
            _vt_display["verified_vehicle_scope"] = (
                "0 km ve 2. el"
            )
            _vt_display["verified_vehicle_age"] = (
                "\u0130kinci elde 10 ya\u015fa kadar"
            )

        out["finance_rules_json"] = json.dumps(
            _vt_rules,
            ensure_ascii=False,
        )


    return out
