# BANSA_LOCAL_AGENT_ANSWERER_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from src.local_agent_contract import (
    CANONICAL_BANKS,
)

from src.local_llm_client import (
    LocalLLMClient,
)


@dataclass(
    frozen=True
)
class AgentAnswerResult:

    status: str

    text: str

    verified: bool

    model_used: bool

    fallback_used: bool

    reasons: tuple[
        str,
        ...
    ]


def _normalize_number(
    value,
) -> str:

    value = str(
        value
        or ""
    ).strip()

    if re.fullmatch(
        r"\d{1,3}(?:\.\d{3})+",
        value,
    ):
        return value.replace(
            ".",
            "",
        )

    if "," in value:
        return value.replace(
            ".",
            "",
        ).replace(
            ",",
            ".",
        )

    return value


def _number_tokens(
    text,
) -> set[str]:

    return {
        _normalize_number(
            token
        )
        for token in re.findall(
            r"\d[\d.,]*",
            str(
                text
                or ""
            ),
        )
    }


def _scaled_number_tokens(
    text,
) -> set[str]:

    multipliers = {
        "bin":
            Decimal(
                "1000"
            ),

        "milyon":
            Decimal(
                "1000000"
            ),

        "milyar":
            Decimal(
                "1000000000"
            ),
    }

    results = set()

    for match in re.finditer(
        (
            r"(\d[\d.,]*)"
            r"\s*"
            r"(bin|milyon|milyar)"
            r"\b"
        ),
        str(
            text
            or ""
        ),
        flags=re.IGNORECASE,
    ):

        normalized = (
            _normalize_number(
                match.group(
                    1
                )
            )
        )

        try:

            number = Decimal(
                normalized
            )

        except InvalidOperation:

            continue

        multiplier = (
            multipliers[
                match.group(
                    2
                ).casefold()
            ]
        )

        scaled = (
            number
            *
            multiplier
        )

        if (
            scaled
            ==
            scaled.to_integral_value()
        ):

            value = format(
                scaled.quantize(
                    Decimal(
                        "1"
                    )
                ),
                "f",
            )

        else:

            value = format(
                scaled.normalize(),
                "f",
            )

        results.add(
            value
        )

    return results


def _urls(
    text,
) -> set[str]:

    return {
        value.rstrip(
            ").,;"
        )
        for value in re.findall(
            r"https?://[^\s\])>]+",
            str(
                text
                or ""
            ),
            flags=re.IGNORECASE,
        )
    }


def _sanitize_grounded_markdown_urls(
    text,
    allowed_urls,
) -> str:

    allowed = set(
        allowed_urls
        or ()
    )

    value = str(
        text
        or ""
    )

    pattern = re.compile(
        r"\[[^\]]*\]\(\s*(https?://[^)\s]+)\s*\)",
        flags=re.IGNORECASE,
    )

    def _replace(match):

        url = match.group(
            1
        )

        if url in allowed:
            return url

        return match.group(
            0
        )

    return pattern.sub(
        _replace,
        value,
    )


def _bank_mentions(
    text,
) -> set[str]:

    low = str(
        text
        or ""
    ).casefold()

    return {
        bank
        for bank in CANONICAL_BANKS
        if bank.casefold()
        in low
    }


def _maximum_facts(
    verified_text,
) -> set[
    tuple[
        str,
        str,
    ]
]:

    text = str(
        verified_text
        or ""
    )

    results = set()

    patterns = (
        (
            r"(?:en\s+fazla|maksimum|azami|en\s+cok)"
            r"\s+"
            r"(\d[\d.,]*)"
            r"\s*"
            r"(mil|tl|puan)"
        ),
        (
            r"(\d[\d.,]*)"
            r"\s*"
            r"(mil|tl|puan)"
            r"(?:['\u2019]?[ea])?"
            r"\s+varan"
        ),
    )

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            results.add(
                (
                    _normalize_number(
                        match.group(
                            1
                        )
                    ),
                    match.group(
                        2
                    ).casefold(),
                )
            )

    return results


