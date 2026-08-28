"""Fast, local-only surface naturalizer for jury-facing deterministic answers.

V16.4 principle:
    deterministic finance/campaign engines decide WHAT is true;
    the small local Qwen model may only decide HOW verified prose is phrased.

The model never receives tools and never becomes a source of financial facts.
Every generated numeric token must already exist in the deterministic answer.
If the local model is unavailable or verification fails, the original answer is
returned unchanged.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import os
import re

from src.competition_fast_router import FastRouteAnswer, normalize


_ALLOWED_ROUTES = {
    "finance_product_conversation",
    "finance_product_benefits",
}

_DESCRIPTIVE_MARKERS = (
    "nasil", "nedir", "ozellik", "avantaj", "hakkinda", "bilgi",
    "anlat", "ne ise yarar", "kimler", "neleri kaps",
)

_FORBIDDEN_MODEL_WORDS = (
    "unverified", "exact", "evidence", "rag", "fact ", "veritabani",
    "database", "snapshot",
)

_BANK_SURFACES = (
    "Albaraka Türk", "Dünya Katılım", "Hayat Finans", "Kuveyt Türk",
    "T.O.M. Katılım", "Türkiye Emlak Katılım", "Türkiye Finans",
    "Vakıf Katılım", "Ziraat Katılım", "Adil Katılım",
)


def _enabled() -> bool:
    value = str(os.getenv("BANSA_FAST_NATURALIZER_ENABLED", "1") or "1").strip().casefold()
    return value not in {"0", "false", "off", "no"}


def _should_polish(question: str, answer: FastRouteAnswer) -> bool:
    if not _enabled() or str(answer.route or "") not in _ALLOWED_ROUTES:
        return False
    q = normalize(question)
    if not any(marker in q for marker in _DESCRIPTIVE_MARKERS):
        return False
    # Exact calculations/rate/fee questions are already concise deterministic
    # responses and should not pay a model-latency or paraphrase risk.
    if any(marker in q for marker in (
        "kar payi", "oran", "aylik taksit", "toplam geri odeme", "hesapla",
        "tahsis", "ekspertiz", "ipotek", "masraf", "ucret", "kac ay",
        "azami", "maksimum", "en fazla ne kadar",
    )):
        return False
    return True


def _split_verified_text(text: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    raw = str(text or "").strip()
    heading = ""
    facts: list[str] = []
    sources: list[str] = []

    for block in re.split(r"\n\s*\n", raw):
        block = block.strip()
        if not block:
            continue
        if block.startswith("### ") and not heading:
            heading = block
            continue
        if re.search(r"\[[^\]]+\]\(https?://", block):
            sources.append(block)
            continue
        cleaned = block
        cleaned = cleaned.replace("BANSA'daki doğrulanmış hesaplama örneği", "Referans hesaplama örneği")
        cleaned = cleaned.replace("BANSA'nın doğrulanmış hesaplama örneği", "Referans hesaplama örneği")
        cleaned = re.sub(r"\*\*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            facts.append(cleaned)

    return heading, tuple(facts), tuple(sources)


def _number_tokens(text: str) -> tuple[str, ...]:
    """Canonical numeric values used by the grounding guard.

    Units are intentionally ignored here (``120 ay`` vs ``120 aya``), while
    the numeric value itself must already exist in the deterministic source.
    """
    values = re.findall(r"(?<!\w)%?\d[\d.,]*", str(text or ""), flags=re.I)
    result: list[str] = []
    for value in values:
        v = value.casefold().lstrip("%")
        if "," in v:
            v = v.replace(".", "").replace(",", ".")
        elif v.count(".") > 1:
            v = v.replace(".", "")
        result.append(v)
    return tuple(result)


def _introduced_bank(source: str, generated: str) -> bool:
    src = normalize(source)
    gen = normalize(generated)
    for bank in _BANK_SURFACES:
        b = normalize(bank)
        if b in gen and b not in src:
            return True
    return False


def _verify(source: str, generated: str) -> bool:
    text = str(generated or "").strip()
    if len(text) < 35 or len(text) > 1800:
        return False
    lower = normalize(text)
    if any(word in lower for word in _FORBIDDEN_MODEL_WORDS):
        return False
    if "http://" in text or "https://" in text:
        return False
    if _introduced_bank(source, text):
        return False

    source_numbers = set(_number_tokens(source))
    generated_numbers = set(_number_tokens(text))
    if not generated_numbers.issubset(source_numbers):
        return False

    # Do not allow attractive but unsupported marketing conclusions.
    for claim in ("masrafsiz", "ucretsiz", "en avantajli", "en uygun", "garantili"):
        if claim in lower and claim not in normalize(source):
            return False
    return True



def _compact_deterministic_fallback(heading: str, facts: tuple[str, ...], sources: tuple[str, ...]) -> str:
    """Compact broad product facts without changing any financial content."""
    description = ""
    maturity = ""
    rate = ""
    fee = ""
    eligibility = ""
    application = ""

    for fact in facts:
        n = normalize(fact)
        if n.startswith("azami vade") or n.startswith("vade acisindan"):
            maturity = fact
        elif "kar payi" in n and ("sabit" in n or "oran" in n):
            rate = fact
        elif n.startswith("masraf tarafinda"):
            fee = fact
        elif n.startswith("kimler neyi kapsiyor"):
            eligibility = re.sub(r"^Kimler/neyi kapsıyor\?\s*", "", fact, flags=re.I)
        elif n.startswith("basvuru"):
            application = re.sub(r"^Başvuru:\s*", "", fact, flags=re.I)
        elif n.startswith("referans hesaplama"):
            # A historical/example calculation is not a product feature. Keep it
            # out of a broad overview unless the user explicitly asks for one.
            continue
        elif not description:
            description = fact

    first_parts = [x.rstrip(".") for x in (description, maturity, rate) if x]
    paragraphs: list[str] = []
    if first_parts:
        paragraphs.append(". ".join(first_parts) + ".")
    if fee:
        fee_norm = normalize(fee)
        # Common mortgage-fee wording is scraper-like; render the same verified
        # facts as natural prose without adding or changing a number.
        if (
            "tahsis" in fee_norm
            and "ekspertiz" in fee_norm
            and ("ipotek" in fee_norm or "rehin" in fee_norm)
            and "gercek maliyet" in fee_norm
        ):
            rate_match = re.search(r"%\s*([0-9]+(?:[.,][0-9]+)?)", fee)
            rate_text = ("%" + rate_match.group(1)) if rate_match else ""
            sentence = "Masraflarda tahsis ücreti"
            if rate_text:
                sentence += f" finansman tutarının {rate_text}'si"
            sentence += "; ekspertiz ve ipotek/rehin ücretleri üçüncü kişilere ödenen gerçek maliyete göre değişiyor"
            if "bsmv muaftir" in fee_norm:
                sentence += " ve bu kalemlerde BSMV muafiyeti belirtiliyor"
            paragraphs.append(sentence + ".")
        else:
            paragraphs.append(fee)
    if eligibility and eligibility not in " ".join(paragraphs):
        paragraphs.append(eligibility)
    if application:
        app_norm = normalize(application)
        if "albaraka mobil" in app_norm and "musterimiz olmaniz gerekmeden" in app_norm:
            paragraphs.append("Başvuru Albaraka Mobil üzerinden müşteri olmadan yapılabiliyor.")
        else:
            paragraphs.append("Başvuru tarafında " + application[:1].lower() + application[1:])

    parts = []
    if heading:
        parts.append(heading)
    parts.extend(paragraphs[:4])
    if sources:
        parts.append("\n".join(sources))
    return "\n\n".join(parts).strip()

def _surface_prompt(question: str, facts: tuple[str, ...]) -> str:
    fact_text = "\n".join(f"- {fact}" for fact in facts)
    return (
        "Kullanıcı sorusu:\n" + str(question or "").strip() +
        "\n\nYalnızca kullanabileceğin doğrulanmış bilgiler:\n" + fact_text +
        "\n\nGörev: Bu bilgileri 2-4 kısa, doğal Türkçe cümleyle finans asistanı gibi anlat. "
        "Kullanıcının sorduğu özellik/avantajı önce cevapla. Ham veri alanlarını peş peşe sayma. "
        "Yeni rakam, oran, ücret, vade, koşul, banka veya ürün ekleme. Mevcut rakamları değiştirme. "
        "Referans hesap farklı senaryoya aitse bunu kesin teklif gibi sunma. "
        "UNVERIFIED, exact, snapshot, RAG, evidence, veritabanı gibi teknik kelimeler kullanma. "
        "Başvuru detayını kullanıcı sormadıysa en fazla bir kısa cümlede tut. Sadece cevabı yaz."
    )


@lru_cache(maxsize=256)
def _generate(question: str, facts: tuple[str, ...]) -> str:
    # First choice: the project's on-prem OpenAI-compatible Qwen endpoint.
    # LocalLLMClient rejects non-loopback URLs, so this can never become an
    # external/commercial API dependency. A small local model is the fallback.
    try:
        from dataclasses import replace
        from src.local_llm_client import LocalLLMClient, LocalLLMConfig

        cfg = LocalLLMConfig.from_env()
        timeout = float(os.getenv("BANSA_FAST_NATURALIZER_TIMEOUT_SECONDS", "0.8") or "0.8")
        cfg = replace(cfg, timeout_seconds=max(0.2, min(timeout, 2.0)))
        client = LocalLLMClient(cfg)
        message = client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Sen BANSA'nın kontrollü doğal anlatım katmanısın. "
                        "Finansal gerçekleri değiştiremez veya yeni bilgi üretemezsin."
                    ),
                },
                {"role": "user", "content": _surface_prompt(question, facts)},
            ],
            max_tokens=240,
            temperature=0.0,
        )
        text = str(message.get("content") or "").strip()
        if text:
            return text
    except Exception:
        pass

    # Do not load a transformer model synchronously on the user's request
    # path. If a bundled naturalizer is explicitly pre-enabled by deployment,
    # it may be used; otherwise fail fast to the compact deterministic renderer.
    enabled = str(os.getenv("BANSA_FAST_NATURALIZER_BUNDLED_FALLBACK", "0")).strip().casefold()
    if enabled in {"1", "true", "yes", "on"}:
        from src.chatbot_grounded_naturalizer import _generate as grounded_generate
        return grounded_generate(question=question, facts=facts, strict_retry=False)
    raise RuntimeError("fast local naturalizer unavailable")


def maybe_naturalize_fast_answer(question: str, answer: FastRouteAnswer) -> tuple[FastRouteAnswer, bool]:
    if not _should_polish(question, answer):
        return answer, False

    heading, facts, sources = _split_verified_text(answer.text)
    if not facts:
        return answer, False

    try:
        generated = _generate(question, facts)
    except Exception:
        # The deterministic V17 product renderer is already natural and
        # question-aware. Do not replace it with a lossy compact summary merely
        # because Qwen is offline or misses the sub-second deadline.
        return answer, False

    source_body = "\n".join((heading,) + facts)
    if not _verify(source_body, generated):
        # Safety beats style: keep the authoritative deterministic answer when
        # the model omits/changes critical facts or invents a number.
        return answer, False

    parts = []
    if heading:
        parts.append(heading)
    parts.append(generated.strip())
    if sources:
        parts.append("\n".join(sources))

    polished = replace(
        answer,
        text="\n\n".join(parts).strip(),
        backend="competition_fast_qwen_surface",
        reasons=tuple(answer.reasons or ()) + (
            "local_qwen_surface_naturalized",
            "numeric_subset_verified",
        ),
    )
    return polished, True
