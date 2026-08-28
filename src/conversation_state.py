"""BANSA conversation state engine (BANSA_CONV_STATE_V1).

Purpose
-------
Track a finance conversation as a small set of *structured slots* instead of
concatenating natural-language fragments turn after turn.  The previous
follow-up resolver (``src/chat_followup_context.py``) works by rewriting the
user's new sentence into one composite sentence and pushing that composite
sentence back into the history list.  Each rewrite only carries forward what
happened to be present in the text of the *previous* resolved sentence, so a
slot that was resolved two turns ago (for example an amount/maturity pair)
can silently disappear by turn three or four even though nothing in the
conversation contradicted it.

This module keeps the actual slots (bank, product family, amount, maturity,
requested attribute/intent) in one explicit state object that is rebuilt from
the *raw* user turns on every call, so nothing is lost by re-serializing
through a sentence.  It intentionally mirrors the public shape of
``FollowupResolution`` (see ``chat_followup_context.py``) so callers such as
``pages/4_Chatbot.py`` can switch between the two resolvers by changing a
single import, with no risk to already-shipped behaviour.

Design rules
------------
* Never invent or guess a slot value. Every slot is only set from a real
  regex/alias match already used elsewhere in BANSA (``competition_fast_router``).
* A new explicit signal always overrides an inherited one for that slot.
* A new bank name or new finance family is treated as a topic change: it
  resets the *other* slots that do not obviously still apply, mirroring the
  behaviour asked for in the product spec ("Adil Katılım ticari finansmanda
  ne sunuyor?" must not inherit an old vehicle/housing context).
* The *intent* (which attribute the user is asking about right now) is
  tracked turn-by-turn and is never silently reused for an unrelated
  question; if the current turn asks a new question type, the resolved
  intent changes even if the bank/amount/maturity slots are inherited.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ConversationState:
    """Structured finance-conversation memory.

    All fields are optional: ``None``/``()`` means "not established yet",
    never "unknown but assume something".
    """

    banks: tuple[str, ...] = ()
    family: str | None = None
    amount: float | None = None
    maturity: int | None = None
    attribute: str | None = None
    compare: bool = False
    is_campaign_topic: bool = False
    campaign_title: str | None = None
    campaign_merchant: str | None = None
    recommendation: bool = False
    prefer_low_monthly: bool = False


@dataclass(frozen=True)
class FollowupResolution:
    """Same public shape as ``chat_followup_context.FollowupResolution``.

    Kept as a separate, independent class (not imported) so this module has
    no hard dependency on the legacy resolver and can be swapped in without
    touching it.
    """

    original_question: str
    resolved_question: str
    used_context: bool
    inherited_bank: str | None = None
    inherited_product: str | None = None
    state: ConversationState | None = None


_RESET_WORDS = (
    "unut", "bastan basla", "yeni soru", "farkli bir konu", "alakasiz",
    "ilgisiz", "konusma bitti", "sifirla",
)


def _asks_recommendation_text(normalized_text: str) -> bool:
    return any(phrase in normalized_text for phrase in (
        "oner", "oneri", "tavsiye", "en mantikli", "en uygun secenek",
        "en uygun banka", "hangisini sec", "hangisini tercih",
        "hangisi daha iyi", "hangisi daha mantikli", "hangisi daha uygun",
        "sen olsan", "bana gore en", "benim icin en",
    ))


def _prefers_low_monthly_text(normalized_text: str) -> bool:
    return any(phrase in normalized_text for phrase in (
        "aylik odemem mumkun oldugunca dusuk",
        "aylik odeme mumkun oldugunca dusuk",
        "aylik taksit mumkun oldugunca dusuk",
        "en dusuk aylik", "aylik odemesi en dusuk", "aylik taksiti en dusuk",
    ))

_FAMILY_LABELS = {
    "konut_finansmani": "konut finansmanı",
    "arac_finansmani": "taşıt finansmanı",
    "tasit_finansmani": "taşıt finansmanı",
    "ihtiyac_finansmani": "ihtiyaç finansmanı",
    "alisveris_finansmani": "alışveriş finansmanı",
    "arsa_finansmani": "arsa finansmanı",
    "isyeri_finansmani": "iş yeri finansmanı",
    "gayrimenkul_finansmani": "gayrimenkul finansmanı",
    "ticari_finansman": "ticari finansman",
    "gayri_nakdi_finansman": "gayri nakdi finansman",
    "tarim_finansmani": "tarım finansmanı",
    "leasing_finansal_kiralama": "leasing / finansal kiralama",
    "leasing": "leasing / finansal kiralama",
    "surdurulebilir_finansman": "sürdürülebilir finansman",
}


def _family_phrase(family: str | None) -> str:
    if not family:
        return ""
    return _FAMILY_LABELS.get(family, family.replace("_", " "))


def _looks_like_reset(normalized_text: str) -> bool:
    return any(word in normalized_text for word in _RESET_WORDS)


def _looks_like_affirmation_only(normalized_text: str, *, has_bank: bool) -> bool:
    """"Ziraat Katılım iyi", "tamam", "olur" etc: a short reaction to the
    assistant's previous answer, not a fresh question.  These turns must
    keep the *entire* prior state (including amount/maturity/attribute)
    because they add no new topic of their own — they only optionally
    confirm a bank that the assistant just proposed.

    This must stay narrow: a short sentence that names a bank *and* asks an
    explicit new question ("Adil Katılım ticari finansmanda ne sunuyor?")
    is a real topic-bearing turn, not a bare affirmation, even though it is
    short and contains a bank name.
    """
    tokens = normalized_text.split()
    if not tokens:
        return False
    if len(tokens) > 6:
        return False
    affirmations = {
        "iyi", "tamam", "olur", "uygun", "guzel", "harika", "evet",
        "bunu", "bu", "istiyorum", "secelim", "secebiliriz", "gidelim",
    }
    non_affirmation_tokens = [t for t in tokens if t not in affirmations]
    # A question mark or an explicit question word means this turn is
    # asking something new, not just reacting — never treat it as a bare
    # affirmation regardless of bank mention.
    if "?" in normalized_text or any(
        w in non_affirmation_tokens for w in (
            "ne", "nedir", "nasil", "kac", "hangi", "ne sunuyor", "sunuyor",
        )
    ):
        return False
    # An explicit request/command verb ("göster", "listele", "var mı",
    # "kaç", "söyle") means the user is issuing a new instruction, not
    # reacting to the assistant's last message — even if it also names a
    # bank in a short sentence (e.g. "Ziraat Katılım'ın kampanyalarını
    # göster"). Without this, such commands were misclassified as a bare
    # affirmation and silently kept stale topic state (e.g. a previous
    # campaign merchant) instead of starting a fresh request.
    if any(
        w in non_affirmation_tokens for w in (
            "goster", "listele", "soyle", "var", "getir", "ac", "bul",
        )
    ):
        return False
    # If, after removing filler/affirmation tokens, nothing informative is
    # left besides (optionally) a bank name that detect_banks already
    # consumed, this is a pure affirmation turn.
    return has_bank or len(non_affirmation_tokens) <= 1


_KNOWN_MERCHANT_WORDS = (
    "teknosa", "gree", "gree klima", "monster", "restoderm", "idefix",
    "a101", "english home", "eve", "amazon", "trendyol",
    "hepsiburada", "mediamarkt", "vatan", "n11", "carrefoursa", "migros",
    "bim", "şok", "sok", "ikea", "decathlon", "lcw", "lc waikiki", "koton",
    "boyner", "defacto", "mavi",
)

_KNOWN_CAMPAIGN_CATEGORIES = (
    "market", "teknoloji", "seyahat", "akaryakit", "akaryakıt", "egitim", "eğitim",
    "mobilya", "saglik", "sağlık",
)


def _extract_campaign_subject(text: str) -> str | None:
    """Bir kampanya sorusundaki marka/kurum adını (varsa) çıkarır.

    Yalnızca bilinen bir üye işyeri/marka listesiyle eşleşen kelimeleri
    tanır — hiçbir isim uydurulmaz. Eşleşme yoksa None döner.
    """
    from src.competition_fast_router import normalize

    norm = normalize(text)
    for merchant in _KNOWN_MERCHANT_WORDS:
        if normalize(merchant) in norm:
            return merchant
    for category in _KNOWN_CAMPAIGN_CATEGORIES:
        if normalize(category) in norm and "kampany" in norm:
            return category

    # V47: retain an explicit campaign subject even when the merchant has not
    # been hard-coded yet.  This is intentionally conservative: it runs only
    # on wording that explicitly says campaign and keeps a few distinctive
    # non-question tokens (e.g. "gree klima kampanyasında" -> "gree klima").
    if "kampany" in norm:
        stop = {
            "kampanya", "kampanyasi", "kampanyasinda", "kampanyalar",
            "kac", "ne", "nedir", "var", "mi", "mı", "mu", "mü",
            "taksit", "imkani", "imkan", "firsati", "firsat", "gecerli",
            "zamana", "kadar", "son", "tarih", "aktif", "guncel",
            "kart", "kredi", "banka", "bankasi", "katilim", "icin", "ile",
            "kampanyalarini", "kampanyalari", "karsilastir", "karsilastirma", "sadece",
        }
        tokens = [t for t in norm.split() if len(t) >= 3 and t not in stop and not t.isdigit()]
        if tokens:
            return " ".join(tokens[:3])
    return None


def resolve_followup_question(
    question: str,
    history,
    *,
    _current_state: ConversationState | None = None,
) -> FollowupResolution:
    """Resolve ``question`` against ``history`` using explicit slot tracking.

    ``history`` is a list of *raw* previous user turns, oldest first — the
    same contract the legacy resolver uses. Passing ``_current_state``
    lets a caller that already keeps a live ``ConversationState`` (for
    example a Streamlit session) skip recomputing it from raw history on
    every turn; when omitted it is rebuilt from ``history`` each call so the
    function stays a drop-in replacement.
    """
    from src.competition_fast_router import (
        detect_attribute,
        detect_banks,
        detect_family,
        is_campaign_query,
        is_compare_query,
        normalize,
        parse_amount_and_maturity,
    )

    original = str(question or "").strip()
    if not original:
        return FollowupResolution(
            original_question=original, resolved_question=original, used_context=False,
        )

    state = _current_state if _current_state is not None else _rebuild_state(list(history or []))

    norm = normalize(original)
    current_banks = tuple(detect_banks(original))
    current_family = detect_family(original)
    current_amount, current_maturity = parse_amount_and_maturity(original)
    current_attribute = detect_attribute(original)
    current_compare = is_compare_query(original)
    current_recommendation = _asks_recommendation_text(norm)
    current_prefer_low_monthly = _prefers_low_monthly_text(norm)
    current_is_campaign = is_campaign_query(original)
    try:
        from src.card_query_service import is_card_product_query
        current_is_card = bool(is_card_product_query(original))
    except Exception:
        current_is_card = False

    if _looks_like_reset(norm):
        state = ConversationState()

    affirmation_only = _looks_like_affirmation_only(norm, has_bank=bool(current_banks))

    # --- Kampanya konusu takibi -------------------------------------------------
    # "Teknosa kampanyası var mı?" -> "ne zamana kadar geçerli?" gibi bir
    # zincirde, ikinci mesajda ne banka ne de kampanya adı tekrar geçer.
    # Bu yüzden bir kampanya sorusunda geçen özel isim (marka/kurum adı gibi
    # görünen büyük harfli veya bilinen bir kelime) hatırlanır ve sonraki
    # kampanya sorularına (yeni bir konu sinyali gelene kadar) eklenir.
    current_campaign_subject = _extract_campaign_subject(original) if current_is_campaign else None
    bank_only_campaign_followup = bool(
        state.is_campaign_topic and current_banks and not current_family and not current_is_campaign
        and any(marker in norm for marker in ("peki", "sadece", "yalniz", "yalnız"))
    )
    topic_changed_away_from_campaign = bool(
        (current_banks or current_family) and not affirmation_only and not bank_only_campaign_followup
    )
    if topic_changed_away_from_campaign:
        campaign_merchant = current_campaign_subject
        is_campaign_topic = current_is_campaign
    elif current_campaign_subject:
        campaign_merchant = current_campaign_subject
        is_campaign_topic = True
    elif current_is_campaign and state.is_campaign_topic:
        campaign_merchant = state.campaign_merchant
        is_campaign_topic = True
    elif bank_only_campaign_followup:
        campaign_merchant = state.campaign_merchant
        is_campaign_topic = True
    elif current_is_campaign:
        campaign_merchant = None
        is_campaign_topic = True
    else:
        campaign_merchant = state.campaign_merchant if not topic_changed_away_from_campaign else None
        is_campaign_topic = state.is_campaign_topic and not topic_changed_away_from_campaign

    # --- Topic-change detection -------------------------------------------------
    # A new, different bank name is a topic change for the bank slot only
    # when the turn is not a pure affirmation of a bank the assistant just
    # suggested (e.g. "Ziraat Katılım iyi" right after BANSA listed Ziraat
    # among options must *set* the bank, not be treated as contradicting a
    # nonexistent previous bank).
    #
    # BANSA_GENERIC_CAMPAIGN_RESET_V1: a *generic* campaign question ("şu an
    # aktif kart kampanyaları neler?") that names no bank and no known
    # merchant is a fresh, broad request — it must not inherit a bank/family
    # left over from an unrelated finance conversation (e.g. two banks being
    # compared for vehicle financing). A campaign follow-up that DOES name a
    # bank, or that continues a specific campaign_merchant already in state,
    # is handled separately above and is unaffected by this reset.
    generic_campaign_reset = bool(
        current_is_campaign and not current_banks and not current_campaign_subject
        and not (state.is_campaign_topic and state.campaign_merchant)
    )

    # V47 cross-domain isolation. An explicit card-product question is a new
    # topic and must never inherit finance amount/family slots. Likewise, an
    # explicit *generic* finance request ("100 bin TL 36 ay bir finansman
    # istiyorum") must not silently inherit the previous product family; the
    # assistant should ask which finance type the user means.
    generic_finance_reset = bool(
        not current_family and not current_banks and not current_is_campaign and not current_is_card
        and current_amount is not None
        and any(phrase in norm for phrase in (
            "bir finansman istiyorum", "finansman istiyorum", "finansman ariyorum",
            "bir finansman lazim", "finansman lazim", "finansman ihtiyacim var",
        ))
    )
    hard_topic_reset = bool(current_is_card or generic_finance_reset)
    banks = () if (generic_campaign_reset or hard_topic_reset) else (current_banks if current_banks else state.banks)

    # A new explicit family that conflicts with the stored one is a real
    # topic change ("Adil Katılım ticari finansmanda ne sunuyor?" after a
    # vehicle-finance conversation) and drops amount/maturity/attribute
    # inherited from the old family, since they described a different
    # product line.
    family_changed = bool(current_family and state.family and current_family != state.family)
    family = None if (generic_campaign_reset or hard_topic_reset) else (current_family or state.family)

    if current_is_card:
        amount = current_amount
        maturity = current_maturity
        attribute = current_attribute
        used_context = False
        is_campaign_topic = False
        campaign_merchant = None
    elif generic_finance_reset:
        amount = current_amount
        maturity = current_maturity
        attribute = current_attribute
        used_context = False
        is_campaign_topic = False
        campaign_merchant = None
    elif generic_campaign_reset:
        amount = current_amount
        maturity = current_maturity
        attribute = current_attribute
        used_context = False
    elif family_changed and not affirmation_only:
        amount = current_amount
        maturity = current_maturity
        attribute = current_attribute
        used_context = bool(banks and not current_banks)
    else:
        amount = current_amount if current_amount is not None else state.amount
        maturity = current_maturity if current_maturity is not None else state.maturity
        # Intent must reflect the *current* turn whenever the current turn
        # asks anything recognisable; only fall back to the inherited intent
        # when this turn adds no new question type of its own (e.g. a bare
        # "peki ya Ziraat?" after a maturity question keeps asking maturity).
        attribute = current_attribute if current_attribute is not None else state.attribute
        used_context = bool(
            (current_amount is None and state.amount is not None)
            or (current_maturity is None and state.maturity is not None)
            or (current_attribute is None and state.attribute is not None)
            or (not current_banks and state.banks)
            or (not current_family and state.family)
        )

    compare = current_compare or (
        state.compare
        and not current_family
        and (
            (len(banks) >= 2 and not current_banks)
            or bank_only_campaign_followup
        )
    )

    # Recommendation intent is a decision goal, not a finance product slot.
    # Preserve it across short clarification/follow-up turns (e.g. user first
    # says "100 bin / 36 ay, en düşük aylık ödemeyi öner", then only
    # clarifies "konut finansmanı"). Reset it when we explicitly leave the
    # finance topic for card/campaign or when a hard topic reset occurs.
    if current_is_card or current_is_campaign:
        recommendation = False
        prefer_low_monthly = False
    elif hard_topic_reset:
        recommendation = current_recommendation
        prefer_low_monthly = current_prefer_low_monthly
    else:
        recommendation = current_recommendation or state.recommendation
        prefer_low_monthly = current_prefer_low_monthly or (state.prefer_low_monthly and recommendation)

    new_state = ConversationState(
        banks=banks,
        family=family,
        amount=amount,
        maturity=maturity,
        attribute=attribute,
        compare=compare,
        is_campaign_topic=is_campaign_topic,
        campaign_merchant=campaign_merchant,
        recommendation=recommendation,
        prefer_low_monthly=prefer_low_monthly,
    )

    resolved = _compose_resolved_question(original, new_state, used_context=used_context)

    # Kampanya sorularında context kullanımı, banka/tutar/vade'den bağımsız
    # olarak da gerçekleşebilir (örn. "ne zamana kadar geçerli?" hiçbir yeni
    # marka/banka içermez ama önceki kampanya konusunu miras alır).
    if is_campaign_topic and campaign_merchant and not current_campaign_subject:
        used_context = True
        resolved = _compose_resolved_question(original, new_state, used_context=True)

    return FollowupResolution(
        original_question=original,
        resolved_question=resolved,
        used_context=used_context,
        inherited_bank=" ve ".join(banks) if banks else None,
        inherited_product=_family_phrase(family) or None,
        state=new_state,
    )


def _compose_resolved_question(original: str, state: ConversationState, *, used_context: bool) -> str:
    """Build the sentence handed to the answer engine.

    The answer engine (``competition_natural_chat.answer_natural`` and the
    deterministic fast router) only receives free text, so the resolved
    sentence must explicitly restate every known slot every time — never
    just append the new fragment to the old resolved sentence, which is the
    mechanism that dropped amount/maturity in the legacy resolver after two
    or three turns.
    """
    if not used_context:
        return original

    # BANSA_CAMPAIGN_TOPIC_ISOLATION_V1: when the conversation is currently
    # about a campaign, the resolved sentence must carry ONLY the bank (if
    # any) and the campaign subject — never the finance amount/maturity/
    # family that happened to be established earlier in the conversation.
    # Otherwise a bare campaign follow-up like "hangi tarihe kadar geçerli?"
    # gets prefixed with stale finance context ("Ziraat Katılım taşıt
    # finansmanı 500000 TL") and the answer engine derails into an
    # unrelated finance-amount-ambiguity question instead of answering
    # about the campaign.
    if state.is_campaign_topic and state.campaign_merchant:
        campaign_parts: list[str] = []
        if state.banks:
            campaign_parts.append(" ve ".join(state.banks))
        if state.compare:
            campaign_parts.append(f"{state.campaign_merchant} kampanyalarını karşılaştır")
            return " ".join(campaign_parts).strip()
        campaign_parts.append(f"{state.campaign_merchant} kampanyası")
        prefix = " ".join(campaign_parts).strip()
        return f"{prefix} - {original}".strip()

    parts: list[str] = []
    if state.banks:
        parts.append(" ve ".join(state.banks))
    family_phrase = _family_phrase(state.family)
    if family_phrase:
        parts.append(family_phrase)
    if state.amount is not None:
        amount = state.amount
        parts.append(f"{int(amount)} TL" if float(amount).is_integer() else f"{amount} TL")
    if state.maturity is not None:
        parts.append(f"{int(state.maturity)} ay")

    prefix = " ".join(parts).strip()
    if not prefix:
        return original

    # Carry the user's decision goal through a clarification turn. The answer
    # engine only sees this resolved free-text sentence, so without this cue a
    # turn like "konut finansmanı" would list options but forget that the user
    # explicitly asked BANSA to recommend the lowest-monthly-payment choice.
    decision_tail = ""
    if state.recommendation:
        if state.prefer_low_monthly:
            decision_tail = " Aylık ödemesi mümkün olduğunca düşük olan en mantıklı seçeneği öner."
        else:
            decision_tail = " Bana en mantıklı seçeneği öner."

    # Keep the user's own current-turn wording attached so the answer engine
    # still sees the literal question type (e.g. "vadesi kaç ay olabilir?"),
    # while the restated prefix guarantees the bank/amount/maturity slots
    # cannot be lost between turns.
    return f"{prefix} - {original}{decision_tail}".strip()


def _rebuild_state(history: list[str]) -> ConversationState:
    state = ConversationState()
    for turn in history:
        turn = str(turn or "").strip()
        if not turn:
            continue
        resolution = resolve_followup_question(turn, [], _current_state=state)
        if resolution.state is not None:
            state = resolution.state
    return state


def resolve_followup_question_compat(question: str, history):
    """Return a ``chat_followup_context.FollowupResolution``-compatible
    object built by this module's engine.

    This lets a caller that already imports the legacy
    ``FollowupResolution`` type (for example ``pages/4_Chatbot.py``) switch
    resolvers via a single import change without adjusting any attribute
    access, since both dataclasses expose the same
    ``original_question / resolved_question / used_context / inherited_bank
    / inherited_product`` fields.
    """
    return resolve_followup_question(question, history)
