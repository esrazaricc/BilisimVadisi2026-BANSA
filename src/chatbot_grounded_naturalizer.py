# CHATBOT_GROUNDED_NATURALIZER_V1_6

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata


MODEL_ID = "Qwen/Qwen3-0.6B"


@dataclass(frozen=True)
class NaturalAnswerResult:

    text: str

    status: str

    model_used: bool

    verified: bool

    fallback_used: bool

    reasons: tuple[str, ...]


_MODEL = None
_TOKENIZER = None
_DEVICE = None


_BANK_ALIASES = {
    "albaraka turk": (
        "albaraka turk",
        "albaraka",
    ),
    "kuveyt turk": (
        "kuveyt turk",
    ),
    "turkiye finans": (
        "turkiye finans",
    ),
    "vakif katilim": (
        "vakif katilim",
    ),
    "ziraat katilim": (
        "ziraat katilim",
    ),
    "turkiye emlak katilim": (
        "turkiye emlak katilim",
        "emlak katilim",
    ),
    "dunya katilim": (
        "dunya katilim",
    ),
    "hayat finans": (
        "hayat finans",
    ),
    "tom katilim": (
        "tom katilim",
        "tom bank",
    ),
}


_KNOWN_PRODUCT_PHRASES = (
    "konut finansmani",
    "ihtiyac finansmani",
    "egitim finansmani",
    "tasit finansmani",
    "arac finansmani",
    "is yeri finansmani",
    "isyeri finansmani",
    "hac ve umre finansmani",
    "umre finansmani",
    "jet finansman",
    "arsa finansmani",
)


def _normalize(
    value,
) -> str:

    text = str(
        value
        or ""
    )

    text = text.translate(
        str.maketrans(
            {
                "\u0131": "i",
                "\u0130": "I",
                "\u015f": "s",
                "\u015e": "S",
                "\u011f": "g",
                "\u011e": "G",
                "\u00fc": "u",
                "\u00dc": "U",
                "\u00f6": "o",
                "\u00d6": "O",
                "\u00e7": "c",
                "\u00c7": "C",
            }
        )
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        ch
        for ch in text
        if not unicodedata.combining(
            ch
        )
    )

    text = text.casefold()

    text = re.sub(
        r"[^a-z0-9%.,:/+-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _detect_attribute(
    question: str,
) -> str | None:

    text = _normalize(
        question
    )

    if any(
        value in text
        for value in (
            "kac ay",
            "vade",
            "vadeli",
            "maksimum sure",
            "azami sure",
        )
    ):
        return "maturity"

    if any(
        value in text
        for value in (
            "kar payi",
            "kar orani",
            "oran nedir",
        )
    ):
        return "rate"

    if any(
        value in text
        for value in (
            "tahsis ucreti",
            "ekspertiz ucreti",
            "ipotek ucreti",
            "masraf",
            "ucret",
        )
    ):
        return "fee"

    if any(
        value in text
        for value in (
            "son tarih",
            "ne zamana kadar",
            "hangi tarihe kadar",
        )
    ):
        return "date"

    if any(
        value in text
        for value in (
            "limit",
            "en fazla ne kadar",
            "maksimum tutar",
            "azami tutar",
        )
    ):
        return "limit"

    return None


def _clean_fallback(
    text: str,
) -> str:

    value = str(
        text
        or ""
    ).strip()

    for marker in (
        "\nKaynaklar:",
        "\n**Kaynaklar:**",
    ):

        if marker in value:

            value = value.split(
                marker,
                1,
            )[0]

    value = re.sub(
        r"\[E\d+\]",
        "",
        value,
    )

    value = re.sub(
        r"[ \t]+",
        " ",
        value,
    )

    value = re.sub(
        r"\n{3,}",
        "\n\n",
        value,
    )

    return value.strip()


