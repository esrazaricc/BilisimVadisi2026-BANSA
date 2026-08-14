from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductFeature:
    feature_key: str
    feature_label: str
    feature_value: str
    source_text: str
    extraction_method: str = "rule_based_source"


FEATURE_LABELS = {
    "usage_purpose": "Kullanım Amacı",
    "target_segment": "Hedef Kitle",
    "currency": "Para Birimi",
    "transaction_structure": "İşlem / Finansman Yapısı",
    "digital_process": "Dijital İşlem",
    "foreign_trade": "Dış Ticaret",
    "application_channel": "Başvuru / Kanal",
    "security_type": "Teminat / Güvence",
    "repayment_structure": "Ödeme / Kullanım Yapısı",
}


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_navigation_noise(sentence: str) -> bool:
    """
    Menü, breadcrumb ve çapraz ürün listeleme metinlerini
    nitel özellik kanıtı olarak kullanma.
    """
    key = _norm(sentence)

    navigation_markers = [
        "ana sayfa",
        "finansman ürünleri",
        "nakdi finansman",
        "gayri nakdi finansman",
    ]

    product_markers = [
        "tedarikçi finansmanı",
        "işletme finansmanı",
        "online finansman",
        "taksitli ticari finansman",
        "savunma sanayii",
        "ihtiyaç finansmanı",
        "taşıt finansmanı",
        "konut finansmanı",
    ]

    nav_count = sum(
        marker in key
        for marker in navigation_markers
    )

    product_count = sum(
        marker in key
        for marker in product_markers
    )

    if "ana sayfa" in key and product_count >= 2:
        return True

    if nav_count >= 2 and product_count >= 2:
        return True

    # Çok uzun, birden fazla ürün adı taşıyan cümleler çoğunlukla
    # breadcrumb/menu düzleştirmesidir.
    if len(sentence) >= 260 and product_count >= 3:
        return True

    return False


def _sentences(text: str) -> list[str]:
    cleaned = _clean(text)

    if not cleaned:
        return []

    result = []

    for part in re.split(
        r"(?<=[.!?])\s+|[\r\n]+",
        cleaned,
    ):
        sentence = _clean(part)

        if not 8 <= len(sentence) <= 700:
            continue

        if _is_navigation_noise(sentence):
            continue

        result.append(sentence)

    return result


def _product_kind(value: str) -> str | None:
    key = _norm(value)

    # Specific before generic.
    if re.search(r"elektronik teminat mektu[pb]", key):
        return "electronic_guarantee"

    if re.search(r"kabul[- /]?aval|\bkabul kred|\baval kred", key):
        return "kabul_aval"

    if re.search(r"referans mektu[pb]", key):
        return "reference_letter"

    if re.search(r"teminat mektu[pb]", key):
        return "guarantee_letter"

    if re.search(r"\belüs\b|elektronik ürün sened", key):
        return "elus"

    if "esnek destek" in key:
        return "esnek_support"

    if "taksitli ticari" in key:
        return "installment_commercial"

    return None


def _identity_phrases(product_name: str) -> list[str]:
    name = _norm(product_name)
    name = re.sub(r"\([^)]*\)", " ", name)
    name = name.replace("*", " ")
    name = re.sub(r"\s+", " ", name).strip()

    phrases = [name] if name else []

    strong_patterns = [
        r"elektronik teminat",
        r"kabul[- /]?aval",
        r"referans mektu[pb]",
        r"teminat mektu[pb]",
        r"\belüs\b",
        r"esnek destek",
        r"taksitli ticari",
        r"savunma sanayii(?: başkanlığı)?",
    ]

    for pattern in strong_patterns:
        match = re.search(pattern, name)
        if match:
            phrases.append(match.group(0))

    return list(dict.fromkeys(phrases))