def _exact_gain_claims(
    answer,
) -> tuple[
    tuple[
        str,
        str,
        str,
    ],
    ...
]:

    text = str(
        answer
        or ""
    )

    pattern = re.compile(
        (
            r"(\d[\d.,]*)"
            r"\s*"
            r"(mil|tl|puan)"
            r"(?:\*|_|:|\s|-){0,12}"
            r"(?:"
            r"kazan(?:irsiniz|irsin|ir|di|acaksiniz|acaksin)"
            r"|"
            r"elde\s+eder(?:siniz|sin)?"
            r")"
        ),
        flags=re.IGNORECASE,
    )

    results = []

    for match in pattern.finditer(
        text
    ):

        start = max(
            0,
            match.start() - 55,
        )

        nearby = text[
            start:
            match.end()
        ].casefold()

        results.append(
            (
                _normalize_number(
                    match.group(
                        1
                    )
                ),
                match.group(
                    2
                ).casefold(),
                nearby,
            )
        )

    return tuple(
        results
    )


def _model_context_for_answer(
    *,
    tool_name,
    verified_text,
) -> str:

    text = str(
        verified_text
        or ""
    ).strip()

    if (
        str(
            tool_name
            or ""
        ).strip()
        !=
        "compare_finance"
    ):
        return text

    marker = (
        "### Kriter bazl\u0131 "
        "de\u011ferlendirme"
    )

    start = text.find(
        marker
    )

    if start < 0:
        return text

    compact = text[
        start:
    ].strip()

    urls = tuple(
        sorted(
            _urls(
                text
            )
        )
    )

    if urls:

        compact += (
            "\n\nKaynak URL'leri:\n"
            +
            "\n".join(
                urls
            )
        )

    return compact