def _unique_evidence(
    context,
):

    result = []

    seen = set()

    for evidence in context.evidence:

        key = (
            str(
                evidence.bank_name
            ),
            str(
                evidence.document_title
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            evidence
        )

    return tuple(
        result
    )


def _maturity_fact_plan(
    context,
) -> list[str]:

    facts = []

    seen = set()

    for evidence in context.evidence:

        structured = (
            evidence.structured_fields
            or {}
        )

        maturity = structured.get(
            "maximum_maturity_months"
        )

        if maturity in {
            None,
            "",
        }:
            continue

        try:

            numeric = float(
                maturity
            )

            if numeric.is_integer():
                maturity_text = str(
                    int(
                        numeric
                    )
                )
            else:
                maturity_text = str(
                    numeric
                )

        except Exception:

            maturity_text = str(
                maturity
            )

        key = (
            evidence.bank_name,
            evidence.document_title,
            maturity_text,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        facts.append(
            (
                "Banka: "
                + evidence.bank_name
                + " | Urun: "
                + evidence.document_title
                + " | Azami vade: "
                + maturity_text
                + " ay."
            )
        )

    return facts


def _fallback_fact_plan(
    context,
    fallback_text: str,
) -> list[str]:

    clean = _clean_fallback(
        fallback_text
    )

    if not clean:
        return []

    lines = []

    for raw in clean.splitlines():

        line = raw.strip()

        line = re.sub(
            r"^[\-*]+\s*",
            "",
            line,
        ).strip()

        if not line:
            continue

        lines.append(
            line
        )

    if not lines:

        lines = [
            clean
        ]

    return lines[:8]


def _load_finance_rules_for_answer(
    raw,
) -> dict:

    if isinstance(
        raw,
        dict,
    ):
        obj = raw

    else:

        try:

            obj = json.loads(
                str(
                    raw
                    or "{}"
                )
            )

        except Exception:

            return {}

    if not isinstance(
        obj,
        dict,
    ):
        return {}

    return obj


def _canonical_fee_type(
    row: dict,
) -> str:

    fee_type = str(
        row.get(
            "fee_type"
        )
        or ""
    ).strip().casefold()

    if fee_type:
        return fee_type

    label = _normalize(
        row.get(
            "fee_label"
        )
        or row.get(
            "label"
        )
        or ""
    )

    if "tahsis" in label:
        return "allocation"

    if "ekspertiz" in label:
        return "appraisal"

    if (
        "ipotek" in label
        or "rehin" in label
    ):
        return "mortgage_establishment"

    if "komisyon" in label:
        return "commission"

    if "sigorta" in label:
        return "insurance"

    return ""


def _requested_fee_types(
    question: str,
):

    text = _normalize(
        question
    )

    if "tahsis" in text:
        return {
            "allocation",
        }

    if "ekspertiz" in text:
        return {
            "appraisal",
            "expertise",
        }

    if (
        "ipotek" in text
        or "rehin" in text
    ):
        return {
            "mortgage",
            "mortgage_establishment",
        }

    if "komisyon" in text:
        return {
            "commission",
        }

    if "sigorta" in text:
        return {
            "insurance",
        }

    return None


def _format_fee_rate(
    value,
) -> str | None:

    if value in {
        None,
        "",
    }:
        return None

    try:

        numeric = float(
            str(
                value
            ).replace(
                ",",
                ".",
            )
        )

    except Exception:

        return None

    # BANSA fee rate semanti?i y?zde puan?d?r.
    #
    # rate=0.5  -> %0,50
    # rate=0.75 -> %0,75
    #
    # Burada 100 ile ?ARPILMAZ.
    raw = (
        f"{numeric:.4f}"
        .rstrip(
            "0"
        )
        .rstrip(
            "."
        )
    )

    if "." in raw:

        whole, fraction = (
            raw.split(
                ".",
                1,
            )
        )

        fraction = (
            fraction.ljust(
                2,
                "0",
            )
        )

        raw = (
            whole
            + ","
            + fraction
        )

    else:

        raw = (
            raw
            + ",00"
        )

    return (
        "%"
        + raw
    )


def _format_fee_amount(
    value,
) -> str | None:

    if value in {
        None,
        "",
    }:
        return None

    try:

        numeric = float(
            str(
                value
            ).replace(
                ",",
                ".",
            )
        )

    except Exception:

        return None

    if numeric.is_integer():

        return (
            f"{int(numeric):,}"
            .replace(
                ",",
                ".",
            )
            + " TL"
        )

    formatted = (
        f"{numeric:,.2f}"
        .replace(
            ",",
            "_",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "_",
            ".",
        )
    )

    return (
        formatted
        + " TL"
    )


def _clean_fee_note(
    value,
) -> str:

    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ""

    # Kaynak URL'si answer fact'ine ta??nmaz.
    text = re.split(
        r"\bKaynak\s*:",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    return text


def _canonical_fee_rows(
    context,
) -> list[dict]:

    requested = (
        _requested_fee_types(
            context.question
        )
    )

    rows = []

    seen = set()

    for evidence in context.evidence:

        structured = (
            evidence.structured_fields
            or {}
        )

        if not isinstance(
            structured,
            dict,
        ):
            continue

        rules = (
            _load_finance_rules_for_answer(
                structured.get(
                    "finance_rules_json"
                )
            )
        )

        fee_rules = (
            rules.get(
                "fee_rules"
            )
        )

        if not isinstance(
            fee_rules,
            list,
        ):
            fee_rules = []

        # Future-compatible:
        # E?er structured payload do?rudan fee_rules ta??rsa
        # onu da okuyabiliriz; canonical veriyi hi?bir yere
        # kopyalam?yoruz, sadece mevcut payload'? okuyoruz.
        direct_fee_rules = (
            structured.get(
                "fee_rules"
            )
        )

        if isinstance(
            direct_fee_rules,
            list,
        ):

            fee_rules = (
                fee_rules
                + direct_fee_rules
            )

        for raw_row in fee_rules:

            if not isinstance(
                raw_row,
                dict,
            ):
                continue

            fee_type = (
                _canonical_fee_type(
                    raw_row
                )
            )

            if (
                requested
                and fee_type
                not in requested
            ):
                continue

            label = str(
                raw_row.get(
                    "fee_label"
                )
                or raw_row.get(
                    "label"
                )
                or fee_type
                or "?cret"
            ).strip()

            rate = raw_row.get(
                "rate"
            )

            amount = raw_row.get(
                "amount"
            )

            waived = raw_row.get(
                "waived"
            )

            note = _clean_fee_note(
                raw_row.get(
                    "note"
                )
            )

            bank = str(
                evidence.bank_name
                or ""
            ).strip()

            product = str(
                evidence.document_title
                or ""
            ).strip()

            identity = (
                bank,
                product,
                fee_type,
                label,
                str(
                    rate
                ),
                str(
                    amount
                ),
                str(
                    waived
                ),
                note,
            )

            if identity in seen:
                continue

            seen.add(
                identity
            )

            rows.append(
                {
                    "bank":
                        bank,
                    "product":
                        product,
                    "fee_type":
                        fee_type,
                    "label":
                        label,
                    "rate":
                        rate,
                    "amount":
                        amount,
                    "waived":
                        waived,
                    "note":
                        note,
                }
            )

    return rows


def _fee_fact_plan(
    context,
) -> list[str]:

    # =========================================================
    # 1. CANONICAL finance_rules_json > fee_rules
    # =========================================================

    canonical_rows = (
        _canonical_fee_rows(
            context
        )
    )

    canonical_facts = []

    for row in canonical_rows:

        parts = []

        rate_text = (
            _format_fee_rate(
                row.get(
                    "rate"
                )
            )
        )

        amount_text = (
            _format_fee_amount(
                row.get(
                    "amount"
                )
            )
        )

        if rate_text:

            parts.append(
                "Oran: "
                + rate_text
            )

        if amount_text:

            parts.append(
                "Tutar: "
                + amount_text
            )

        waived = row.get(
            "waived"
        )

        if (
            waived is True
        ):

            parts.append(
                "Muafiyet: var"
            )

        elif (
            waived is False
            and not rate_text
            and not amount_text
        ):

            parts.append(
                "Muafiyet: yok"
            )

        note = str(
            row.get(
                "note"
            )
            or ""
        ).strip()

        # A??klama sadece rakamsal bilgi yoksa
        # fact'e eklenir. B?ylece ayn? %0,50
        # hem rate hem note i?inden iki kez ?retilmez.
        if (
            not rate_text
            and not amount_text
            and note
        ):

            parts.append(
                "A??klama: "
                + note
            )

        if not parts:
            continue

        canonical_facts.append(
            (
                "Banka: "
                + str(
                    row.get(
                        "bank"
                    )
                    or ""
                )
                + " | Urun: "
                + str(
                    row.get(
                        "product"
                    )
                    or ""
                )
                + " | Ucret: "
                + str(
                    row.get(
                        "label"
                    )
                    or "?cret"
                )
                + " | "
                + " | ".join(
                    parts
                )
                + "."
            )
        )

    if canonical_facts:

        return canonical_facts

    # =========================================================
    # 2. LEGACY FLAT STRUCTURED FIELDS
    #
    # finance_rules_json bulunmayan eski ?r?nlerin davran???
    # korunur.
    # =========================================================

    facts = []

    identities = []

    waived_values = {
        "allocation_fee_waived":
            set(),
        "commission_fee_waived":
            set(),
        "insurance_fee_waived":
            set(),
    }

    amount_keys = (
        "allocation_fee_amount",
        "commission_fee_amount",
        "insurance_fee_amount",
        "expertise_fee_amount",
        "mortgage_fee_amount",
        "total_fee_amount",
    )

    explicit_amounts = []

    for evidence in context.evidence:

        identity = (
            str(
                evidence.bank_name
                or ""
            ).strip(),
            str(
                evidence.document_title
                or ""
            ).strip(),
        )

        if identity not in identities:

            identities.append(
                identity
            )

        structured = (
            evidence.structured_fields
            or {}
        )

        for key in waived_values:

            if key in structured:

                value = (
                    structured.get(
                        key
                    )
                )

                if isinstance(
                    value,
                    bool,
                ):

                    waived_values[
                        key
                    ].add(
                        value
                    )

        for key in amount_keys:

            value = (
                structured.get(
                    key
                )
            )

            if value not in {
                None,
                "",
            }:

                explicit_amounts.append(
                    (
                        key,
                        value,
                    )
                )

    if identities:

        bank, product = (
            identities[0]
        )

        if bank or product:

            facts.append(
                (
                    "Banka: "
                    + bank
                    + " | Urun: "
                    + product
                    + "."
                )
            )

    if explicit_amounts:

        for key, value in explicit_amounts:

            facts.append(
                (
                    "Dogrulanmis ucret alani: "
                    + key
                    + " = "
                    + str(
                        value
                    )
                    + "."
                )
            )

    else:

        facts.append(
            (
                "Net masraf tutari: "
                "dogrulanmis structured veride "
                "belirtilmemis."
            )
        )

    labels = {
        "allocation_fee_waived":
            "Tahsis ucreti muafiyeti",
        "commission_fee_waived":
            "Komisyon ucreti muafiyeti",
        "insurance_fee_waived":
            "Sigorta ucreti muafiyeti",
    }

    for key, label in labels.items():

        values = (
            waived_values[
                key
            ]
        )

        if values == {
            True
        }:

            facts.append(
                label
                + ": muaf olarak isaretlenmis."
            )

        elif values == {
            False
        }:

            facts.append(
                label
                + ": muaf olarak isaretlenmemis."
            )

    return facts





def build_fact_plan(
    context,
    fallback_text: str,
) -> tuple[str, ...]:

    attribute = _detect_attribute(
        context.question
    )

    if attribute == "maturity":

        maturity = _maturity_fact_plan(
            context
        )

        if maturity:

            return tuple(
                maturity
            )


    if attribute == "fee":

        fee_facts = _fee_fact_plan(
            context
        )

        if fee_facts:

            return tuple(
                fee_facts
            )


    return tuple(
        _fallback_fact_plan(
            context,
            fallback_text,
        )
    )


def _load_model():

    global _MODEL
    global _TOKENIZER
    global _DEVICE

    if (
        _MODEL is not None
        and
        _TOKENIZER is not None
    ):
        return (
            _TOKENIZER,
            _MODEL,
            _DEVICE,
        )

    import torch

    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
    )

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    tokenizer = (
        AutoTokenizer.from_pretrained(
            MODEL_ID,
            local_files_only=True,
        )
    )

    kwargs = {
        "local_files_only":
            True,
    }

    if device == "cuda":

        kwargs[
            "dtype"
        ] = torch.float16

    model = (
        AutoModelForCausalLM
        .from_pretrained(
            MODEL_ID,
            **kwargs,
        )
    )

    model.to(
        device
    )

    model.eval()

    _TOKENIZER = tokenizer
    _MODEL = model
    _DEVICE = device

    return (
        tokenizer,
        model,
        device,
    )


def _build_prompt(
    *,
    question: str,
    facts: tuple[str, ...],
) -> str:

    fact_text = "\n".join(
        (
            "FACT "
            + str(index)
            + ": "
            + fact
        )
        for index, fact
        in enumerate(
            facts,
            start=1,
        )
    )

    return (
        "KULLANICI SORUSU:\n"
        + question
        + "\n\n"
        + "DOGRULANMIS GERCEKLER:\n"
        + fact_text
        + "\n\n"
        + "GOREV:\n"
        + "Kullanicinin sorusuna dogal, akici ve "
          "kisa Turkce ile cevap ver.\n"
        + "Yalnizca DOGRULANMIS GERCEKLER bolumundeki "
          "bilgileri kullan.\n"
        + "Yeni banka, urun, rakam, tarih, oran, ucret "
          "veya kosul ekleme.\n"
        + "Farkli FACT satirlarini yeni bir neden-sonuc "
          "veya yeni bir kosul kuracak sekilde birlestirme.\n"
        + "Rakamlarin anlamini degistirme.\n"
        + "Sayisal araliklari birlestirme, kisaltma veya "
          "yeni bir aralik olusturma.\n"
        + "Ornegin bir FACT 5.000-19.999 icin 400, "
          "20.000-49.999 icin 1.000 diyorsa bu "
          "eslesmeleri aynen koru.\n"
        + "Bir tutarin hangi kosula veya odul miktarina "
          "bagli oldugunu degistirme.\n"
        + "Kaynakta 'azami' veya 'kadar' deniyorsa bunu "
          "kesin sabit vade gibi ifade etme.\n"
        + "'Dogrulanmis urun', 'evidence', 'FACT', "
          "'RAG' gibi teknik ifadeler kullanma.\n"
        + "Kullaniciya dogrudan cevap ver.\n"
        + "Tarafsiz bir finans asistani gibi konus.\n"
        + "Bankanin web sitesindeki birinci cogul dili "
          "aynen kopyalama.\n"
        + "Ornegin 'finansmanimizdan faydalanabilirsiniz' "
          "yerine 'bu finansmandan yararlanabilirsiniz' yaz.\n"
        + "Bir urunu insan gibi ozne yapma.\n"
        + "Ornegin 'Egitim Finansmani masraflarinizi "
          "odeyebilir' yazma; 'Egitim Finansmani, "
          "masraflari taksitlendirme imkani sunuyor' yaz.\n"
        + "Banka adini ayni cumlede gereksiz yere "
          "tekrar etme.\n"
        + "Kaynak metni kelimesi kelimesine kopyalamak "
          "yerine anlami koruyarak dogal Turkce kullan.\n"
        + "Gereksiz giris yapma.\n"
        + "Cevabi 1-4 cumleyle sinirla.\n"
        + "Sadece cevabi yaz."
    )


def _build_strict_retry_prompt(
    *,
    question: str,
    facts: tuple[str, ...],
) -> str:

    fact_text = "\n".join(
        (
            "["
            + str(index)
            + "] "
            + fact
        )
        for index, fact
        in enumerate(
            facts,
            start=1,
        )
    )

    return (
        "SORU:\n"
        + question
        + "\n\n"
        + "IZIN VERILEN BILGILER:\n"
        + fact_text
        + "\n\n"
        + "Yalnizca yukaridaki bilgilerden cevap yaz.\n"
        + "Baska bir banka, kampanya veya urun hakkinda "
          "hicbir bilgi kullanma.\n"
        + "Yukarida bulunmayan hicbir sayiyi yazma.\n"
        + "Sayilari farkli kosullarla birlestirme.\n"
        + "Yeni bir tarih, oran, ucret, limit veya "
          "vade uretme.\n"
        + "Bilgilerde olmayan bir kosulu ekleme.\n"
        + "Kullaniciya dogrudan ve dogal Turkce ile "
          "cevap ver.\n"
        + "Tarafsiz bir finans asistani gibi konus.\n"
        + "Bankanin 'biz, bankamiz, musterilerimiz, "
          "finansmanimiz' dilini kullanma.\n"
        + "Urunu insan gibi konusturma veya insan gibi "
          "eylem yapan ozne haline getirme.\n"
        + "Urun icin 'imkan sunuyor', 'kapsiyor', "
          "'vadesi bulunuyor' gibi tarafsiz yapilar kullan.\n"
        + "Banka adini ayni cumlede birden fazla kez "
          "tekrar etme.\n"
        + "Teknik ifadeler, FACT, evidence, RAG, "
          "dogrulanmis urun gibi ifadeler kullanma.\n"
        + "En fazla 3 kisa cumle yaz.\n"
        + "Sadece cevabi yaz."
    )


def _generate(
    *,
    question: str,
    facts: tuple[str, ...],
    strict_retry: bool = False,
) -> str:

    tokenizer, model, device = (
        _load_model()
    )

    import torch

    if strict_retry:

        user_prompt = (
            _build_strict_retry_prompt(
                question=question,
                facts=facts,
            )
        )

    else:

        user_prompt = _build_prompt(
            question=question,
            facts=facts,
        )

    messages = [
        {
            "role": "system",
            "content": (
                "Sen BANSA'nin kontrollu "
                "cevap yazma katmanisin. "
                "Sana verilen dogrulanmis "
                "gerceklerin disina cikamazsin."
            ),
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    try:

        prompt = (
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        )

    except TypeError:

        prompt = (
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
    )

    inputs = {
        key:
            value.to(
                device
            )
        for key, value
        in inputs.items()
    }

    with torch.inference_mode():

        output = model.generate(
            **inputs,
            max_new_tokens=240,
            do_sample=False,
            repetition_penalty=1.03,
            pad_token_id=(
                tokenizer.eos_token_id
            ),
        )

    generated = output[
        0,
        inputs[
            "input_ids"
        ].shape[1]:
    ]

    text = tokenizer.decode(
        generated,
        skip_special_tokens=True,
    ).strip()

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=(
            re.I
            | re.S
        ),
    ).strip()

    text = re.sub(
        (
            r"^\s*"
            r"(?:\*{1,2})?\s*"
            r"(?:cevabi?|answer)"
            r"\s*:\s*"
            r"(?:\*{1,2})?\s*"
        ),
        "",
        text,
        flags=re.I,
    )


    return text.strip()


def _canonical_number(
    raw: str,
) -> str:

    value = str(
        raw
        or ""
    ).strip()

    if not value:
        return ""

    if (
        "."
        in value
        and
        ","
        in value
    ):

        value = (
            value
            .replace(".", "")
            .replace(",", ".")
        )

    elif "." in value:

        parts = value.split(".")

        if (
            len(parts) > 1
            and
            all(
                len(part) == 3
                for part in parts[1:]
            )
        ):

            value = "".join(
                parts
            )

    elif "," in value:

        value = value.replace(
            ",",
            ".",
        )

    try:

        numeric = float(
            value
        )

        if numeric.is_integer():

            return str(
                int(
                    numeric
                )
            )

        return (
            f"{numeric:.8f}"
            .rstrip("0")
            .rstrip(".")
        )

    except Exception:

        return value


def _numeric_matches(
    value,
):

    pattern = (
        r"(?<!\d)"
        r"(?:"
        r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"
        r"|"
        r"\d+(?:[.,]\d+)?"
        r")"
        r"(?!\d)"
    )

    return tuple(
        match.group(0)
        for match in re.finditer(
            pattern,
            str(
                value
                or ""
            ),
        )
    )


def _number_tokens(
    value,
) -> set[str]:

    return {
        canonical
        for canonical in (
            _canonical_number(
                raw
            )
            for raw in _numeric_matches(
                value
            )
        )
        if canonical
    }


def _range_pairs(
    value,
) -> set[
    tuple[
        str,
        str,
    ]
]:

    text = str(
        value
        or ""
    )

    text = (
        text
        .replace(
            "\u2013",
            "-",
        )
        .replace(
            "\u2014",
            "-",
        )
    )

    number = (
        r"(?:"
        r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"
        r"|"
        r"\d+(?:[.,]\d+)?"
        r")"
    )

    pattern = (
        r"("
        + number
        + r")"
        r"\s*(?:TL\s*)?"
        r"(?:ile|-)"
        r"\s*("
        + number
        + r")"
        r"\s*(?:TL)?"
    )

    result = set()

    for match in re.finditer(
        pattern,
        text,
        flags=re.I,
    ):

        left = _canonical_number(
            match.group(1)
        )

        right = _canonical_number(
            match.group(2)
        )

        if left and right:

            result.add(
                (
                    left,
                    right,
                )
            )

    return result


def _tier_relations(
    value,
) -> set[
    tuple[
        str,
        str,
        str,
        str,
    ]
]:

    """
    Extract campaign-style numeric relations.

    Examples:

    5.000 TL ile 19.999 TL arasindaki
    harcamaya 400 TL

        ->
    ("between", "5000", "19999", "400")

    50.000 TL ve uzerindeki
    harcamaya 2.000 TL

        ->
    ("above", "50000", "", "2000")
    """

    text = _normalize(
        value
    )

    number = (
        r"(?:"
        r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"
        r"|"
        r"\d+(?:[.,]\d+)?"
        r")"
    )

    result = set()


    between_pattern = (
        r"("
        + number
        + r")"
        r"\s*tl\s*"
        r"(?:ile|-)"
        r"\s*("
        + number
        + r")"
        r"\s*tl\s*"
        r"aras[a-z]*"
        r".{0,160}?"
        r"("
        + number
        + r")"
        r"\s*tl"
    )


    for match in re.finditer(
        between_pattern,
        text,
        flags=re.I,
    ):

        low = _canonical_number(
            match.group(1)
        )

        high = _canonical_number(
            match.group(2)
        )

        reward = _canonical_number(
            match.group(3)
        )

        if (
            low
            and
            high
            and
            reward
        ):

            result.add(
                (
                    "between",
                    low,
                    high,
                    reward,
                )
            )


    above_pattern = (
        r"("
        + number
        + r")"
        r"\s*tl\s*"
        r"ve\s*uzer[a-z]*"
        r".{0,160}?"
        r"("
        + number
        + r")"
        r"\s*tl"
    )


    for match in re.finditer(
        above_pattern,
        text,
        flags=re.I,
    ):

        threshold = (
            _canonical_number(
                match.group(1)
            )
        )

        reward = (
            _canonical_number(
                match.group(2)
            )
        )

        if (
            threshold
            and
            reward
        ):

            result.add(
                (
                    "above",
                    threshold,
                    "",
                    reward,
                )
            )


    return result


def _has_complete_tail(
    value: str,
) -> bool:

    text = str(
        value
        or ""
    ).strip()

    text = re.sub(
        r"[\s*_`#>]+$",
        "",
        text,
    )

    if not text:
        return False

    return text[-1] in {
        ".",
        "!",
        "?",
        ":",
        ";",
        ")",
        "]",
        "}",
        "\u2026",
    }


def _allowed_banks(
    context,
) -> set[str]:

    return {
        _normalize(
            evidence.bank_name
        )
        for evidence
        in context.evidence
        if str(
            evidence.bank_name
            or ""
        ).strip()
    }


def _mentioned_known_banks(
    text,
) -> set[str]:

    normalized = _normalize(
        text
    )

    result = set()

    for canonical, aliases in (
        _BANK_ALIASES.items()
    ):

        for alias in aliases:

            alias_norm = _normalize(
                alias
            )

            if re.search(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        alias_norm
                    )
                    + r"(?![a-z0-9])"
                ),
                normalized,
            ):

                result.add(
                    canonical
                )

                break

    return result


def _allowed_products(
    context,
) -> set[str]:

    return {
        _normalize(
            evidence.document_title
        )
        for evidence
        in context.evidence
        if str(
            evidence.document_title
            or ""
        ).strip()
    }


def _product_contamination(
    text,
    context,
) -> tuple[str, ...]:

    normalized = _normalize(
        text
    )

    allowed = _allowed_products(
        context
    )

    violations = []

    for phrase in (
        _KNOWN_PRODUCT_PHRASES
    ):

        if phrase not in normalized:
            continue

        supported = any(
            (
                phrase in product
                or product in phrase
            )
            for product in allowed
        )

        if not supported:

            violations.append(
                phrase
            )

    return tuple(
        violations
    )


def _content_tokens(
    value,
) -> set[str]:

    stop = {
        "bir",
        "bu",
        "da",
        "de",
        "ile",
        "icin",
        "ve",
        "veya",
        "olarak",
        "olan",
        "kadar",
        "gibi",
        "daha",
        "ise",
        "icin",
        "size",
        "sizin",
    }

    return {
        token
        for token in _normalize(
            value
        ).split()
        if (
            len(token) >= 3
            and token not in stop
            and not re.fullmatch(
                r"\d+(?:[.,]\d+)?",
                token,
            )
        )
    }


def _semantic_surface_check(
    answer: str,
    facts: tuple[str, ...],
) -> bool:

    answer_tokens = _content_tokens(
        answer
    )

    fact_tokens = _content_tokens(
        " ".join(
            facts
        )
    )

    if not answer_tokens:
        return False

    overlap = len(
        answer_tokens
        & fact_tokens
    )

    ratio = (
        overlap
        / max(
            1,
            len(
                answer_tokens
            ),
        )
    )

    return ratio >= 0.18


def _neutralize_style(
    value: str,
) -> str:

    text = str(
        value
        or ""
    )

    replacements = (
        (
            "finansman\u0131m\u0131zdan",
            "bu finansmandan",
        ),
        (
            "Finansman\u0131m\u0131zdan",
            "Bu finansmandan",
        ),
        (
            "m\u00fc\u015fterilerimize",
            "m\u00fc\u015fterilere",
        ),
        (
            "M\u00fc\u015fterilerimize",
            "M\u00fc\u015fterilere",
        ),
        (
            "m\u00fc\u015fterilerimiz",
            "m\u00fc\u015fteriler",
        ),
        (
            "M\u00fc\u015fterilerimiz",
            "M\u00fc\u015fteriler",
        ),
        (
            "bankam\u0131zdaki",
            "bankadaki",
        ),
        (
            "Bankam\u0131zdaki",
            "Bankadaki",
        ),
        (
            "\u015fubelerimizden",
            "\u015fubelerden",
        ),
        (
            "\u015eubelerimizden",
            "\u015eubelerden",
        ),
        (
            "kartlar\u0131m\u0131z",
            "kartlar",
        ),
        (
            "Kartlar\u0131m\u0131z",
            "Kartlar",
        ),
        (
            "kampanyam\u0131z",
            "kampanya",
        ),
        (
            "Kampanyam\u0131z",
            "Kampanya",
        ),
        (
            "sa\u011fl\u0131yoruz",
            "sunuluyor",
        ),
        (
            "Sa\u011fl\u0131yoruz",
            "Sunuluyor",
        ),
        (
            "sunuyoruz",
            "sunuluyor",
        ),
        (
            "Sunuyoruz",
            "Sunuluyor",
        ),
    )

    for old, new in replacements:

        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r" +([,.!?;:])",
        r"\1",
        text,
    )

    return text.strip()