def _local_sentences(
    sentences: list[str],
    product_name: str,
) -> list[str]:
    if not sentences:
        return []

    phrases = _identity_phrases(product_name)

    hits = []

    for index, sentence in enumerate(sentences):
        key = _norm(sentence)

        if any(phrase and phrase in key for phrase in phrases):
            hits.append(index)

    current_kind = _product_kind(product_name)

    if not hits:
        selected = set(range(min(5, len(sentences))))
    else:
        selected = set()

        for index in hits:
            selected.add(index)

            if index > 0:
                selected.add(index - 1)

            if index + 1 < len(sentences):
                selected.add(index + 1)

    if current_kind:
        for index, sentence in enumerate(sentences):
            if _product_kind(sentence) == current_kind:
                selected.add(index)

    candidates = [
        sentences[index]
        for index in sorted(selected)
    ]

    safe = []

    for sentence in candidates:
        sentence_kind = _product_kind(sentence)

        if (
            current_kind
            and sentence_kind
            and sentence_kind != current_kind
        ):
            continue

        safe.append(sentence)

    return safe


def _evidence(
    local: list[str],
    patterns: list[str],
) -> str:
    for sentence in local:
        key = _norm(sentence)

        if any(
            re.search(pattern, key, flags=re.IGNORECASE)
            for pattern in patterns
        ):
            return sentence[:500]

    return ""


def _add(
    result: list[ProductFeature],
    *,
    key: str,
    value: str | None,
    evidence: str,
    method: str = "rule_based_source",
) -> None:
    value = _clean(value)
    evidence = _clean(evidence)

    if not value:
        return

    if method == "rule_based_source" and not evidence:
        return

    result.append(
        ProductFeature(
            feature_key=key,
            feature_label=FEATURE_LABELS[key],
            feature_value=value,
            source_text=evidence[:500],
            extraction_method=method,
        )
    )


def _transaction_structure(
    product_name: str,
    local: list[str],
) -> tuple[str | None, str, str]:
    kind = _product_kind(product_name)

    mapping = {
        "electronic_guarantee": "Elektronik teminat mektubu",
        "kabul_aval": "Kabul / Aval",
        "reference_letter": "Referans mektubu",
        "guarantee_letter": "Teminat mektubu",
        "elus": "ELÜS teminatlı finansman",
        "esnek_support": "Esnek / limitli kullanım",
        "installment_commercial": "Taksitli finansman",
    }

    if kind in mapping:
        evidence = next(
            (
                sentence
                for sentence in local
                if _product_kind(sentence) == kind
            ),
            product_name,
        )

        return (
            mapping[kind],
            evidence,
            "product_identity",
        )

    return None, "", "rule_based_source"