def verify_agent_answer(
    *,
    question,
    verified_text,
    answer,
) -> tuple[
    bool,
    tuple[
        str,
        ...
    ],
]:

    answer = str(
        answer
        or ""
    ).strip()

    if not answer:
        return (
            False,
            (
                "empty_answer",
            ),
        )

    reasons = []

    # --------------------------------------------------------
    # NUMBER GROUNDING
    #
    # User-provided numbers are allowed to be repeated.
    # New numbers not present in either the question or the
    # verified tool output are not allowed.
    # --------------------------------------------------------

    allowed_numbers = (
        _number_tokens(
            question
        )
        |
        _scaled_number_tokens(
            question
        )
        |
        _number_tokens(
            verified_text
        )
    )

    generated_numbers = (
        _number_tokens(
            answer
        )
    )

    unsupported_numbers = (
        generated_numbers
        -
        allowed_numbers
    )

    if unsupported_numbers:

        reasons.append(
            "unsupported_numbers:"
            + ",".join(
                sorted(
                    unsupported_numbers
                )
            )
        )

    # --------------------------------------------------------
    # URL GROUNDING
    # --------------------------------------------------------

    allowed_urls = (
        _urls(
            verified_text
        )
    )

    generated_urls = (
        _urls(
            answer
        )
    )

    unsupported_urls = (
        generated_urls
        -
        allowed_urls
    )

    if unsupported_urls:

        reasons.append(
            "unsupported_url"
        )

    # --------------------------------------------------------
    # URL PRESENTATION CONTRACT
    #
    # Official URLs may be repeated only as plain text.
    # Markdown links are forbidden even if the target URL is
    # otherwise grounded in VERIFIED_CONTEXT.
    # --------------------------------------------------------

    if re.search(
        r"\[[^\]]*\]\(\s*https?://[^)]+\)",
        answer,
        flags=re.IGNORECASE,
    ):

        reasons.append(
            "markdown_url_not_allowed"
        )

    # --------------------------------------------------------
    # BANK GROUNDING
    # --------------------------------------------------------

    allowed_banks = (
        _bank_mentions(
            question
        )
        |
        _bank_mentions(
            verified_text
        )
    )

    generated_banks = (
        _bank_mentions(
            answer
        )
    )

    unsupported_banks = (
        generated_banks
        -
        allowed_banks
    )

    if unsupported_banks:

        reasons.append(
            "unsupported_bank:"
            + ",".join(
                sorted(
                    unsupported_banks
                )
            )
        )

    # --------------------------------------------------------
    # MAXIMUM / CAP MUST NOT BECOME EXACT GAIN
    #
    # Example:
    #
    # verified:
    #   aylik en fazla 2.000 Mil
    #
    # invalid generation:
    #   2.000 Mil kazanirsiniz
    #
    # valid generation:
    #   en fazla 2.000 Mil kazanabilirsiniz
    # --------------------------------------------------------

    maximums = (
        _maximum_facts(
            verified_text
        )
    )

    qualifiers = (
        "en fazla",
        "maksimum",
        "azami",
        "en cok",
        "kadar",
        "ust sinir",
        "tavan",
    )

    for (
        number,
        unit,
        nearby,
    ) in _exact_gain_claims(
        answer
    ):

        if (
            (
                number,
                unit,
            )
            not in maximums
        ):
            continue

        if not any(
            qualifier
            in nearby
            for qualifier in qualifiers
        ):

            reasons.append(
                (
                    "maximum_recast_as_exact_gain:"
                    + number
                    + ":"
                    + unit
                )
            )

    # --------------------------------------------------------
    # FINANCE_FEE_COVERAGE_NEGATION_GUARD_V1
    #
    # A verified finance comparison may explicitly state that
    # total fee/cost coverage is incomplete. The answer model
    # must not invert that fact into:
    #
    #   "eksik degil"
    #   "eksik olmasa da"
    #   "ucret bilgisi eksiksiz"
    #
    # This is a semantic safety guard only. It does not calculate
    # fees, rank products or modify finance-engine output.
    # --------------------------------------------------------

    def _fee_semantic_key(value) -> str:

        return (
            str(value or "")
            .casefold()
            .replace("\u0131", "i")
            .replace("\u0130", "i")
            .replace("\u015f", "s")
            .replace("\u00e7", "c")
            .replace("\u00fc", "u")
            .replace("\u00f6", "o")
            .replace("\u011f", "g")
        )

    verified_fee_key = _fee_semantic_key(
        verified_text
    )

    answer_fee_key = _fee_semantic_key(
        answer
    )

    verified_has_fee_context = (
        (
            "ucret"
            in verified_fee_key
            or
            "masraf"
            in verified_fee_key
        )
        and
        "toplam"
        in verified_fee_key
    )

    verified_fee_coverage_incomplete = (
        verified_has_fee_context
        and (
            "eksik"
            in verified_fee_key
            or
            "eksiksiz olmad"
            in verified_fee_key
            or
            "eksiksiz degil"
            in verified_fee_key
            or
            "tam olmad"
            in verified_fee_key
            or
            "tam degil"
            in verified_fee_key
        )
    )

    answer_reverses_fee_coverage = (
        re.search(
            r"\beksik\s+(?:degil|olmasa|olmad\w*)\b",
            answer_fee_key,
        )
        is not None
        or
        re.search(
            r"\b(?:ucret|masraf)"
            r"[^\n.!?]{0,80}"
            r"\beksiksiz"
            r"(?!\s+(?:degil|olmad))",
            answer_fee_key,
        )
        is not None
        or
        re.search(
            r"\b(?:ucret|masraf)"
            r"[^\n.!?]{0,80}"
            r"\b(?:tamdir|tam\s+olarak|tam\s+ve\s+eksiksiz)\b",
            answer_fee_key,
        )
        is not None
    )

    if (
        verified_fee_coverage_incomplete
        and answer_reverses_fee_coverage
    ):

        reasons.append(
            "finance_fee_coverage_negation_flip"
        )

    # --------------------------------------------------------
    # FINANCE_FEE_COVERAGE_CAVEAT_REQUIRED_V1
    #
    # If deterministic finance output explicitly says total
    # fee/cost coverage is incomplete, the naturalized answer
    # must preserve that limitation.
    #
    # Otherwise a "lowest total repayment" conclusion could be
    # misread as a complete all-in cost comparison.
    # --------------------------------------------------------

    answer_has_fee_or_cost_context = (
        "ucret"
        in answer_fee_key
        or
        "masraf"
        in answer_fee_key
        or
        "maliyet"
        in answer_fee_key
    )

    fee_limitation_patterns = (
        r"\beksik\b",

        r"\beksiksiz\s+"
        r"(?:degil|olmad\w*)\b",

        r"\btam(?:\s+olarak)?\s+"
        r"(?:degil|olmad\w*|dogrulanmad\w*)\b",

        r"\bkapsam(?:i)?\s+"
        r"(?:eksik|sinirli)\b",

        r"\b(?:tum|butun)\s+"
        r"(?:ucret|ucretler|masraf|masraflar)\b"
        r"[^\n.!?]{0,80}"
        r"\b(?:dahil\s+degil|dahil\s+olmad\w*)\b",

        r"\bkesin\s+(?:toplam\s+)?maliyet\b"
        r"[^\n.!?]{0,60}"
        r"\b(?:degil|olmad\w*)\b",
    )

    answer_preserves_fee_limitation = (
        answer_has_fee_or_cost_context
        and
        not answer_reverses_fee_coverage
        and
        any(
            re.search(
                pattern,
                answer_fee_key,
            )
            is not None
            for pattern
            in fee_limitation_patterns
        )
    )

    if (
        verified_fee_coverage_incomplete
        and not answer_preserves_fee_limitation
    ):

        reasons.append(
            "finance_fee_coverage_caveat_omitted"
        )

    return (
        not reasons,
        tuple(
            reasons
        ),
    )