def _split_style_sentences(
    value: str,
) -> tuple[str, ...]:

    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ()

    pieces = re.split(
        r"(?<=[.!?])\s+|\n+",
        text,
    )

    return tuple(
        piece.strip()
        for piece in pieces
        if piece.strip()
    )


def _opening_sentence(
    value: str,
) -> str:

    sentences = (
        _split_style_sentences(
            value
        )
    )

    if not sentences:
        return ""

    return sentences[0]


def _style_reasons(
    *,
    context,
    answer: str,
) -> tuple[str, ...]:

    reasons = []

    normalized = _normalize(
        answer
    )

    institutional_voice = (
        "finansmanimizdan",
        "musterilerimiz",
        "musterilerimize",
        "bankamiz",
        "bankamizdaki",
        "subelerimiz",
        "kartlarimiz",
        "kampanyamiz",
        "urunlerimiz",
        "oranlarimiz",
    )

    if any(
        token in normalized
        for token in institutional_voice
    ):

        reasons.append(
            "institutional_first_person_voice"
        )


    # --------------------------------------------------------
    # PRODUCT-AS-HUMAN CHECK
    #
    # BAD:
    # "Egitim Finansmani, masraflarinizi odeyebilir."
    #
    # VALID:
    # "Egitim Finansmani ile masraflarinizi
    #  taksitlendirerek odeyebilirsiniz."
    #
    # The second sentence has an implicit user subject.
    # --------------------------------------------------------

    personal_verbs = (
        "odeyebilir",
        "faydalanabilir",
        "yararlanabilir",
        "sahip olabilir",
    )

    safe_connectors = (
        "ile",
        "sayesinde",
        "kapsaminda",
        "hakkinda",
        "icin",
        "uzerinden",
    )

    allowed_products = (
        _allowed_products(
            context
        )
    )

    sentences = (
        _split_style_sentences(
            answer
        )
    )

    for sentence in sentences:

        sentence_norm = _normalize(
            sentence
        )

        for product in allowed_products:

            if not product:
                continue

            position = sentence_norm.find(
                product
            )

            if position < 0:
                continue

            tail = sentence_norm[
                position
                + len(product):
            ].strip(
                " ,:-"
            )

            first_word = (
                tail.split(
                    " ",
                    1,
                )[0]
                if tail
                else ""
            )

            if first_word in safe_connectors:
                continue

            if any(
                verb in tail
                for verb in personal_verbs
            ):

                reasons.append(
                    "product_as_human_actor"
                )

                break

        if (
            "product_as_human_actor"
            in reasons
        ):
            break


    # --------------------------------------------------------
    # DUPLICATE BANK ONLY IN OPENING SENTENCE
    # --------------------------------------------------------

    opening_normalized = (
        _normalize(
            _opening_sentence(
                answer
            )
        )
    )

    for evidence in context.evidence:

        bank = _normalize(
            evidence.bank_name
        )

        if not bank:
            continue

        aliases = []

        for canonical, values in (
            _BANK_ALIASES.items()
        ):

            if (
                _normalize(
                    canonical
                )
                == bank
            ):

                aliases.extend(
                    _normalize(
                        value
                    )
                    for value in values
                )

        if not aliases:

            aliases = [
                bank
            ]

        shortest = min(
            aliases,
            key=len,
        )

        occurrences = len(
            re.findall(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        shortest
                    )
                    + r"(?![a-z0-9])"
                ),
                opening_normalized,
            )
        )

        if occurrences > 1:

            reasons.append(
                "duplicate_bank_in_opening"
            )

            break


    return tuple(
        reasons
    )