def _purpose_full_page_fallback(
    product_name: str,
    raw_text: str,
) -> tuple[str | None, str]:
    """
    Bazı ürün sayfalarında amaç cümlesi ürün başlığının hemen
    yanında olmadığı için _local_sentences dışında kalabilir.

    Burada yalnız çok güçlü ve ürün adına özgü kalıplar için
    tüm sayfada ikinci tarama yapılır. Genel amaç tahmini
    yapılmaz; kaynak cümlesi bulunamazsa değer üretilmez.
    """
    name = _norm(product_name).replace("i̇", "i")

    rules = []

    if (
        "savunma sanayii başkanlığı" in name
        or "savunma sanayi başkanlığı" in name
    ):
        rules.append(
            (
                [
                    r"tedarik ekosistemine yönelik yatırımları desteklemek",
                    r"savunma sanayi.{0,160}tedarikçi.{0,160}(?:destek|yatırım)",
                ],
                "Savunma sanayii tedarikçilerinin yatırım ve finansman "
                "ihtiyaçlarının desteklenmesi",
            )
        )

    if name == "finansman desteği":
        rules.append(
            (
                [
                    r"yatırımlarınız için ihtiyacınız olan finansman deste",
                    r"hammadde.{0,220}(?:gayrimenkul|makine|teçhizat|hizmet bedeli)",
                ],
                "İşletme yatırımı / mal ve hizmet finansmanı",
            )
        )

    raw = _clean(raw_text)

    if not raw:
        return None, ""

    # Burada navigasyon filtresinden geçmiş cümleleri değil,
    # ham clean_text'i kullanıyoruz. Fallback kuralları yalnız
    # güçlü + ürün adına özgü olduğu için bu tarama genel bir
    # çıkarım kapısı açmaz.
    for patterns, value in rules:
        for pattern in patterns:
            match = re.search(
                pattern,
                raw,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            start = max(0, match.start() - 180)
            end = min(len(raw), match.end() + 220)

            evidence = _clean(
                raw[start:end]
            )

            return value, evidence

    return None, ""


def _usage_purpose(
    product_name: str,
    local: list[str],
    raw_text: str = "",
) -> tuple[str | None, str]:
    kind = _product_kind(product_name)

    kind_rules = {
        "electronic_guarantee": (
            [
                r"dijital ortam",
                r"elektronik teminat mektu[pb]",
            ],
            "Elektronik teminat işlemleri",
        ),
        "reference_letter": (
            [
                r"kredibilite",
                r"referans mektu[pb]",
            ],
            "Kredibilite / referans sunumu",
        ),
        "kabul_aval": (
            [
                r"ithalat",
                r"dış ticaret",
                r"vadeli olarak öden",
                r"poliçe vadesinde",
            ],
            "Dış ticaret işlemleri",
        ),
        "guarantee_letter": (
            [
                r"bir işin yapıl",
                r"borcun öden",
                r"malın teslim",
                r"garanti altına",
            ],
            "Ticari yükümlülüklerin güvence altına alınması",
        ),
    }

    if kind in kind_rules:
        patterns, value = kind_rules[kind]
        found = _evidence(local, patterns)

        if found:
            return value, found

    generic = [
        (
            [
                r"teminat yetersizli",
                r"finansmana erişimde zorluk",
            ],
            "Teminat desteğiyle finansmana erişimin kolaylaştırılması",
        ),
        (
            [
                r"savunma sanayi.{0,120}tedarikçi",
                r"tedarikçi.{0,120}savunma sanayi",
                r"tedarik ekosistemine yönelik yatırımları desteklemek",
            ],
            "Savunma sanayii tedarikçilerinin yatırım ve finansman ihtiyaçlarının desteklenmesi",
        ),
        (
            [
                r"yatırımlarınız için ihtiyacınız olan finansman deste",
                r"yatırımlar için.{0,100}finansman deste",
            ],
            "İşletme yatırımı / mal ve hizmet finansmanı",
        ),
        (
            [
                r"yurt içi finansman ihtiya",
            ],
            "Yurt içi finansman ihtiyaçlarının karşılanması",
        ),
        (
            [
                r"nakit akış.{0,100}destek",
                r"nakit akışına uygun",
            ],
            "İşletme nakit akışının desteklenmesi",
        ),
        (
            [
                r"kısa vadeli.{0,100}uzun vadeli.{0,100}mali gereksinim",
                r"mali gereksinimlerini karşılamak",
            ],
            "İşletmenin finansman ihtiyacının karşılanması",
        ),
        (
            [
                r"küçük işletmeler için.{0,160}finansman",
                r"küçük işletmelere.{0,160}finansman",
            ],
            "Küçük işletmelerin finansman ihtiyacının karşılanması",
        ),
        (
            [
                r"emtia veya hizmet alım",
                r"emtia.{0,80}hizmet alım",
            ],
            "Emtia / hizmet alımı finansmanı",
        ),
        (
            [
                r"işletme sermayesi",
                r"acil nakit",
            ],
            "İşletme sermayesi / nakit ihtiyacı",
        ),
        (
            [
                r"hammadde",
                r"yarı mamul",
                r"makine",
                r"teçhizat",
                r"hizmet bedeli",
            ],
            "İşletme yatırımı / mal ve hizmet finansmanı",
        ),
        (
            [
                r"elektronik ürün sened",
                r"\belüs\b",
                r"lisanslı depo",
                r"lisanlı depo",
            ],
            "Tarımsal ürün karşılığı finansman",
        ),
        (
            [
                r"finansman ihtiyac.{0,120}karşıla",
                r"finansman ihtiyac.{0,120}çözüm",
                r"finansman çözüm",
            ],
            "İşletmenin finansman ihtiyacının karşılanması",
        ),
    ]

    for patterns, value in generic:
        found = _evidence(local, patterns)

        if found:
            return value, found

    if raw_text:
        value, evidence = _purpose_full_page_fallback(
            product_name,
            raw_text,
        )

        if value and evidence:
            return value, evidence

    return None, ""


def _target_segment(
    local: list[str],
    scope: str,
) -> tuple[str | None, str, str]:
    values = []
    evidence_patterns = []

    terms = [
        (
            r"(?:\bkobi(?:'|’)?(?:ler)?(?:e|lere|ler için|lerin)|"
            r"\bkobi.{0,30}ölçekli)",
            "KOBİ",
        ),
        (
            r"\bişletme(?:ler)?(?:iniz|niz|lere|ler için|lerden)",
            "İşletmeler",
        ),
        (
            r"\besnaf(?:a|lar için|ların)",
            "Esnaf",
        ),
        (
            r"\bçiftçi(?:lere|ler için|lerin)",
            "Çiftçiler",
        ),
        (
            r"\bithalatçı(?:lara|lar için|ların)",
            "İthalatçılar",
        ),
        (
            r"\bihracatçı(?:lara|lar için|ların)",
            "İhracatçılar",
        ),
        (
            r"\btarım işletme(?:lerine|leri için|lerinin)",
            "Tarım işletmeleri",
        ),
    ]

    local_key = " ".join(_norm(item) for item in local)

    for pattern, label in terms:
        if re.search(pattern, local_key, flags=re.IGNORECASE):
            if label not in values:
                values.append(label)
            evidence_patterns.append(pattern)

    scope_key = _norm(scope)

    if "ticari" in scope_key:
        base = "Ticari"
    elif "bireysel" in scope_key:
        base = "Bireysel"
    else:
        base = None

    if base and base not in values:
        values.insert(0, base)

    if not values:
        return None, "", ""

    source = _evidence(local, evidence_patterns)

    if not source and base:
        source = f"scope={scope}"

    method = (
        "source_and_structured_scope"
        if evidence_patterns and base
        else (
            "rule_based_source"
            if evidence_patterns
            else "structured_scope"
        )
    )

    return " · ".join(values[:4]), source, method


def _currency(local: list[str]) -> tuple[str | None, str]:
    dual = [
        r"\btl\b.{0,60}yabancı para",
        r"yabancı para.{0,60}\btl\b",
        r"türk lirası.{0,60}yabancı para",
        r"yabancı para.{0,60}türk lirası",
        r"\btl\b.{0,40}\bdöviz\b",
        r"\bdöviz\b.{0,40}\btl\b",
        r"türk lirası.{0,40}\bdöviz\b",
        r"\bdöviz\b.{0,40}türk lirası",
        r"\btl\b.{0,80}(?:dolar|usd|euro|eur)",
        r"(?:dolar|usd|euro|eur).{0,80}\btl\b",
    ]

    found = _evidence(local, dual)

    if found:
        return "TL / Yabancı Para", found

    single = [
        (
            [
                r"\btl\b.{0,50}(?:cinsinden|üzerinden|olarak düzen)",
                r"(?:cinsinden|üzerinden).{0,50}\btl\b",
            ],
            "TL",
        ),
        (
            [
                r"\busd\b.{0,50}(?:cinsinden|üzerinden)",
                r"(?:cinsinden|üzerinden).{0,50}\busd\b",
            ],
            "USD",
        ),
        (
            [
                r"\beur\b.{0,50}(?:cinsinden|üzerinden)",
                r"(?:cinsinden|üzerinden).{0,50}\beur\b",
            ],
            "EUR",
        ),
    ]

    for patterns, value in single:
        found = _evidence(local, patterns)

        if found:
            return value, found

    foreign_only = _evidence(
        local,
        [
            r"\bdöviz\b.{0,40}(?:cinsinden|üzerinden)",
            r"(?:cinsinden|üzerinden).{0,40}\bdöviz\b",
            r"yabancı para.{0,40}(?:cinsinden|üzerinden)",
        ],
    )

    if foreign_only:
        return "Yabancı Para", foreign_only

    return None, ""


def _digital(
    product_name: str,
    local: list[str],
) -> tuple[str | None, str]:
    patterns = [
        r"dijital ortam",
        r"elektronik ortam",
        r"mobil (?:uygulama|şube|üzerinden)",
        r"internet şube",
        r"online (?:başvuru|işlem)",
    ]

    found = _evidence(local, patterns)

    if found:
        return "Evet", found

    if _product_kind(product_name) == "electronic_guarantee":
        return "Evet", product_name

    return None, ""


def _foreign_trade(local: list[str]) -> tuple[str | None, str]:
    found = _evidence(
        local,
        [
            r"dış ticaret",
            r"\bithalat",
            r"\bihracat",
            r"\bgümrük",
            r"\beximbank",
        ],
    )

    return ("Evet", found) if found else (None, "")


def _channels(local: list[str]) -> tuple[str | None, str]:
    values = []
    sources = {}

    def add(label: str, sentence: str) -> None:
        if label not in values:
            values.append(label)
        if label not in sources:
            sources[label] = sentence

    for sentence in local:
        # Türkçe büyük İ -> casefold sonrası "i̇" olabilir.
        # Kanal eşleşmesinde bunu düz i'ye indiriyoruz.
        key = _norm(sentence).replace("i̇", "i")

        if (
            "internet şube" in key
            and any(
                token in key
                for token in (
                    "başvur",
                    "üzerinden",
                    "self servis",
                    "yararlan",
                    "kullan",
                    "karşılay",
                    "sayesinde",
                )
            )
        ):
            add("İnternet Şubesi", sentence)

        if (
            re.search(r"\bmobil\b", key)
            and any(
                token in key
                for token in (
                    "başvur",
                    "üzerinden",
                    "self servis",
                    "yararlan",
                    "kullan",
                    "karşılay",
                    "uygulama",
                    "sayesinde",
                )
            )
        ):
            add("Mobil", sentence)

        if (
            re.search(r"\bsms\b", key)
            and any(
                token in key
                for token in (
                    "başvur",
                    "işlem",
                    "gönder",
                )
            )
        ):
            add("SMS", sentence)

        negative_branch_phrases = (
            "şubeye gitmenize gerek",
            "şubeye gitmeye gerek",
            "şubeye gitmeden",
            "şubeye gelmeden",
            "şubesine gitmeden",
        )

        if any(
            phrase in key
            for phrase in negative_branch_phrases
        ):
            continue

        physical_patterns = [
            r"\bşubelerimizden\b",
            r"\bşubelerimiz üzerinden\b",
            r"\bşubelerinden\b",
            r"\bşubeleri üzerinden\b",
            r"\bşubesinden\b",
            r"\bşubesine\b",
            r"\bşubeye\b",
            r"\bşubeden\b",
            r"\bbanka şubesi\b",
        ]

        if (
            any(
                re.search(pattern, key)
                for pattern in physical_patterns
            )
            and any(
                token in key
                for token in (
                    "başvur",
                    "gerçekleştir",
                    "talep",
                    "süreci başlat",
                    "işlem",
                )
            )
        ):
            add("Şube", sentence)

    if not values:
        return None, ""

    order = [
        "İnternet Şubesi",
        "Mobil",
        "Şube",
        "SMS",
    ]
    ordered = [label for label in order if label in values]

    source = ""
    for label in ordered:
        if sources.get(label):
            source = sources[label]
            break

    return " · ".join(ordered), source



def _security(local: list[str]) -> tuple[str | None, str]:
    rules = [
        (
            [
                r"elektronik ürün sened.{0,140}teminat",
                r"\belüs\b.{0,140}teminat",
            ],
            "ELÜS",
        ),
        ([r"\bipotek"], "İpotek"),
        ([r"\brehin"], "Rehin"),
        ([r"\bkefalet"], "Kefalet"),
        (
            [
                r"banka garanti",
                r"garantisi altına",
            ],
            "Banka garantisi",
        ),
    ]

    values = []
    source = ""

    for patterns, label in rules:
        found = _evidence(local, patterns)

        if found:
            if label not in values:
                values.append(label)
            if not source:
                source = found

    return (
        (" · ".join(values), source)
        if values
        else (None, "")
    )


def _variant_maturity_repayment(
    product_name: str,
    raw_text: str,
) -> tuple[str | None, str]:
    """
    Alt finansman yapıları farklı vade/taksit limitlerine
    sahipse bunu tek genel vade yerine alt yapı bazında göster.
    """
    name = _norm(product_name).replace("i̇", "i")
    raw = _clean(raw_text)

    if not raw:
        return None, ""

    # Kuveyt Türk SSB Destek Paketi
    if (
        "savunma sanayii başkanlığı" in name
        and "finansman destek paketi" in name
    ):
        leasing = re.search(
            r"leasing\s+finansman"
            r"[^.!?]{0,300}?"
            r"(?:toplamda\s+)?60\s*aya?\s+kadar",
            raw,
            flags=re.IGNORECASE,
        )

        business = re.search(
            r"işletme\s+finansman"
            r"[^.!?]{0,300}?"
            r"maksimum\s+12\s*ay",
            raw,
            flags=re.IGNORECASE,
        )

        if leasing and business:
            start = max(
                0,
                min(
                    leasing.start(),
                    business.start(),
                ) - 80,
            )
            end = min(
                len(raw),
                max(
                    leasing.end(),
                    business.end(),
                ) + 120,
            )

            evidence = _clean(
                raw[start:end]
            )

            return (
                "Leasing: azami 60 ay · "
                "İşletme Finansmanı: azami 12 ay",
                evidence,
            )

    # Türkiye Finans / Finansman Desteği
    #
    # 18 ay değeri ürünün tamamının vadesi değil,
    # Döviz Kredileri alt bölümünün taksit koşuludur.
    if name == "finansman desteği":
        fx_match = re.search(
            r"döviz\s+kredileri"
            r"[^.!?]{0,500}?"
            r"18\s+aya?\s+varan\s+taksit",
            raw,
            flags=re.IGNORECASE,
        )

        if fx_match:
            start = max(
                0,
                fx_match.start() - 120,
            )
            end = min(
                len(raw),
                fx_match.end() + 180,
            )

            return (
                "Döviz Kredileri: 18 aya varan taksit",
                _clean(
                    raw[start:end]
                ),
            )

    return None, ""



def _repayment(
    local: list[str],
    product_name: str = "",
    raw_text: str = "",
) -> tuple[str | None, str]:
    variant_value, variant_source = (
        _variant_maturity_repayment(
            product_name,
            raw_text,
        )
    )

    if variant_value:
        return variant_value, variant_source
    rules = [
        (
            [
                r"dilediğiniz zaman ve miktarda",
                r"limitiniz dahilinde",
            ],
            "Limit dahilinde esnek kullanım",
        ),
        ([r"esnek ödeme"], "Esnek ödeme"),
        (
            [
                r"\btaksitli\b.{0,80}(?:ödeme plan|geri ödeme|finansman sağlan|finansman kullan)",
                r"(?:ödeme plan|geri ödeme|finansman sağlan|finansman kullan).{0,80}\btaksitli\b",
            ],
            "Taksitli",
        ),
        (
            [
                r"vadeli olarak öden",
                r"vadeli öden",
                r"poliçe vadesinde",
            ],
            "Vadeli",
        ),
    ]

    values = []
    source = ""

    for patterns, label in rules:
        found = _evidence(local, patterns)

        if found:
            if label not in values:
                values.append(label)
            if not source:
                source = found

    return (
        (" · ".join(values[:3]), source)
        if values
        else (None, "")
    )


def extract_qualitative_features(
    *,
    product_name: str,
    product_family: str,
    scope: str,
    clean_text: str,
) -> list[ProductFeature]:
    all_sentences = _sentences(clean_text)

    local = _local_sentences(
        all_sentences,
        product_name,
    )

    result: list[ProductFeature] = []

    value, source = _usage_purpose(
        product_name,
        local,
        clean_text,
    )
    _add(
        result,
        key="usage_purpose",
        value=value,
        evidence=source,
    )

    value, source, method = _transaction_structure(
        product_name,
        local,
    )
    _add(
        result,
        key="transaction_structure",
        value=value,
        evidence=source,
        method=method,
    )

    value, source, method = _target_segment(local, scope)
    _add(
        result,
        key="target_segment",
        value=value,
        evidence=source,
        method=method,
    )

    for key, fn in [
        ("currency", lambda: _currency(local)),
        ("digital_process", lambda: _digital(product_name, local)),
        ("foreign_trade", lambda: _foreign_trade(local)),
        ("application_channel", lambda: _channels(local)),
        ("security_type", lambda: _security(local)),
        (
            "repayment_structure",
            lambda: _repayment(
                local,
                product_name,
                clean_text,
            ),
        ),
    ]:
        value, source = fn()

        _add(
            result,
            key=key,
            value=value,
            evidence=source,
        )

    deduped = {}

    for item in result:
        deduped[item.feature_key] = item

    return list(deduped.values())