def _system_prompt() -> str:

    return (
        "Sen BANSA'nin tamamen yerel calisan "
        "finans asistani cevaplayicisisin. "
        "Yalnizca VERIFIED_CONTEXT icindeki "
        "dogrulanmis bilgileri kullan. "
        "Kullanicinin kendi mesajindaki tutari "
        "tekrar edebilirsin. "
        "Yeni banka, kampanya, rakam, oran, tarih, "
        "kosul veya avantaj uydurma. "
        "Matematiksel hesap yapma. "
        "Bir maksimum veya ust siniri kesin kazanilacak "
        "tutar gibi sunma. "
        "Kaynakta sadece maksimum deger varsa "
        "bunu maksimum olarak ifade et. "
        "Asgari, minimum veya alt sinir olarak verilen "
        "bir finansal ucreti kesin ucret gibi yorumlama. "
        "Asgari veya minimum bir degeri kesin bir degerle "
        "karsilastirip daha dusuk ya da daha yuksek sonucu cikarma. "
        "VERIFIED_CONTEXT toplam ucret veya masraf kapsaminda eksik "
        "bilgi oldugunu soyluyorsa bunu tersine cevirme. "
        "Ozellikle eksik degil, eksik olmasa da veya ucret bilgisi "
        "eksiksiz gibi zit bir ifade kullanma. "
        "VERIFIED_CONTEXT eksik ucret veya masraf kapsaminin genel "
        "sonucu sinirladigini soyluyorsa bu uyariyi cevaptan cikarma. "
        "Toplam geri odeme sonucunun tum masraflari iceren kesin "
        "toplam maliyet sonucu olmadigini acik tut. "
        "VERIFIED_CONTEXT icinde acikca bulunmayan yeni bir "
        "karsilastirmali sonuc turetme. "
        "Farkli bankalarin urun veya konut kosulu varyantlarini "
        "ayni kosulmus gibi birlestirme. "
        "Her bankanin dogrulanmis kosul adlarini ayri tut. "
        "Karsilastirma sorularinda VERIFIED_CONTEXT icindeki tum "
        "tablolari ve tum ayrintilari tekrar yazma. "
        "Yalnizca kullanicinin karar vermesi icin gerekli temel "
        "farklari, dogrulanmis genel sonucu ve gerekli uyariyi ozetle. "
        "Kosul varyantlarini kullanici ozellikle sormadiysa tek tek "
        "listeleme. "
        "Cevabi gereksiz yere uzatma. "
        "Dogal, kisa ve profesyonel Turkce cevap ver. "
        "Varsa kaynak URL'sini koru. "
        "URL kullanacaksan VERIFIED_CONTEXT icindeki URL'yi "
        "karakter karakter aynen kopyala. "
        "URL'yi kisaltma, degistirme veya yeni URL uretme. "
        "Markdown link olusturma; [metin](adres) bicimini "
        "URL'ler icin kullanma. "
        "Kaynak URL'sini yalnizca duz metin olarak yaz."
    )