def verify_natural_answer(
    *,
    context,
    facts: tuple[str, ...],
    answer: str,
) -> tuple[
    bool,
    tuple[str, ...],
]:

    reasons = []

    value = str(
        answer
        or ""
    ).strip()

    if not value:

        return (
            False,
            (
                "empty_generation",
            ),
        )

    if len(value) > 1600:

        reasons.append(
            "answer_too_long"
        )

    low = _normalize(
        value
    )

    if any(
        forbidden in low
        for forbidden in (
            "dogrulanmis gercekler",
            "fact 1",
            "evidence",
            "rag ",
            "system prompt",
        )
    ):

        reasons.append(
            "prompt_leak"
        )


    instruction_leaks = (
        "birinci cogul",
        "tarafsiz bir finans asistani",
        "kaynak metni kelimesi kelimesine",
        "urunu insan gibi",
        "banka adini ayni cumlede",
        "kullaniciya dogrudan cevap ver",
        "teknik ifadeler kullanma",
        "dogrulanmis gerceklerin disina",
        "yalnizca yukaridaki bilgilerden",
        "izin verilen bilgiler",
    )

    if any(
        phrase in low
        for phrase in instruction_leaks
    ):

        reasons.append(
            "prompt_instruction_leak"
        )

    supported_numbers = (
        _number_tokens(
            " ".join(
                facts
            )
        )
    )

    generated_numbers = (
        _number_tokens(
            value
        )
    )

    unsupported_numbers = (
        generated_numbers
        - supported_numbers
    )

    if unsupported_numbers:

        reasons.append(
            (
                "unsupported_numbers:"
                + ",".join(
                    sorted(
                        unsupported_numbers
                    )
                )
            )
        )


    # --------------------------------------------------------
    # NUMERIC RELATION CHECK
    #
    # Supported-number checking alone is insufficient:
    #
    # FACT:
    #   5.000-19.999 -> 400
    #   20.000-49.999 -> 1.000
    #
    # must never become:
    #   2.000-50.000 -> 400-2.000
    #
    # Every explicit range created by the model must already
    # exist as an explicit range in the grounded facts.
    # --------------------------------------------------------

    supported_range_pairs = set()

    for fact in facts:

        supported_range_pairs.update(
            _range_pairs(
                fact
            )
        )


    generated_range_pairs = (
        _range_pairs(
            value
        )
    )


    unsupported_range_pairs = (
        generated_range_pairs
        - supported_range_pairs
    )


    if unsupported_range_pairs:

        formatted = ",".join(
            (
                left
                + "-"
                + right
            )
            for left, right
            in sorted(
                unsupported_range_pairs
            )
        )

        reasons.append(
            (
                "unsupported_numeric_relations:"
                + formatted
            )
        )


    # A response cut in the middle of a sentence must never
    # be accepted as a verified natural answer.

    if not _has_complete_tail(
        value
    ):

        reasons.append(
            "incomplete_generation_tail"
        )

    # --------------------------------------------------------
    # CAMPAIGN TIER RELATION CHECK
    #
    # It is not enough for each number to exist somewhere
    # in the evidence. The relationship between spending
    # range and reward must also be preserved.
    # --------------------------------------------------------

    supported_tiers = set()

    for fact in facts:

        supported_tiers.update(
            _tier_relations(
                fact
            )
        )


    generated_tiers = (
        _tier_relations(
            value
        )
    )


    unsupported_tiers = (
        generated_tiers
        - supported_tiers
    )


    if unsupported_tiers:

        formatted = ";".join(
            ":".join(
                relation
            )
            for relation
            in sorted(
                unsupported_tiers
            )
        )

        reasons.append(
            (
                "unsupported_tier_relations:"
                + formatted
            )
        )


    allowed_banks = (
        _allowed_banks(
            context
        )
    )

    mentioned_banks = (
        _mentioned_known_banks(
            value
        )
    )

    unsupported_banks = {
        bank
        for bank in mentioned_banks
        if _normalize(
            bank
        )
        not in allowed_banks
    }

    if unsupported_banks:

        reasons.append(
            (
                "unsupported_banks:"
                + ",".join(
                    sorted(
                        unsupported_banks
                    )
                )
            )
        )

    wrong_products = (
        _product_contamination(
            value,
            context,
        )
    )

    if wrong_products:

        reasons.append(
            (
                "unsupported_products:"
                + ",".join(
                    wrong_products
                )
            )
        )

    if not _semantic_surface_check(
        value,
        facts,
    ):

        reasons.append(
            "insufficient_fact_overlap"
        )


    reasons.extend(
        _style_reasons(
            context=context,
            answer=value,
        )
    )

    attribute = _detect_attribute(
        context.question
    )


    hard_fact_attributes = {
        "maturity",
        "rate",
        "fee",
        "date",
        "limit",
    }


    if (
        attribute
        in hard_fact_attributes
    ):

        answer_sentences = (
            _split_style_sentences(
                value
            )
        )

        if len(
            answer_sentences
        ) > 1:

            reasons.append(
                "hard_attribute_extra_content"
            )

    if attribute == "maturity":

        expected = set()

        for evidence in context.evidence:

            structured = (
                evidence.structured_fields
                or {}
            )

            maturity = structured.get(
                "maximum_maturity_months"
            )

            if maturity in {
                None,
                "",
            }:
                continue

            try:

                numeric = float(
                    maturity
                )

                if numeric.is_integer():

                    expected.add(
                        str(
                            int(
                                numeric
                            )
                        )
                    )

            except Exception:
                pass

        if (
            expected
            and
            not (
                generated_numbers
                & expected
            )
        ):

            reasons.append(
                "requested_maturity_missing"
            )


        if (
            expected
            and
            (
                generated_numbers
                & expected
            )
            and
            not any(
                qualifier in low
                for qualifier in (
                    "azami",
                    "maksimum",
                    "en fazla",
                    "aya kadar",
                )
            )
        ):

            reasons.append(
                "maximum_maturity_qualifier_missing"
            )

    return (
        not reasons,
        tuple(
            reasons
        ),
    )


