from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _evidence(text: str, *patterns: str, fallback: str = "") -> str:
    clean = _clean(text)
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if not match:
            continue
        start = max(0, match.start() - 80)
        end = min(len(clean), match.end() + 180)
        snippet = clean[start:end].strip(" -–—:;")
        return snippet
    return fallback


def _rules(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("finance_rules_json")
    if isinstance(raw, dict):
        data = deepcopy(raw)
    else:
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
    for key in (
        "category_rules",
        "amount_maturity_rules",
        "pricing_tiers",
        "fee_rules",
        "offer_rules",
    ):
        data.setdefault(key, [])
    return data


def _amount_rule(
    *,
    months: int,
    source_text: str,
    min_amount: float | None = None,
    max_amount: float | None = None,
    min_inclusive: bool = False,
    max_inclusive: bool = True,
) -> dict[str, Any]:
    return {
        "min_amount": min_amount,
        "max_amount": max_amount,
        "min_inclusive": min_inclusive,
        "max_inclusive": max_inclusive,
        "max_maturity_months": months,
        "source_text": source_text,
    }


def _category_rule(
    *,
    key: str,
    label: str,
    source_text: str,
    min_amount: float | None = None,
    max_amount: float | None = None,
    min_inclusive: bool = False,
    max_inclusive: bool = True,
    max_installments: int | None = None,
    max_maturity_months: int | None = None,
) -> dict[str, Any]:
    return {
        "category_key": key,
        "category_label": label,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "min_inclusive": min_inclusive,
        "max_inclusive": max_inclusive,
        "max_installments": max_installments,
        "max_maturity_months": max_maturity_months,
        "condition_text": (
            f"Maksimum {max_installments} taksit"
            if max_installments is not None
            else (
                "Tüm tutarlar"
                if min_amount is None and max_amount is None
                else "Kategori/tutar kuralı"
            )
        ),
        "source_text": source_text,
    }


def _offer_rule(
    *,
    source_text: str,
    max_amount: float | None = None,
    max_installments: int | None = None,
    max_maturity_months: int | None = None,
    interest_free: bool = False,
    condition_text: str,
) -> dict[str, Any]:
    return {
        "rule_type": "product_offer",
        "rule_label": "Ürüne Özel Finansman Koşulu",
        "min_amount": None,
        "max_amount": max_amount,
        "min_inclusive": False,
        "max_inclusive": True,
        "max_installments": max_installments,
        "max_maturity_months": max_maturity_months,
        "interest_free": interest_free,
        "condition_text": condition_text,
        "source_text": source_text,
    }


def apply_albaraka_standard_product_overrides(row: dict[str, Any]) -> dict[str, Any]:
    """
    Albaraka'nın kaynak sayfalarında açıkça yayımlanan fakat genel
    extractor'ın kaçırdığı/yanlış bağlama bağladığı standart ürün
    metriklerini kaynak metnine dayalı olarak düzeltir.

    Kural: kaynakta açıkça bulunmayan tutar/oran/vade üretilmez.
    """
    if str(row.get("bank_name") or "") != "Albaraka Türk":
        return row

    out = dict(row)
    name = _clean(out.get("product_name"))
    scope = _clean(out.get("scope"))
    text = _clean(out.get("clean_text"))
    rules = _rules(out)

    # Genel yanlış pozitifler: hesaplama aracındaki varsayılan tutarı
    # ürünün resmî üst limiti gibi göstermeyelim.
    if name == "İhtiyaç Finansmanı":
        out["maximum_financing_amount"] = None

    if (
        out.get("profit_share_rate") is None
        and not _clean(out.get("profit_share_rate_text"))
        and re.search(r"Hesaplama Aracı", text, flags=re.IGNORECASE)
        and re.search(
            r"Kâr Oranı\s*%\s*Oranı kendim gireceğim",
            text,
            flags=re.IGNORECASE,
        )
    ):
        out["profit_share_rate_text"] = "Hesaplama aracında dinamik"

    if (
        out.get("profit_share_rate") is None
        and not _clean(out.get("profit_share_rate_text"))
        and re.search(
            r"Finansman Kâr Oranları ve Ücretleri",
            text,
            flags=re.IGNORECASE,
        )
    ):
        out["profit_share_rate_text"] = (
            "Finansman Kâr Oranları ve Ücretleri sayfasında yayımlanıyor"
        )

    fixed_maturity = {
        "Deniz Taşıtları Finansmanı": 36,
        # Üst tanıtım metninde 36 ay ifadesi bulunsa da resmî
        # kasko/satış değeri tablosunda 400.000 TL ve altı için
        # azami 48 ay yayımlanıyor. Ürünün genel azami vadesi
        # bu nedenle tablodaki en yüksek yapılandırılmış vadedir.
        "Dijital Araç Finansmanı": 48,
        "Taşıt Kiralama Finansmanı": 36,
        "Togg Finansmanı": 48,
        "2B Arazi Finansmanı": 60,
        "Arsa Finansmanı": 60,
        "Konut Finansmanı": 120,
        "Bitkisel Üretim Finansmanı": 24,
        "Biçerdöver Finansmanı": 48,
        "Makine Ekipman Finansmanı": 48,
        "Seracılık Finansmanı": 48,
        "Tarla Alım Finansmanı": 48,
        "Traktör Finansmanı": 48,
        "Eğitim Finansmanı": 12,
        "Hac ve Umre Finansmanı": 36,
        "Jet Finansman": 36,
        "Motosiklet, ATV , Bisiklet": 36,
        "Pratik Finansman Kart": 36,
        "İhtiyaç Finansmanı": 36,
    }
    if name == "İş Yeri Finansmanı" and scope == "bireysel":
        fixed_maturity[name] = 60

    if name in fixed_maturity:
        value = fixed_maturity[name]
        # Yalnız kaynak metninde aynı vade görünüyorsa override uygula.
        if re.search(rf"\b{value}\s*(?:ay|aya|aylık|vadeye|kadar)", text, flags=re.IGNORECASE):
            out["maximum_maturity_months"] = value
        elif name in {"Deniz Taşıtları Finansmanı", "Taşıt Kiralama Finansmanı"} and re.search(r"36\s+kadar\s+vadelendirebilir", text, flags=re.IGNORECASE):
            out["maximum_maturity_months"] = 36

    # Kaynakta açık oranlar.
    if name in {"Arsa Finansmanı", "Leasing - Finansal Kiralama"}:
        if re.search(r"%\s*100[^.!?]{0,80}finansman|finansman[^.!?]{0,80}%\s*100", text, flags=re.IGNORECASE):
            out["maximum_financing_ratio"] = 100.0
    if name == "İş Yeri Finansmanı" and scope == "bireysel":
        if re.search(r"%\s*100[^.!?]{0,100}(?:finans|destek)|ekspertiz[^.!?]{0,100}%\s*100", text, flags=re.IGNORECASE):
            out["maximum_financing_ratio"] = 100.0
    if name == "Togg Finansmanı" and re.search(r"%\s*70[^.!?]{0,100}finansman", text, flags=re.IGNORECASE):
        out["maximum_financing_ratio"] = 70.0

    # ------------------------------------------------------------------
    # ALBARAKA ARAÇ FİNANSMANI — RESMÎ TABLO / ARAÇ DURUMU KURALLARI
    # ------------------------------------------------------------------
    # Taşıt Finansmanı ve Dijital Araç Finansmanı sayfalarında aynı
    # kasko/fatura değeri tablosu açıkça yayımlanıyor. Ana extractor
    # bazı sayfalarda son "%0 / kullandırım yok" satırını kaçırabildiği
    # için burada yalnız kaynak metninde tablo kanıtı varsa tam kuralı
    # kuruyoruz.
    vehicle_band_evidence = bool(
        re.search(r"400\.000\s*TL", text, flags=re.IGNORECASE)
        and re.search(r"800\.000\s*TL", text, flags=re.IGNORECASE)
        and re.search(r"1\.200\.000\s*TL", text, flags=re.IGNORECASE)
        and re.search(r"2\.000\.000", text, flags=re.IGNORECASE)
        and re.search(r"%?\s*70", text, flags=re.IGNORECASE)
        and re.search(r"%?\s*50", text, flags=re.IGNORECASE)
        and re.search(r"%?\s*30", text, flags=re.IGNORECASE)
        and re.search(r"%?\s*20", text, flags=re.IGNORECASE)
    )

    if name in {"Taşıt Finansmanı", "Dijital Araç Finansmanı"} and vehicle_band_evidence:
        out["maximum_maturity_months"] = 48
        out["maximum_financing_ratio"] = 70.0
        out["maturity_rules_text"] = (
            "≤ 400.000 TL → 48 ay | "
            "400.001–800.000 TL → 36 ay | "
            "800.001–1.200.000 TL → 24 ay | "
            "1.200.001–2.000.000 TL → 12 ay | "
            "> 2.000.000 TL → kullandırım yok"
        )
        out["financing_ratio_rules_text"] = (
            "≤ 400.000 TL → %70 | "
            "400.001–800.000 TL → %50 | "
            "800.001–1.200.000 TL → %30 | "
            "1.200.001–2.000.000 TL → %20 | "
            "> 2.000.000 TL → %0 / kullandırım yok"
        )
        out["vehicle_finance_rules_text"] = (
            "≤ 400.000 TL: %70 / 48 ay · "
            "400.001–800.000 TL: %50 / 36 ay · "
            "800.001–1.200.000 TL: %30 / 24 ay · "
            "1.200.001–2.000.000 TL: %20 / 12 ay · "
            "> 2.000.000 TL: Kullandırım yok"
        )

    # Araç durumunu ve ikinci el yaş sınırını yalnız ürünün kendi
    # metnindeki açık ifadelerden kur. Bu alan Streamlit ürün detayında
    # 0 km / 2. El ayrımını göstermek için de kullanılır.
    if name == "Taşıt Finansmanı":
        has_zero = bool(
            re.search(r"(?:sıfır\s*\(0\)|0\s*km|sıfır\s+araç)", text, flags=re.IGNORECASE)
        )
        has_second = bool(
            re.search(r"(?:ikinci\s+el|2\.?\s*el)", text, flags=re.IGNORECASE)
        )
        has_ten_year = bool(
            re.search(r"10\s+yaşını\s+aşmamış|10\s+yaşa\s+kadar|maksimum\s+10\s+yaş", text, flags=re.IGNORECASE)
        )
        if has_zero and has_second:
            out["vehicle_age_rules_text"] = (
                "0 km ve 2. El araçlar; ikinci el araçlarda azami 10 yaş"
                if has_ten_year
                else "0 km ve 2. El araçlar"
            )

    if name == "Dijital Araç Finansmanı":
        has_second = bool(
            re.search(r"(?:İkinci\s+el|2\.?\s*el)\s+araç", text, flags=re.IGNORECASE)
        )
        has_ten_year = bool(
            re.search(r"10\s+yaşa\s+kadar|maksimum\s+10\s+yaş", text, flags=re.IGNORECASE)
        )
        if has_second:
            out["vehicle_age_rules_text"] = (
                "Yalnız 2. El araçlar; ikinci el araçlarda azami 10 yaş"
                if has_ten_year
                else "Yalnız 2. El araçlar"
            )

    if name == "Togg Finansmanı":
        if re.search(r"(?:sıfır\s*\(0\)\s*km|sadece\s+sıfır\s+kilometre|yalnızca\s+sıfır\s+kilometre)", text, flags=re.IGNORECASE):
            out["vehicle_age_rules_text"] = "Yalnız 0 km Togg"

    if name == "Konut Finansmanı" and "STANDART KONUT MARJLARI" in text:
        out["housing_first_home_rules_text"] = (
            "≤ 5 milyon TL: A-B %90 / C %80 / Diğer %70 · "
            "5–7 milyon TL: A-B %80 / C %70 / Diğer %60 · "
            "7–10 milyon TL: A-B %70 / C %60 / Diğer %50 · "
            "10–20 milyon TL: A-B %50 / C %40 / Diğer %30 · "
            "> 20 milyon TL: A-B %40 / C %30 / Diğer %20"
        )
        out["housing_additional_home_rules_text"] = (
            "≤ 5 milyon TL: A-B %22,5 / C %20 / Diğer %17,5 · "
            "5–7 milyon TL: A-B %20 / C %17,5 / Diğer %15 · "
            "7–10 milyon TL: A-B %17,5 / C %15 / Diğer %12,5 · "
            "10–20 milyon TL: A-B %12,5 / C %10 / Diğer %7,5 · "
            "> 20 milyon TL: A-B %10 / C %7,5 / Diğer %5"
        )
        out["housing_finance_rules_json"] = json.dumps(
            {
                "standard_home": [
                    {"max_value": 5_000_000, "ab": 90, "c": 80, "other": 70},
                    {"min_value": 5_000_000, "max_value": 7_000_000, "ab": 80, "c": 70, "other": 60},
                    {"min_value": 7_000_000, "max_value": 10_000_000, "ab": 70, "c": 60, "other": 50},
                    {"min_value": 10_000_000, "max_value": 20_000_000, "ab": 50, "c": 40, "other": 30},
                    {"min_value": 20_000_000, "ab": 40, "c": 30, "other": 20},
                ],
                "additional_home": [
                    {"max_value": 5_000_000, "ab": 22.5, "c": 20, "other": 17.5},
                    {"min_value": 5_000_000, "max_value": 7_000_000, "ab": 20, "c": 17.5, "other": 15},
                    {"min_value": 7_000_000, "max_value": 10_000_000, "ab": 17.5, "c": 15, "other": 12.5},
                    {"min_value": 10_000_000, "max_value": 20_000_000, "ab": 12.5, "c": 10, "other": 7.5},
                    {"min_value": 20_000_000, "ab": 10, "c": 7.5, "other": 5},
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    # Açık ürün limitleri.
    if name == "Jet Ticari Finansman" and "2.000.000 TL" in text:
        out["maximum_financing_amount"] = 2_000_000.0
    if name == "Jet Finansman":
        if "minimum 1.000 TL" in text and "maksimum 60.000 TL" in text:
            out["minimum_financing_amount"] = 1_000.0
            out["maximum_financing_amount"] = 60_000.0
    if name == "Pratik Finansman Kart":
        if re.search(r"asgari\s+250\s*TL", text, flags=re.IGNORECASE):
            out["minimum_financing_amount"] = 250.0
        if re.search(r"150\.000\s*(?:TRY|TL)", text, flags=re.IGNORECASE):
            out["maximum_financing_amount"] = 150_000.0
    if name == "Şubesiz Umre Finansmanı" and "50.000 TL" in text:
        out["maximum_financing_amount"] = 50_000.0

    # 2B: kaynakta açık iki masraf muafiyeti.
    if name == "2B Arazi Finansmanı" and re.search(r"İpotek tesis ücreti ve ekspertiz ücreti ödemeyerek", text, flags=re.IGNORECASE):
        evidence = _evidence(text, r"İpotek tesis ücreti ve ekspertiz ücreti ödemeyerek[^.!?]*")
        out["fee_waiver_text"] = evidence
        rules["fee_rules"] = [
            {
                "fee_type": "mortgage_establishment",
                "fee_label": "İpotek Tesis Ücreti",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": evidence,
            },
            {
                "fee_type": "appraisal",
                "fee_label": "Ekspertiz Ücreti",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": evidence,
            },
        ]

    # Tutar-vade bantları.
    if name == "Jet Finansman":
        rules["amount_maturity_rules"] = [
            _amount_rule(months=36, max_amount=50_000.0, source_text=_evidence(text, r"1\.000-50\.000\s*TL[^.!?]{0,90}36\s*Ay")),
            _amount_rule(months=24, min_amount=50_000.0, max_amount=100_000.0, min_inclusive=False, max_inclusive=True, source_text=_evidence(text, r"50\.001-100\.000\s*TL[^.!?]{0,90}24\s*Ay")),
            _amount_rule(months=12, min_amount=100_000.0, min_inclusive=False, source_text=_evidence(text, r"100\.001\s*TL[^.!?]{0,90}12\s*Ay")),
        ]

        # Jet Finansman'ın resmî ürün sayfasında da teknoloji ürünü
        # taksit sınırları açıkça yayımlanır. Bunları Pratik Finansman
        # Kart'tan bağımsız olarak Jet ürününde de koru.
        jet_phone_low = _evidence(
            text,
            r"Cep telefonlarında\s+20\.000\s*TL[^.!?]{0,160}maksimum\s+12\s+taksit",
        )
        jet_phone_high = _evidence(
            text,
            r"20\.000\s*TL[^.!?]{0,180}üzerindeki[^.!?]{0,140}(?:3\s*Aya|3\s+taksit)",
        )
        jet_computer = _evidence(
            text,
            r"Bilgisayar alışverişlerinizde[^.!?]{0,120}maksimum\s+12\s+taksit",
        )
        jet_tablet = _evidence(
            text,
            r"Tablet alışverişlerinizde[^.!?]{0,120}maksimum\s+6\s+taksit",
        )
        jet_category_rules = []
        if jet_phone_low:
            jet_category_rules.append(
                _category_rule(
                    key="cep_telefonu", label="Cep Telefonu",
                    max_amount=20_000.0, max_installments=12,
                    source_text=jet_phone_low,
                )
            )
        if jet_phone_high:
            jet_category_rules.append(
                _category_rule(
                    key="cep_telefonu", label="Cep Telefonu",
                    min_amount=20_000.0, min_inclusive=False,
                    max_installments=3, source_text=jet_phone_high,
                )
            )
        if jet_computer:
            jet_category_rules.append(
                _category_rule(
                    key="bilgisayar", label="Bilgisayar",
                    max_installments=12, source_text=jet_computer,
                )
            )
        if jet_tablet:
            jet_category_rules.append(
                _category_rule(
                    key="tablet", label="Tablet",
                    max_installments=6, source_text=jet_tablet,
                )
            )
        if jet_category_rules:
            rules["category_rules"] = jet_category_rules

    if name in {"Motosiklet, ATV , Bisiklet", "İhtiyaç Finansmanı", "Hac ve Umre Finansmanı"}:
        upper_e = _evidence(text, r"125\.000\s*TL[^.!?]{0,100}36")
        middle_e = _evidence(text, r"125\.000[^.!?]{0,50}250\.000\s*TL[^.!?]{0,100}24")
        lower_e = _evidence(text, r"250\.000\s*TL[^.!?]{0,100}12")
        rules["amount_maturity_rules"] = [
            _amount_rule(months=36, max_amount=125_000.0, source_text=upper_e),
            _amount_rule(months=24, min_amount=125_000.0, max_amount=250_000.0, min_inclusive=False, max_inclusive=True, source_text=middle_e),
            _amount_rule(months=12, min_amount=250_000.0, min_inclusive=False, source_text=lower_e),
        ]

    if name == "Pratik Finansman Kart":
        rules["amount_maturity_rules"] = [
            _amount_rule(months=36, max_amount=125_000.0, source_text=_evidence(text, r"125\.000\s*TL[^.!?]{0,150}36\s*aya")),
            _amount_rule(months=24, min_amount=125_000.0, max_amount=150_000.0, min_inclusive=False, max_inclusive=True, source_text=_evidence(text, r"125\.000\s*TL\s+ile\s+150\.000\s*TL[^.!?]{0,150}24\s*aya")),
        ]

        # Pratik Finansman Kart'ın resmî SSS bölümündeki ürün bazlı
        # teknoloji taksit kurallarını açık kategori kuralları olarak tut.
        # Bunlar sektör adı değil, alışveriş/ürün kategorisi kuralıdır.
        phone_low = _evidence(
            text,
            r"Cep telefonlarında\s+20\.000\s*TL[^.!?]{0,160}maksimum\s+12\s+taksit",
        )
        phone_high = _evidence(
            text,
            r"20\.000\s*TL[^.!?]{0,180}üzerindeki[^.!?]{0,140}maksimum\s+3\s+taksit",
        )
        computer = _evidence(
            text,
            r"Bilgisayar alışverişlerinde[^.!?]{0,120}maksimum\s+12\s+taksit",
        )
        tablet = _evidence(
            text,
            r"Tablet alışverişlerinde[^.!?]{0,120}maksimum\s+6\s+taksit",
        )

        pratik_category_rules = []
        if phone_low:
            pratik_category_rules.append(
                _category_rule(
                    key="cep_telefonu",
                    label="Cep Telefonu",
                    max_amount=20_000.0,
                    max_installments=12,
                    source_text=phone_low,
                )
            )
        if phone_high:
            pratik_category_rules.append(
                _category_rule(
                    key="cep_telefonu",
                    label="Cep Telefonu",
                    min_amount=20_000.0,
                    min_inclusive=False,
                    max_installments=3,
                    source_text=phone_high,
                )
            )
        if computer:
            pratik_category_rules.append(
                _category_rule(
                    key="bilgisayar",
                    label="Bilgisayar",
                    max_installments=12,
                    source_text=computer,
                )
            )
        if tablet:
            pratik_category_rules.append(
                _category_rule(
                    key="tablet",
                    label="Tablet",
                    max_installments=6,
                    source_text=tablet,
                )
            )

        if pratik_category_rules:
            rules["category_rules"] = pratik_category_rules

        # Kaynaktaki ödemesiz dönem bilgisini koşul olarak görünür tut.
        ev = _evidence(text, r"ilk taksit tarihiniz 2 ay sonraya[^.!?]*|3 aya varan ödemesiz dönem[^.!?]*")
        if ev:
            rules["offer_rules"] = [
                _offer_rule(source_text=ev, condition_text="İlk taksit 2 ay sonra; isteğe bağlı 3 aya varan ödemesiz dönem")
            ]

    if name == "Şubesiz Umre Finansmanı":
        ev_amount = _evidence(text, r"50\.000\s*TL[^.!?]{0,100}vade farksız")
        ev_inst = _evidence(text, r"4\s*taksite kadar[^.!?]*")
        rules["offer_rules"] = [
            _offer_rule(
                source_text=" · ".join(x for x in (ev_amount, ev_inst) if x),
                max_amount=50_000.0,
                max_installments=4,
                interest_free=True,
                condition_text="50.000 TL'ye kadar vade farksız · 4 taksite kadar",
            )
        ]
        out["interest_free"] = True
        out["interest_free_text"] = "Vade farksız"

    # Togg tablosu: model + finansman tutarı + vade + oran birlikte korunur.
    if name == "Togg Finansmanı" and "Araç Modeli Vade (Ay) Kredi Tutarı Aylık Kar Oranı" in text:
        rows = [
            ("T10F V2", 12, 1_000_000.0, 0.00),
            ("T10F V2", 48, 1_700_000.0, 2.99),
            ("T10X V2", 12, 800_000.0, 0.00),
            ("T10X V2", 48, 1_700_000.0, 2.99),
            ("T10X V2 4MORE", 10, 1_500_000.0, 0.00),
            ("T10F V2 4MORE", 36, 1_500_000.0, 3.05),
        ]
        tiers = []
        for model, months, amount, rate in rows:
            source = _evidence(
                text,
                rf"{re.escape(model)}\s+{months}\s+{int(amount):,}".replace(",", r"\.") + rf"\s+{str(rate).replace('.', ',')}%",
                fallback=f"{model} | {months} | {int(amount):,} | {rate:.2f}%".replace(",", "."),
            )
            tiers.append(
                {
                    "pricing_variant": model,
                    "financing_amount": amount,
                    "maturity_months": months,
                    "profit_share_rate": rate,
                    "allocation_fee_rate": None,
                    "monthly_total_cost_rate": None,
                    "annual_total_cost_rate": None,
                    "source_text": source,
                }
            )
        rules["pricing_tiers"] = tiers

    out["finance_rules_json"] = json.dumps(rules, ensure_ascii=False, sort_keys=True)
    return out


# Nitel extraction'ta Albaraka menü/breadcrumb sızıntısını engellemek için
# bu alanları yeniden yalnız ürünün kendi kaynak cümlesinden kuruyoruz.
ALBARAKA_REBUILD_FEATURE_KEYS = {
    "usage_purpose",
    "application_channel",
    "digital_process",
    "security_type",
}


def albaraka_feature_overrides(
    *,
    product_name: str,
    product_family: str,
    scope: str,
    clean_text: str,
) -> dict[str, tuple[str, str]]:
    name = _clean(product_name)
    family = _clean(product_family)
    text = _clean(clean_text)
    result: dict[str, tuple[str, str]] = {}

    def add(key: str, value: str, *patterns: str) -> None:
        evidence = _evidence(text, *patterns)
        if evidence:
            result[key] = (value, evidence)

    # Kullanım amacı — ürünün kendi açıklamasından.
    purpose_specs: dict[tuple[str, str | None], tuple[str, tuple[str, ...]]] = {
        ("Bayide Finansman", "Alışveriş Finansmanı"): ("Alışveriş anında iş yerinde bireysel finansman", (r"alışveriş anında[^.!?]{0,180}bireysel finansman", r"iş yerlerinde kullanabileceğiniz bireysel finansman")),
        ("Bayide Finansman", "Ticari Finansman"): ("Müşterilere alışveriş finansmanı sunan alternatif satış kanalı", (r"ürün/hizmetlerini satın almak isteyen[^.!?]{0,220}alternatif online bir satış kanalı",)),
        ("Deniz Taşıtları Finansmanı", None): ("Deniz aracı alımının finansmanı", (r"Talep ettiğiniz her türlü deniz aracına dair kredi talebinde bulunabilirsiniz",)),
        ("Dijital Araç Finansmanı", None): ("Araç alımının dijital finansmanı", (r"araç finansmanı çözümüdür",)),
        ("Taşıt Finansmanı", None): ("Sıfır veya ikinci el araç alımının finansmanı", (r"araç alımlarında kullanabileceğiniz[^.!?]{0,160}finansman",)),
        ("Taşıt Kiralama Finansmanı", None): ("Araç/tekne gibi taşıtların kiralama hizmeti finansmanı", (r"taşıtları kiralamak için finansmana",)),
        ("Togg Finansmanı", None): ("Sıfır kilometre Togg araç alımının finansmanı", (r"Togg için özel olarak sunulan taşıt finansmanı",)),
        ("2B Arazi Finansmanı", None): ("2B arazi ediniminin finansmanı", (r"2B araziler için finansman desteği",)),
        ("Arsa Finansmanı", None): ("Arsa yatırımının finansmanı", (r"Arsa finansmanı ile yatırım[^.!?]{0,180}finansman",)),
        ("Akreditifler", None): ("Uluslararası ticarette şartlı ödeme/güvence işlemi", (r"uluslararası ticaret işlemlerinizi[^.!?]{0,120}", r"garantili bir ödeme aracı")),
        ("Jet Teminat Mektubu", None): ("Kamu ihale ve TOKİ teminat mektubu işlemleri", (r"Kamu İhale[^.!?]{0,220}mektuplarını[^.!?]{0,120}online",)),
        ("Kabul-Aval Finansmanları", None): ("İthalat işlemlerinde kabul/aval güvencesi", (r"uygun koşullarda ürün ithal edebilirsiniz",)),
        ("Referans Mektupları", None): ("Kredibilite / referans sunumu", (r"kredibilitenizin[^.!?]{0,160}değerlendirilmesini",)),
        ("Teminat Mektupları", None): ("Ticari yükümlülüklerin güvence altına alınması", (r"işbirliği yaptığınız kurumlara[^.!?]{0,180}güvence",)),
        ("Konut Finansmanı", None): ("Konut ediniminin finansmanı", (r"Dilediğiniz ev[^.!?]{0,180}120 aya",)),
        ("Leasing - Finansal Kiralama", None): ("İş yatırımı, teknoloji ve ekipman finansmanı", (r"işinizi geliştirmeyi veya kullandığınız teknolojiyi yenilemeyi[^.!?]{0,180}", r"Yatırım projelerinizde[^.!?]{0,160}finansman")),
        ("Bitkisel Üretim Finansmanı", None): ("Tohum, gübre, ilaç, mazot gibi bitkisel üretim ihtiyaçlarının finansmanı", (r"Bitkisel üretim faaliyetlerinizle ilgili tohum, gübre, ilaç, mazot",)),
        ("Biçerdöver Finansmanı", None): ("Biçerdöver alımının finansmanı", (r"biçerdöver alımlarınıza yönelik finansman desteği",)),
        ("Makine Ekipman Finansmanı", None): ("Tarımsal makine ve ekipman alımının finansmanı", (r"ekipman ve makine alımına yönelik finansman desteği",)),
        ("Seracılık Finansmanı", None): ("Sera yapımı, bakımı ve modernizasyonunun finansmanı", (r"Sera yapımı, bakımı ve modernizasyonu[^.!?]{0,180}finanse",)),
        ("Tarla Alım Finansmanı", None): ("Tarla alımının finansmanı", (r"alacağınız tarlalarınızı[^.!?]{0,180}finanse",)),
        ("Traktör Finansmanı", None): ("Traktör alımının finansmanı", (r"traktör alımlarınıza yönelik finansman desteği",)),
        ("DBS Fatura Teminatlı Kredi", None): ("DBS'ye yüklenen faturaların teminatıyla fon kullanımı", (r"DBS sistemine yükledikleri faturaları teminata vererek fon",)),
        ("Elüs Teminatlı Kredi", None): ("ELÜS teminatıyla tarımsal ürün karşılığı finansman", (r"ELÜS[^.!?]{0,220}(?:teminat|finans)",)),
        ("Jet Ticari Finansman", None): ("İşletme finansman ihtiyacının dijital kanallardan karşılanması", (r"İşletmenizi büyütmek isteyen[^.!?]{0,180}finansman ihtiyacınız", r"kurumsal finansman kullanabileceği ürünümüzdür")),
        ("Katılım Finans Kefalet (KFK)", None): ("Teminat desteğiyle finansmana erişimin kolaylaştırılması", (r"teminat yetersizliği[^.!?]{0,220}finansmana erişim",)),
        ("Kira Sertifikası Teminatlı Kredi", None): ("Kira sertifikalarının teminatıyla finansman", (r"kira sertifikalarınızı finansmanlarınızda teminat olarak",)),
        ("Pratik KOBİ Kart", None): ("POS ve online kanallarda işletme finansman ihtiyacının karşılanması", (r"Fiziki Pos/Mail Order/Sanal Pos[^.!?]{0,180}işletme finansman ihtiyaçlarını",)),
        ("Proje Finansmanı", None): ("Yenilenebilir enerji, altyapı ve imalat yatırımlarının finansmanı", (r"Yenilenebilir enerji projeleri[^.!?]{0,220}yatırım projelerine kaynak",)),
        ("Tedarikçi Finansmanı", None): ("Vadeli alacakların teminata verilerek finansmana dönüştürülmesi", (r"vadeli alacağı olan kobiler[^.!?]{0,180}teminata vererek finansman",)),
        ("İş Yeri Finansmanı", "Ticari Finansman"): ("İşletme yatırımı / mal, hizmet ve gayrimenkul finansmanı", (r"mamul|hammadde|gayrimenkul|hizmet bedeli",)),
        ("BES Teminatlı Finansman", None): ("BES birikimini bozmadan ihtiyaç finansmanı", (r"BES birikimlerini[^.!?]{0,220}teminat göstererek finansman",)),
        ("Eğitim Finansmanı", None): ("Eğitim masraflarının finansmanı", (r"eğitim masraflarını 12 aya kadar",)),
        ("Hac ve Umre Finansmanı", None): ("Hac ve umre ziyaret giderlerinin finansmanı", (r"hac ve umre ziyaretleriniz için gerekli olan ödeme için finansman desteği",)),
        ("Jet Finansman", None): ("Alışveriş, eğitim, sağlık, tatil ve benzeri ihtiyaçların finansmanı", (r"alışverişleriniz için ya da eğitim, sağlık, tatil[^.!?]{0,220}",)),
        ("Motosiklet, ATV , Bisiklet", None): ("Motosiklet, ATV veya bisiklet alımının finansmanı", (r"motosiklet, ATV veya bisikleti satın almak",)),
        ("Pratik Finansman Kart", None): ("Yurt içi POS ve online alışveriş ihtiyaçlarının finansmanı", (r"yurtiçi tüm POS ve online alışverişlerinizde kullanabileceğiniz",)),
        ("SMS’ li Finansman", None): ("Konut, taşıt, tüketici ve eğitim finansmanı için SMS başvurusu", (r"SMS ile Konut, Taşıt, Tüketici finansmanı", r"Bu ürün aracılığıyla konut, taşıt, tüketici ve eğitim finansmanı")),
        ("İhtiyaç Finansmanı", None): ("Bireysel tüketim ve temel ihtiyaçların finansmanı", (r"eşya alımlarından sağlık giderlerine, tatil planlarından teknolojik aletlere",)),
        ("Şubesiz Umre Finansmanı", None): ("Umre organizasyonunun finansmanı", (r"umre organizasyonlarında kullanılmak üzere",)),
        ("İş Yeri Finansmanı", "İş Yeri Finansmanı"): ("Büro, dükkân, mağaza, depo gibi iş yeri gayrimenkulünün finansmanı", (r"büro, dükkan, mağaza, lojman, depo[^.!?]{0,180}finansman",)),
    }

    spec = purpose_specs.get((name, family)) or purpose_specs.get((name, None))
    if spec:
        add("usage_purpose", spec[0], *spec[1])

    # Kanal — menüdeki "Albaraka Mobil" ifadesini değil, ürünün
    # başvuru/işlem cümlesini kanıt olarak kullan.
    channel_specs: dict[tuple[str, str | None], tuple[str, tuple[str, ...]]] = {
        ("Bayide Finansman", "Alışveriş Finansmanı"): ("Bayi / İş Yeri Platformu", (r"iş yerindeki yetkili aracılığıyla[^.!?]{0,180}Bayide Finansman Platformu",)),
        ("Deniz Taşıtları Finansmanı", None): ("Şube", (r"en yakın Albaraka Türk şubesine[^.!?]{0,120}başvuru",)),
        ("Dijital Araç Finansmanı", None): ("Albaraka Mobil", (r"Albaraka Mobil uygulaması üzerinden[^.!?]{0,180}başvur",)),
        ("Taşıt Finansmanı", None): ("Web Sitesi · Albaraka Mobil · SMS · Şube", (r"Başvuru Kanalları Web Sitesi Albaraka Mobil SMS Şube",)),
        ("Taşıt Kiralama Finansmanı", None): ("Şube", (r"en yakın Albaraka Türk şubesine[^.!?]{0,140}başvuru",)),
        ("Togg Finansmanı", None): ("Şube", (r"başvuruları yalnızca şubelerimizden",)),
        ("2B Arazi Finansmanı", None): ("Web Sitesi · Albaraka Mobil · SMS · Şube", (r"Başvuru Kanalları Web Sitesi Albaraka Mobil SMS Şube",)),
        ("Arsa Finansmanı", None): ("Web Sitesi · Albaraka Mobil · SMS · Şube", (r"Başvuru Kanalları Web Sitesi Albaraka Mobil SMS Şube",)),
        ("Akreditifler", None): ("Şube", (r"Akreditif finansmanları kullanmak için[^.!?]{0,140}Şubesi",)),
        ("Jet Teminat Mektubu", None): ("Kurumsal İnternet Bankacılığı", (r"Kurumsal İnternet Bankacılığı üzerinden[^.!?]{0,180}",)),
        ("Kabul-Aval Finansmanları", None): ("Şube", (r"Kabul-aval finansmanları kullanmak için[^.!?]{0,140}Şubesi",)),
        ("Referans Mektupları", None): ("Şube", (r"Referans mektubu talebiniz için[^.!?]{0,140}Şubesi",)),
        ("Teminat Mektupları", None): ("Şube", (r"Teminat Mektubu talebiniz için[^.!?]{0,140}Şubesi",)),
        ("Konut Finansmanı", None): ("Web Sitesi · Albaraka Mobil · SMS · Şube", (r"Başvuru Kanalları Web Sitesi Albaraka Mobil SMS Şube",)),
        ("Leasing - Finansal Kiralama", None): ("Şube", (r"Albaraka Türk şubelerine bekliyoruz",)),
        ("Bayide Finansman", "Ticari Finansman"): ("Bayi / Şube", (r"şubeye gerek kalmadan 60\.000\s*TL[^.!?]{0,180}|60\.000\s*TL üstünde[^.!?]{0,180}şubemize",)),
        ("Biçerdöver Finansmanı", None): ("Tarım Bankacılığı Şubesi", (r"Tarım Bankacılığı Hizmeti veren şubelerimize",)),
        ("DBS Fatura Teminatlı Kredi", None): ("Şube", (r"en yakın Albaraka Türk şubemize",)),
        ("Elüs Teminatlı Kredi", None): ("Şube", (r"en yakın Albaraka Türk şubemize",)),
        ("Jet Ticari Finansman", None): ("Kurumsal İnternet Bankacılığı / Dijital Kanallar", (r"Kurumsal internet bankacılığındaki[^.!?]{0,180}", r"şubeye gitmeden dijital kanallar üzerinden")),
        ("Katılım Finans Kefalet (KFK)", None): ("Şube", (r"en yakın şubemize bekliyoruz",)),
        ("Kira Sertifikası Teminatlı Kredi", None): ("Şube", (r"başvuru için sizi şubelerimize",)),
        ("Pratik KOBİ Kart", None): ("Fiziki POS · Mail Order · Sanal POS / Şube", (r"Fiziki Pos/Mail Order/Sanal Pos[^.!?]{0,180}",)),
        ("Proje Finansmanı", None): ("Şube", (r"başvuru için sizi şubelerimize",)),
        ("Tedarikçi Finansmanı", None): ("Şube", (r"en yakın Albaraka Türk şubesine",)),
        ("BES Teminatlı Finansman", None): ("Şube", (r"finansmana yalnızca Albaraka Türk şubelerinden",)),
        ("Eğitim Finansmanı", None): ("Şube · Web Sitesi / Albaraka Mobil (Jet Finansman üzerinden)", (r"Şubelerimiz üzerinden Eğitim Finansmanına başvur", r"Şubeye gitmeden[^.!?]{0,180}Jet Finansman")),
        ("Hac ve Umre Finansmanı", None): ("Şube · Web Sitesi / Albaraka Mobil (Jet Finansman üzerinden)", (r"Şubeye gitmeden[^.!?]{0,180}Jet Finansman", r"Şubelerimiz üzerinden Hac ve Umre Finansmanına başvur")),
        ("Jet Finansman", None): ("Albaraka Mobil · Web Sitesi", (r"Albaraka Mobil üzerinden ya da .Hemen Başvur.", r"web sitemiz üzerinden Jet finansman başvurunuzu")),
        ("Motosiklet, ATV , Bisiklet", None): ("Şube", (r"en yakın Albaraka Türk şubesine uğrayın",)),
        ("Pratik Finansman Kart", None): ("Albaraka Mobil · İnternet Şubesi · Şube", (r"Albaraka Mobil ve İnternet şubemiz üzerinden[^.!?]{0,160}şubelerimize",)),
        ("SMS’ li Finansman", None): ("SMS 4462 · Şube", (r"4462’ye mesaj atılır", r"herhangi bir şubeye başvurarak")),
        ("İhtiyaç Finansmanı", None): ("Web Sitesi · Albaraka Mobil · İnternet Şubesi · Şube", (r"mobil uygulama ve internet şube üzerinden", r"Başvuru Kanalları")),
        ("Şubesiz Umre Finansmanı", None): ("Albaraka Mobil", (r"tüm süreç Albaraka Mobil üzerinden",)),
        ("İş Yeri Finansmanı", "İş Yeri Finansmanı"): ("Şube", (r"en yakın Albaraka Türk şubesine[^.!?]{0,120}başvuru",)),
    }
    ch = channel_specs.get((name, family)) or channel_specs.get((name, None))
    if ch:
        add("application_channel", ch[0], *ch[1])

    # Dijital süreç yalnız kaynak açıkça ürün işlem akışını dijital diye
    # tarif ediyorsa "Evet" olur.
    digital_specs = {
        "Dijital Araç Finansmanı": ("Evet", (r"Albaraka Mobil uygulaması üzerinden[^.!?]{0,180}işlemlerinizi",)),
        "Jet Teminat Mektubu": ("Evet", (r"online olarak düzenleyip",)),
        "Jet Ticari Finansman": ("Evet", (r"şubeye gitmeden dijital kanallar üzerinden",)),
        "Eğitim Finansmanı": ("Evet", (r"Şubeye gitmeden[^.!?]{0,180}eğitim finansmanınızı[^.!?]{0,180}Jet Finansman",)),
        "Hac ve Umre Finansmanı": ("Evet", (r"Şubeye gitmeden[^.!?]{0,180}hac/umre finansmanınızı[^.!?]{0,180}Jet Finansman", r"Şubeye gitmeden[^.!?]{0,180}Jet Finansman")),
        "Jet Finansman": ("Evet", (r"Albaraka Mobil üzerinden anında finansman",)),
        "Pratik Finansman Kart": ("Evet", (r"online alışverişlerinizde", r"Albaraka Mobil ve İnternet")),
        "Şubesiz Umre Finansmanı": ("Evet", (r"Tamamen Dijital Süreç", r"tamamen mobil uygulama üzerinden")),
    }
    if name in digital_specs:
        add("digital_process", digital_specs[name][0], *digital_specs[name][1])


    # Kaynak sayfası açıkça birden fazla başvuru sahibi türü yayımlıyorsa
    # path'ten gelen genel "Bireysel" etiketine düşürme.
    if name == "Eğitim Finansmanı":
        add(
            "target_segment",
            "Bireysel · Serbest Meslek · Tüzel Kişi",
            r"gerçek kişi olarak yararlanmak",
            r"serbest meslek sahibi olarak yararlanmak",
            r"tüzel kişi olarak yararlanmak",
        )
    if name == "Hac ve Umre Finansmanı":
        add(
            "target_segment",
            "Bireysel · Serbest Meslek · Tüzel Kişi",
            r"gerçek kişi olarak yararlanmak",
            r"serbest meslek sahibi olarak yararlanmak",
            r"tüzel kişi olarak yararlanmak",
        )

    # Başvuru/işlem yapısını ödeme yapısıyla karıştırmadan ayrı metrikte tut.
    if name == "SMS’ li Finansman":
        add(
            "transaction_structure",
            "SMS ile ön onay · Finansman kullanımı şubede",
            r"4462’ye mesaj atılır",
            r"Onay alan müşteri[^.!?]{0,220}şubeye başvurarak",
        )
    if name == "BES Teminatlı Finansman":
        add(
            "transaction_structure",
            "BES birikimi teminat olarak kullanılır · Nakit kullandırım yok",
            r"BES birikimlerini[^.!?]{0,180}teminat göstererek finansman",
            r"Nakit olarak finansman desteği sağlanmamaktadır",
        )

    security_specs = {
        "DBS Fatura Teminatlı Kredi": ("DBS'ye yüklenen faturalar", (r"faturaları teminata vererek",)),
        "Elüs Teminatlı Kredi": ("ELÜS", (r"ELÜS[^.!?]{0,180}teminat",)),
        "Katılım Finans Kefalet (KFK)": ("KFK kefaleti", (r"KFK kefaletinden yararlanarak",)),
        "Kira Sertifikası Teminatlı Kredi": ("Kira sertifikası", (r"kira sertifikalarınızı[^.!?]{0,120}teminat",)),
        "BES Teminatlı Finansman": ("BES birikimi", (r"BES birikimlerini[^.!?]{0,160}teminat",)),
        "Eğitim Finansmanı": ("Kefil şartı yok", (r"kefil şartı yok",)),
    }
    if name in security_specs:
        add("security_type", security_specs[name][0], *security_specs[name][1])

    # Ek, açık kaynaklı metrikler.
    if name == "Jet Teminat Mektubu":
        add("transaction_limit", "15.000.000 TL mektup üst limiti", r"Mektup tutarı üst limiti 15\.000\.000\s*TL")
    if name == "Konut Finansmanı":
        add("cost_advantage", "KKDF ve BSMV muafiyeti", r"KKDF\), Banka ve Sigorta Muameleleri Vergisi \(BSMV\) ödemelerinden muaf")
    if name == "BES Teminatlı Finansman":
        add("cost_advantage", "Standart oranlardan 20 puan indirim", r"standart oranlarımız üzerinden 20 puan indirim")
    if name == "Bayide Finansman" and family == "Ticari Finansman":
        add("transaction_limit", "Bayide şubesiz işlem 60.000 TL'ye kadar; üzeri şubede tamamlanır", r"şubeye gerek kalmadan 60\.000\s*TL", r"60\.000\s*TL üstünde[^.!?]{0,180}şubemize")
    if name == "Leasing - Finansal Kiralama":
        add("cost_advantage", "%1 KDV oranı (leasinge özgü)", r"leasinge özgü %\s*1\s*KDV oranı")
    if name == "Pratik Finansman Kart":
        # Resmî ürün metnindeki iki farklı anlatımı da kabul et.
        # Kaynakta mevcut örnekler:
        # - "ilk taksit tarihiniz 2 ay sonraya otomatik olarak atanır"
        # - "Dilerseniz 3 aya varan ödemesiz dönem seçebilirsiniz"
        # - SSS: "kartın ilk taksit tarihini toplamda 3 ay öteleyebilirsiniz"
        add(
            "repayment_structure",
            "İlk taksit 2 ay sonraya otomatik atanır · İlk taksit toplamda 3 aya kadar ötelenebilir",
            r"ilk taksit tarihiniz 2 ay sonraya otomatik olarak atanır",
            r"ilk taksit tarihiniz 2 ay sonraya",
            r"3 aya varan ödemesiz dönem seçebilirsiniz",
            r"3 aya varan ödemesiz dönem",
            r"ilk taksit tarihini toplamda 3 ay öteleyebilirsiniz",
            r"kartın ilk taksit tarihini toplamda 3 ay öteleyebilirsiniz",
        )
    if name == "Eğitim Finansmanı":
        add("repayment_structure", "12 aya kadar · Aylık eşit veya değişken tutarlı ödeme", r"12 aya kadar taksitlendir", r"aylık eşit taksitler[^.!?]{0,120}her ay farklı miktarda")
    if name == "Hac ve Umre Finansmanı":
        add("repayment_structure", "125.000 TL’ye kadar 36 ay · 125.001–250.000 TL 24 ay · 250.000 TL üzeri 12 ay", r"125\.000 TL[^.!?]{0,220}36 ay[^.!?]{0,220}24 ay[^.!?]{0,220}12 ay")
    if name == "Jet Finansman":
        add("repayment_structure", "Tutar bandına göre 36/24/12 ay · İlk taksit en geç 45 gün sonra", r"1\.000-50\.000 TL[^.!?]{0,180}36 Ay", r"İlk taksit için en geç 45 gün sonrasına kadar")
    if name == "Motosiklet, ATV , Bisiklet":
        add("repayment_structure", "Aylık eşit taksit · Tutar bandına göre 36/24/12 ay", r"Aylık eşit taksitli ödeme", r"125\.000 TL[^.!?]{0,220}36 ay[^.!?]{0,220}24 ay[^.!?]{0,220}12 ay")
    if name == "İhtiyaç Finansmanı":
        add("repayment_structure", "Tutar bandına göre 36/24/12 ay · Esnek ödeme planı", r"125\.000 TL[^.!?]{0,220}36 aya[^.!?]{0,220}24 aya[^.!?]{0,220}12 aya", r"esnek ödeme planları")
    if name == "Şubesiz Umre Finansmanı":
        add("repayment_structure", "4 eşit taksit · Vade farksız", r"4 eşit taksit", r"4 taksite kadar", r"Vade Farksız Finansman")
    if name == "İş Yeri Finansmanı" and family == "İş Yeri Finansmanı":
        add("repayment_structure", "Aylık eşit · 2/3 ayda bir · değişken tutarlı esnek taksit", r"2 ayda bir, 3 ayda bir ya da değişken tutarlı esnek taksitler")

    return result