def answer_local_agent(
    *,
    question,
    run_result,
    client=None,
) -> AgentAnswerResult:

    if (
        run_result is None
        or
        getattr(
            run_result,
            "status",
            "",
        )
        != "ok"
        or
        getattr(
            run_result,
            "tool_result",
            None,
        )
        is None
    ):

        return AgentAnswerResult(
            status="fallback",
            text="",
            verified=False,
            model_used=False,
            fallback_used=True,
            reasons=(
                "no_verified_tool_result",
            ),
        )

    data = (
        run_result
        .tool_result
        .data
        or {}
    )

    # Preferred V2 contract:
    # every safe tool may expose deterministic verified text
    # directly. Keep the historical result["text"] contract as
    # a backward-compatible fallback.
    verified_text = str(
        data.get(
            "verified_text"
        )
        or ""
    ).strip()

    if not verified_text:

        payload = (
            data.get(
                "result"
            )
            or {}
        )

        if not isinstance(
            payload,
            dict,
        ):

            return AgentAnswerResult(
                status="fallback",
                text="",
                verified=False,
                model_used=False,
                fallback_used=True,
                reasons=(
                    "invalid_verified_payload",
                ),
            )

        verified_text = str(
            payload.get(
                "text"
            )
            or ""
        ).strip()

    if not verified_text:

        return AgentAnswerResult(
            status="fallback",
            text="",
            verified=False,
            model_used=False,
            fallback_used=True,
            reasons=(
                "missing_verified_text",
            ),
        )

    model_context = (
        _model_context_for_answer(
            tool_name=getattr(
                run_result.tool_result,
                "tool_name",
                "",
            ),
            verified_text=verified_text,
        )
    )

    active_client = (
        client
        or LocalLLMClient()
    )

    try:

        message = active_client.chat(
            [
                {
                    "role":
                        "system",

                    "content":
                        _system_prompt(),
                },
                {
                    "role":
                        "user",

                    "content":
                        (
                            "KULLANICI SORUSU:\n"
                            + str(
                                question
                                or ""
                            )
                            + "\n\n"
                            + "VERIFIED_CONTEXT:\n"
                            + model_context
                            + "\n\n"
                            + "Yalnizca bu bilgilerle "
                            + "kullaniciya cevap ver."
                        ),
                },
            ],
            max_tokens=700,
            temperature=0.0,
        )

        finish_reason = str(
            message.get(
                "_finish_reason"
            )
            or ""
        ).strip().casefold()

        draft = str(
            message.get(
                "content"
            )
            or ""
        ).strip()

        if finish_reason in {
            "length",
            "max_tokens",
        }:

            return AgentAnswerResult(
                status="safe_fallback",
                text=verified_text,
                verified=True,
                model_used=True,
                fallback_used=True,
                reasons=(
                    (
                        "answer_model_truncated:"
                        + finish_reason
                    ),
                ),
            )

    except Exception as exc:

        return AgentAnswerResult(
            status="safe_fallback",
            text=verified_text,
            verified=True,
            model_used=False,
            fallback_used=True,
            reasons=(
                (
                    "answer_model_error:"
                    + type(
                        exc
                    ).__name__
                ),
            ),
        )

    # --------------------------------------------------------
    # DETERMINISTIC URL FORMAT NORMALIZATION
    #
    # The verifier remains strict: raw Markdown URLs are still
    # forbidden. Before verification, only Markdown links whose
    # target URL is already grounded in VERIFIED_CONTEXT are
    # converted to the exact plain-text URL.
    # --------------------------------------------------------

    draft = (
        _sanitize_grounded_markdown_urls(
            draft,
            _urls(
                verified_text
            ),
        )
    )

    verified, reasons = (
        verify_agent_answer(
            question=question,
            verified_text=verified_text,
            answer=draft,
        )
    )

    if not verified:

        return AgentAnswerResult(
            status="safe_fallback",
            text=verified_text,
            verified=True,
            model_used=True,
            fallback_used=True,
            reasons=tuple(
                (
                    "generated_answer_rejected",
                )
                +
                tuple(
                    reasons
                )
            ),
        )

    return AgentAnswerResult(
        status="verified_model_answer",
        text=draft,
        verified=True,
        model_used=True,
        fallback_used=False,
        reasons=(
            "grounded_agent_answer_verified",
        ),
    )