def _first_identity(
    context,
):

    if not context.evidence:

        return (
            "",
            "",
        )

    first = context.evidence[0]

    return (
        str(
            first.bank_name
            or ""
        ).strip(),
        str(
            first.document_title
            or ""
        ).strip(),
    )


def _safe_maturity_answer(
    context,
) -> str | None:

    bank, product = (
        _first_identity(
            context
        )
    )

    maturities = []

    for evidence in context.evidence:

        structured = (
            evidence.structured_fields
            or {}
        )

        value = structured.get(
            "maximum_maturity_months"
        )

        if value in {
            None,
            "",
        }:
            continue

        try:

            numeric = float(
                value
            )

            value = (
                str(
                    int(
                        numeric
                    )
                )
                if numeric.is_integer()
                else str(
                    numeric
                )
            )

        except Exception:

            value = str(
                value
            )

        if value not in maturities:

            maturities.append(
                value
            )

    if len(
        maturities
    ) != 1:

        return None

    if not bank or not product:

        return None

    return (
        bank
        + " "
        + product
        + " i\u00e7in azami vade "
        + maturities[0]
        + " aya kadard\u0131r."
    )


def _safe_fee_answer(
    context,
) -> str | None:

    bank, product = (
        _first_identity(
            context
        )
    )

    if not bank or not product:
        return None

    # =========================================================
    # 1. CANONICAL finance_rules_json > fee_rules
    # =========================================================

    requested = (
        _requested_fee_types(
            context.question
        )
    )

    canonical_rows = (
        _canonical_fee_rows(
            context
        )
    )

    # Deterministic safe fallback ?zellikle tek bir ?cret
    # t?r? soruldu?unda kullan?labilir.
    #
    # ?rn:
    # "Tahsis ?creti ne kadar?"
    #
    # Generic "masraflar neler?" sorusunda normal grounded
    # generation birden fazla fee_rule'u do?al bi?imde
    # birle?tirsin.
    if (
        requested
        and canonical_rows
    ):

        row = canonical_rows[0]

        label = str(
            row.get(
                "label"
            )
            or "?cret"
        ).strip()

        rate_text = (
            _format_fee_rate(
                row.get(
                    "rate"
                )
            )
        )

        amount_text = (
            _format_fee_amount(
                row.get(
                    "amount"
                )
            )
        )

        if rate_text:

            return (
                bank
                + " "
                + product
                + " i\u00e7in "
                + label
                + " "
                + rate_text
                + " olarak belirtiliyor."
            )

        if amount_text:

            return (
                bank
                + " "
                + product
                + " i\u00e7in "
                + label
                + " "
                + amount_text
                + " olarak belirtiliyor."
            )

        if (
            row.get(
                "waived"
            )
            is True
        ):

            return (
                bank
                + " "
                + product
                + " i\u00e7in "
                + label
                + " muaf olarak belirtiliyor."
            )

        note = str(
            row.get(
                "note"
            )
            or ""
        ).strip()

        if note:

            return (
                bank
                + " "
                + product
                + " i\u00e7in "
                + label
                + ": "
                + note
            )

    # =========================================================
    # 2. LEGACY FLAT STRUCTURED FALLBACK
    # =========================================================

    flags = {
        "allocation_fee_waived":
            set(),
        "commission_fee_waived":
            set(),
        "insurance_fee_waived":
            set(),
    }

    amount_keys = {
        "allocation_fee_amount",
        "commission_fee_amount",
        "insurance_fee_amount",
        "expertise_fee_amount",
        "mortgage_fee_amount",
        "total_fee_amount",
    }

    explicit_amount_found = False

    for evidence in context.evidence:

        structured = (
            evidence.structured_fields
            or {}
        )

        for key in amount_keys:

            if structured.get(
                key
            ) not in {
                None,
                "",
            }:

                explicit_amount_found = True

        for key in flags:

            value = (
                structured.get(
                    key
                )
            )

            if isinstance(
                value,
                bool,
            ):

                flags[
                    key
                ].add(
                    value
                )

    if explicit_amount_found:

        return None

    labels = []

    label_map = {
        "allocation_fee_waived":
            "tahsis",
        "commission_fee_waived":
            "komisyon",
        "insurance_fee_waived":
            "sigorta",
    }

    for key, label in label_map.items():

        if flags[
            key
        ] == {
            False
        }:

            labels.append(
                label
            )

    base = (
        bank
        + " "
        + product
        + " i\u00e7in do\u011frulanm\u0131\u015f "
          "veride net bir masraf tutar\u0131 "
          "yer alm?yor"
    )

    if labels:

        if len(
            labels
        ) == 1:

            detail = labels[0]

        elif len(
            labels
        ) == 2:

            detail = (
                labels[0]
                + " ve "
                + labels[1]
            )

        else:

            detail = (
                ", ".join(
                    labels[:-1]
                )
                + " ve "
                + labels[-1]
            )

        return (
            base
            + "; "
            + detail
            + " \u00fccretleri muaf olarak "
              "i\u015faretlenmemi\u015f, bu nedenle "
              "kesin bir tutar vermiyorum."
        )

    return (
        base
        + "; bu nedenle kesin bir "
          "tutar vermiyorum."
    )





def _is_navigation_noise(
    line: str,
) -> bool:

    normalized = _normalize(
        line
    )

    if not normalized:

        return True


    if normalized.startswith(
        "hemen basvur"
    ):

        return True


    if (
        "basvurusu hangi kanallari kullanabilirsiniz"
        in normalized
    ):

        return True


    if (
        "hangi kanallari kullanabilirsiniz"
        in normalized
    ):

        return True


    return False


def _clean_fallback_content_line(
    line: str,
    attribute: str | None,
) -> str:

    value = str(
        line
        or ""
    ).strip()


    if _is_navigation_noise(
        value
    ):

        return ""


    if (
        attribute
        == "benefits"
        and
        ":"
        in value
    ):

        prefix, remainder = (
            value.split(
                ":",
                1,
            )
        )

        prefix_norm = _normalize(
            prefix
        )

        if (
            "avantaj"
            in prefix_norm
            and
            len(
                remainder.strip()
            ) >= 15
        ):

            value = remainder.strip()


    return value


def build_safe_natural_fallback(
    *,
    context,
    fallback_text: str,
) -> str:

    attribute = _detect_attribute(
        context.question
    )

    if attribute == "maturity":

        maturity_answer = (
            _safe_maturity_answer(
                context
            )
        )

        if maturity_answer:

            return maturity_answer


    if attribute == "fee":

        fee_answer = (
            _safe_fee_answer(
                context
            )
        )

        if fee_answer:

            return fee_answer

    clean = _clean_fallback(
        fallback_text
    )

    bank, title = (
        _first_identity(
            context
        )
    )

    lines = []

    for raw in clean.splitlines():

        line = raw.strip()

        if not line:
            continue

        normalized = _normalize(
            line
        )

        if normalized.startswith(
            "dogrulanmis urun"
        ):

            continue

        if normalized.startswith(
            "dogrulanmis kampanya"
        ):

            continue

        line = re.sub(
            r"^[\-*]+\s*",
            "",
            line,
        ).strip()

        if not line:
            continue

        line = (
            _clean_fallback_content_line(
                line,
                attribute,
            )
        )

        if not line:
            continue

        lines.append(
            line
        )

    # Deduplicate while preserving order.

    unique = []

    seen = set()

    for line in lines:

        key = _normalize(
            line
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            line
        )

    if not unique:

        return clean

    if context.route == "campaign_rag":

        if bank and title:

            intro = (
                bank
                + " taraf\u0131nda \""
                + title
                + "\" kampanyas\u0131 bulunuyor."
            )

        elif title:

            intro = (
                "\""
                + title
                + "\" kampanyas\u0131 bulunuyor."
            )

        else:

            intro = (
                "Kampanyayla ilgili \u00f6ne "
                "\u00e7\u0131kan bilgiler \u015f\u00f6yle:"
            )

    elif context.route == "product_rag":

        if bank and title:

            intro = (
                bank
                + " "
                + title
                + " hakk\u0131nda \u00f6ne "
                "\u00e7\u0131kan bilgiler \u015f\u00f6yle:"
            )

        elif title:

            intro = (
                title
                + " hakk\u0131nda \u00f6ne "
                "\u00e7\u0131kan bilgiler \u015f\u00f6yle:"
            )

        else:

            intro = (
                "\u00d6ne \u00e7\u0131kan bilgiler "
                "\u015f\u00f6yle:"
            )

    else:

        return clean

    if len(unique) == 1:

        return _neutralize_style(
            intro
            + "\n\n"
            + unique[0]
        )

    body = "\n".join(
        "- " + line
        for line in unique
    )

    return _neutralize_style(
        intro
        + "\n\n"
        + body
    )


def naturalize_grounded_answer(
    *,
    context,
    fallback_text: str,
) -> NaturalAnswerResult:

    fallback = (
        build_safe_natural_fallback(
            context=context,
            fallback_text=(
                fallback_text
            ),
        )
    )

    if (
        context.answer_mode
        != "rag"
    ):

        return NaturalAnswerResult(
            text=fallback,
            status=(
                "not_applicable"
            ),
            model_used=False,
            verified=True,
            fallback_used=True,
            reasons=(
                "rag_only_v1",
            ),
        )

    if not context.evidence:

        return NaturalAnswerResult(
            text=fallback,
            status=(
                "fallback"
            ),
            model_used=False,
            verified=True,
            fallback_used=True,
            reasons=(
                "no_grounded_evidence",
            ),
        )

    facts = build_fact_plan(
        context,
        fallback,
    )

    if not facts:

        return NaturalAnswerResult(
            text=fallback,
            status=(
                "fallback"
            ),
            model_used=False,
            verified=True,
            fallback_used=True,
            reasons=(
                "no_fact_plan",
            ),
        )

    try:

        draft = _generate(
            question=(
                context.question
            ),
            facts=facts,
        )

    except Exception as exc:

        return NaturalAnswerResult(
            text=fallback,
            status=(
                "fallback"
            ),
            model_used=False,
            verified=True,
            fallback_used=True,
            reasons=(
                (
                    "model_error:"
                    + type(
                        exc
                    ).__name__
                ),
            ),
        )

    verified, reasons = (
        verify_natural_answer(
            context=context,
            facts=facts,
            answer=draft,
        )
    )

    if not verified:

        first_reasons = reasons

        try:

            retry_draft = _generate(
                question=(
                    context.question
                ),
                facts=facts,
                strict_retry=True,
            )

            (
                retry_verified,
                retry_reasons,
            ) = verify_natural_answer(
                context=context,
                facts=facts,
                answer=retry_draft,
            )

        except Exception as exc:

            retry_draft = ""

            retry_verified = False

            retry_reasons = (
                (
                    "retry_model_error:"
                    + type(
                        exc
                    ).__name__
                ),
            )


        if retry_verified:

            polished_retry = (
                _neutralize_style(
                    retry_draft
                )
            )

            (
                polished_retry_ok,
                _,
            ) = verify_natural_answer(
                context=context,
                facts=facts,
                answer=polished_retry,
            )

            if polished_retry_ok:

                retry_draft = (
                    polished_retry
                )

            return NaturalAnswerResult(
                text=retry_draft,
                status=(
                    "pass_after_retry"
                ),
                model_used=True,
                verified=True,
                fallback_used=False,
                reasons=(
                    "strict_retry_verified",
                ),
            )


        combined_reasons = tuple(
            list(
                first_reasons
            )
            + [
                "strict_retry_failed"
            ]
            + list(
                retry_reasons
            )
        )


        (
            fallback_verified,
            fallback_verify_reasons,
        ) = verify_natural_answer(
            context=context,
            facts=facts,
            answer=fallback,
        )


        if not fallback_verified:

            return NaturalAnswerResult(
                text=fallback,
                status=(
                    "safe_fallback_verification_failed"
                ),
                model_used=True,
                verified=False,
                fallback_used=True,
                reasons=tuple(
                    list(
                        combined_reasons
                    )
                    + list(
                        fallback_verify_reasons
                    )
                ),
            )


        return NaturalAnswerResult(
            text=fallback,
            status=(
                "safe_natural_fallback"
            ),
            model_used=True,
            verified=True,
            fallback_used=True,
            reasons=(
                combined_reasons
            ),
        )

    polished = _neutralize_style(
        draft
    )

    polished_ok, polished_reasons = (
        verify_natural_answer(
            context=context,
            facts=facts,
            answer=polished,
        )
    )

    if polished_ok:

        draft = polished

    return NaturalAnswerResult(
        text=draft,
        status="pass",
        model_used=True,
        verified=True,
        fallback_used=False,
        reasons=(
            "grounded_generation_verified",
        ),
    )


# ============================================================
# BANSA_EVREN_FIRST_NATURALIZER_V1
#
# Generation provider order:
#
#   1. EVREN llm-fast
#   2. Existing local Qwen3-0.6B naturalizer
#   3. Existing extractive fallback
#
# Existing:
#   - fact planning
#   - prompt contract
#   - grounding verification
#   - numeric checks
#   - relation checks
#   - style checks
#
# are preserved.
#
# API credentials are read ONLY from environment variables.
# No API key is stored in source.
# ============================================================

import os as _evren_os_v1
import time as _evren_time_v1

import requests as _evren_requests_v1


_naturalize_grounded_answer_local_before_evren_v1 = (
    naturalize_grounded_answer
)


_EVREN_LAST_TRACE_V1 = {
    "provider":
        "not_called",

    "model":
        None,

    "latency_seconds":
        None,

    "first_verified":
        None,

    "retry_verified":
        None,

    "fallback":
        None,

    "reason":
        None,
}


def _evren_config_v1():

    key = str(
        _evren_os_v1.getenv(
            "EVREN_API_KEY",
            "",
        )
        or ""
    ).strip()

    base = str(
        _evren_os_v1.getenv(
            "EVREN_BASE_URL",
            "https://evren-llmapi.ssyz.org.tr/v1",
        )
        or ""
    ).strip().rstrip("/")

    model = str(
        _evren_os_v1.getenv(
            "EVREN_MODEL",
            "llm-fast",
        )
        or ""
    ).strip()

    timeout_raw = str(
        _evren_os_v1.getenv(
            "EVREN_TIMEOUT_SECONDS",
            "8",
        )
        or "8"
    ).strip()


    try:

        timeout = float(
            timeout_raw
        )

    except Exception:

        timeout = 8.0


    timeout = max(
        2.0,
        min(
            timeout,
            20.0,
        ),
    )


    return (
        key,
        base,
        model,
        timeout,
    )


def _evren_enabled_v1():

    # BANSA_ON_PREM_ONLY_V1
    #
    # Competition build is on-prem by default.
    # No external LLM provider may be called while this
    # guard is enabled.
    on_prem_only = str(
        _evren_os_v1.getenv(
            "BANSA_ON_PREM_ONLY",
            "1",
        )
        or ""
    ).strip().casefold()

    if on_prem_only not in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    # BANSA_ON_PREM_ONLY_V1
    #
    # Competition build is on-prem by default.
    # No external LLM provider may be called while this
    # guard is enabled.
    on_prem_only = str(
        _evren_os_v1.getenv(
            "BANSA_ON_PREM_ONLY",
            "1",
        )
        or ""
    ).strip().casefold()

    if on_prem_only not in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    # Active test suite must remain deterministic and
    # must not depend on an external network service.
    if (
        "PYTEST_CURRENT_TEST"
        in
        _evren_os_v1.environ
        and
        _evren_os_v1.getenv(
            "BANSA_ALLOW_EVREN_IN_PYTEST",
            ""
        )
        !=
        "1"
    ):

        return False


    key, base, model, _ = (
        _evren_config_v1()
    )


    return bool(
        key
        and
        base
        and
        model
    )


def _evren_system_prompt_v1():

    return (
        "BANSA icin tarafsiz bir finans asistani olarak "
        "dogal ve profesyonel Turkce cevap ver. "
        "Yalnizca kullanici mesajinda verilen dogrulanmis "
        "gercekleri kullan. "
        "Yeni bilgi, rakam, oran, tarih, kosul, avantaj veya "
        "karsilastirma uretme. "
        "Reklam slogani, satis cagrisi, 'hemen kesfedin', "
        "'kacirmayin', 'siz de' gibi pazarlama dili kullanma. "
        "Kaynakta acik bir karsilastirma yoksa 'daha ucuz', "
        "'daha dusuk maliyetli', 'en iyi' veya benzeri "
        "yeni karsilastirmalar kurma. "
        "Web sitesi metnini yapistirmak yerine bilgiyi "
        "1-3 kisa ve akici cumleyle anlat. "
        "Sadece cevabi yaz."
    )


def _evren_generate_v1(
    prompt,
):

    (
        key,
        base,
        model,
        timeout,
    ) = _evren_config_v1()


    if not key:

        raise RuntimeError(
            "EVREN_API_KEY missing."
        )


    started = (
        _evren_time_v1.perf_counter()
    )


    response = (
        _evren_requests_v1.post(
            (
                base
                + "/chat/completions"
            ),

            headers={
                "Authorization":
                    "Bearer "
                    + key,

                "Content-Type":
                    "application/json",
            },

            json={
                "model":
                    model,

                "messages": [
                    {
                        "role":
                            "system",

                        "content":
                            _evren_system_prompt_v1(),
                    },
                    {
                        "role":
                            "user",

                        "content":
                            str(
                                prompt
                                or ""
                            ),
                    },
                ],

                "temperature":
                    0.1,

                "max_tokens":
                    350,
            },

            timeout=timeout,
        )
    )


    elapsed = (
        _evren_time_v1.perf_counter()
        -
        started
    )


    if (
        response.status_code
        !=
        200
    ):

        raise RuntimeError(
            "EVREN HTTP "
            + str(
                response.status_code
            )
        )


    payload = response.json()

    choices = (
        payload.get(
            "choices"
        )
        or []
    )


    if not choices:

        raise RuntimeError(
            "EVREN choices missing."
        )


    message = (
        choices[0].get(
            "message"
        )
        or {}
    )

    text = str(
        message.get(
            "content"
        )
        or ""
    ).strip()


    if not text:

        raise RuntimeError(
            "EVREN empty generation."
        )


    return (
        text,
        elapsed,
        model,
    )


def _evren_verified_result_v1(
    *,
    text,
    model,
    latency,
    retry,
    verifier_reasons,
):

    global _EVREN_LAST_TRACE_V1


    _EVREN_LAST_TRACE_V1 = {
        "provider":
            "evren",

        "model":
            model,

        "latency_seconds":
            round(
                float(
                    latency
                ),
                4,
            ),

        "first_verified":
            (
                False
                if retry
                else True
            ),

        "retry_verified":
            (
                True
                if retry
                else None
            ),

        "fallback":
            False,

        "reason":
            (
                "strict_retry_verified"
                if retry
                else
                "first_generation_verified"
            ),
    }


    return NaturalAnswerResult(
        text=text,

        status=(
            "grounded_generation_verified"
        ),

        model_used=True,

        verified=True,

        fallback_used=False,

        reasons=tuple(
            (
                "provider_evren",
                (
                    "evren_model_"
                    + str(
                        model
                    )
                ),
            )
            +
            tuple(
                verifier_reasons
                or ()
            )
        ),
    )


def naturalize_grounded_answer(
    *,
    context,
    fallback_text,
):

    global _EVREN_LAST_TRACE_V1


    # --------------------------------------------------------
    # External provider disabled/unavailable:
    # preserve exact existing local behavior.
    # --------------------------------------------------------

    if not _evren_enabled_v1():

        _EVREN_LAST_TRACE_V1 = {
            "provider":
                "local",

            "model":
                MODEL_ID,

            "latency_seconds":
                None,

            "first_verified":
                None,

            "retry_verified":
                None,

            "fallback":
                True,

            "reason":
                "evren_not_enabled",
        }


        return (
            _naturalize_grounded_answer_local_before_evren_v1(
                context=context,
                fallback_text=(
                    fallback_text
                ),
            )
        )


    # --------------------------------------------------------
    # Reuse the EXISTING deterministic fact planner.
    # --------------------------------------------------------

    facts = build_fact_plan(
        context,
        fallback_text,
    )


    if not facts:

        _EVREN_LAST_TRACE_V1 = {
            "provider":
                "local",

            "model":
                MODEL_ID,

            "latency_seconds":
                None,

            "first_verified":
                None,

            "retry_verified":
                None,

            "fallback":
                True,

            "reason":
                "evren_no_fact_plan",
        }


        return (
            _naturalize_grounded_answer_local_before_evren_v1(
                context=context,
                fallback_text=(
                    fallback_text
                ),
            )
        )


    question = str(
        getattr(
            context,
            "question",
            "",
        )
        or ""
    ).strip()


    # --------------------------------------------------------
    # EVREN attempt 1.
    # --------------------------------------------------------

    try:

        first_prompt = (
            _build_prompt(
                question=question,
                facts=facts,
            )
        )


        (
            first_text,
            first_latency,
            first_model,
        ) = _evren_generate_v1(
            first_prompt
        )


        (
            first_ok,
            first_reasons,
        ) = verify_natural_answer(
            context=context,
            facts=facts,
            answer=first_text,
        )


        if first_ok:

            return (
                _evren_verified_result_v1(
                    text=first_text,
                    model=first_model,
                    latency=(
                        first_latency
                    ),
                    retry=False,
                    verifier_reasons=(
                        first_reasons
                    ),
                )
            )


        # ----------------------------------------------------
        # EVREN strict retry.
        # ----------------------------------------------------

        strict_prompt = (
            _build_strict_retry_prompt(
                question=question,
                facts=facts,
            )
        )


        (
            retry_text,
            retry_latency,
            retry_model,
        ) = _evren_generate_v1(
            strict_prompt
        )


        (
            retry_ok,
            retry_reasons,
        ) = verify_natural_answer(
            context=context,
            facts=facts,
            answer=retry_text,
        )


        if retry_ok:

            return (
                _evren_verified_result_v1(
                    text=retry_text,
                    model=retry_model,
                    latency=(
                        first_latency
                        +
                        retry_latency
                    ),
                    retry=True,
                    verifier_reasons=(
                        retry_reasons
                    ),
                )
            )


        _EVREN_LAST_TRACE_V1 = {
            "provider":
                "local",

            "model":
                MODEL_ID,

            "latency_seconds":
                round(
                    float(
                        first_latency
                        +
                        retry_latency
                    ),
                    4,
                ),

            "first_verified":
                False,

            "retry_verified":
                False,

            "fallback":
                True,

            "reason":
                (
                    "evren_grounding_verification_failed"
                ),
        }


    except Exception as exc:

        _EVREN_LAST_TRACE_V1 = {
            "provider":
                "local",

            "model":
                MODEL_ID,

            "latency_seconds":
                None,

            "first_verified":
                False,

            "retry_verified":
                None,

            "fallback":
                True,

            "reason":
                (
                    "evren_exception:"
                    + type(
                        exc
                    ).__name__
                ),
        }


    # --------------------------------------------------------
    # EVREN failed:
    # exact pre-existing local naturalizer takes over.
    #
    # The local naturalizer itself already contains its own
    # verifier + extractive fallback behavior.
    # --------------------------------------------------------

    return (
        _naturalize_grounded_answer_local_before_evren_v1(
            context=context,
            fallback_text=(
                fallback_text
            ),
        )
    )

