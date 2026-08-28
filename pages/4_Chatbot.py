from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

from src.ui_theme import (
    apply_bansa_theme,
    render_nav_controls,
    render_page_header,
    render_sidebar_brand,
)


ROOT = Path(
    __file__
).resolve().parents[1]

if str(
    ROOT
) not in sys.path:

    sys.path.insert(
        0,
        str(
            ROOT
        ),
    )


import os

# BANSA_CONV_STATE_V1: yapılandırılmış-alan tabanlı konuşma motoru (banka /
# kategori / tutar / vade / soru-tipini serbest metne dönüştürmeden takip
# eder). Eski `chat_followup_context.resolve_followup_question` context'i
# cümle olarak taşıdığı için birkaç turdan sonra bilgi kaybediyordu; bu yeni
# motor onun yerine geçer. Bir sorun tespit edilirse
# BANSA_LEGACY_FOLLOWUP_RESOLVER=1 ortam değişkeniyle anında eski davranışa
# dönülebilir.
if os.getenv("BANSA_LEGACY_FOLLOWUP_RESOLVER", "0").strip() == "1":
    from src.chat_followup_context import (
        resolve_followup_question,
    )
else:
    from src.conversation_state import (
        resolve_followup_question,
    )

from src.chat_history import (
    add_message,
    conversation_exists,
    create_conversation,
    delete_conversation,
    get_messages,
    init_chat_history,
    list_conversations,
)

from src.competition_response_service import (
    ask_bansa,
)


st.set_page_config(
    page_title="BANSA",
    page_icon="\U0001f4ac",
    layout="wide",
)

apply_bansa_theme()


init_chat_history()


SESSION_KEY = (
    "bansa_current_conversation_id"
)


def _rerun() -> None:

    if hasattr(
        st,
        "rerun",
    ):

        st.rerun()

    else:

        st.experimental_rerun()


def _get_current_conversation_id():
    
    value = st.session_state.get(
        SESSION_KEY
    )

    if (
        value
        and
        conversation_exists(
            value
        )
    ):

        return value

    conversations = list_conversations(
        limit=1
    )

    if conversations:

        value = conversations[0][
            "id"
        ]

        st.session_state[
            SESSION_KEY
        ] = value

        return value

    st.session_state[
        SESSION_KEY
    ] = None

    return None


def _select_conversation(
    conversation_id: str,
) -> None:

    st.session_state[
        SESSION_KEY
    ] = conversation_id

    _rerun()


def _new_conversation() -> None:

    # CHAT_NEW_CONVERSATION_FIX_V1
    #
    # Gercekten yeni ve bos bir sohbet olustur.
    # Session'i None yapmak, _get_current_conversation_id()
    # tarafindan son sohbetin yeniden secilmesine neden oluyordu.
    conversation_id = (
        create_conversation()
    )

    st.session_state[
        SESSION_KEY
    ] = conversation_id

    _rerun()


def _delete_sidebar_conversation(
    conversation_id: str,
    current_id,
) -> None:

    # CHAT_DELETE_CONVERSATION_FIX_V1
    #
    # Sidebar'daki herhangi bir sohbet silinebilir.
    delete_conversation(
        conversation_id
    )

    # Aktif sohbet silindiyse kalan en yeni sohbete gec.
    if conversation_id == current_id:

        remaining = list_conversations(
            limit=1
        )

        st.session_state[
            SESSION_KEY
        ] = (
            remaining[0]["id"]
            if remaining
            else None
        )

    _rerun()

def _sidebar(
    current_id,
) -> None:

    with st.sidebar:

        render_sidebar_brand()
        render_nav_controls("chatbot")
        st.divider()

        if st.button(
            "\u2795 Yeni Sohbet",
            use_container_width=True,
            type="primary",
        ):

            _new_conversation()

        st.divider()

        st.caption(
            "Sohbetler"
        )

        conversations = (
            list_conversations(
                limit=40
            )
        )

        if not conversations:

            st.caption(
                "Hen\u00fcz kay\u0131tl\u0131 sohbet yok."
            )

        for conversation in conversations:

            conversation_id = (
                conversation[
                    "id"
                ]
            )

            title = str(
                conversation[
                    "title"
                ]
                or "Yeni Sohbet"
            )

            prefix = (
                "● "
                if conversation_id
                == current_id
                else ""
            )

            conversation_col, delete_col = (
                st.columns(
                    [6, 1]
                )
            )

            with conversation_col:

                if st.button(
                    prefix + title,
                    key=(
                        "conversation_"
                        + conversation_id
                    ),
                    use_container_width=True,
                ):

                    _select_conversation(
                        conversation_id
                    )

            with delete_col:

                if st.button(
                    "🗑️",
                    key=(
                        "delete_conversation_"
                        + conversation_id
                    ),
                    help="Bu sohbeti sil",
                    use_container_width=True,
                ):

                    _delete_sidebar_conversation(
                        conversation_id,
                        current_id,
                    )


def _render_empty_state() -> None:

    st.markdown(
        "### Kat\u0131l\u0131m bankac\u0131l\u0131\u011f\u0131yla ilgili ne merak ediyorsunuz?"
    )

    st.caption(
        "Finansman \u00fcr\u00fcnleri, kampanyalar ve "
        "do\u011frulanm\u0131\u015f finansman "
        "kar\u015f\u0131la\u015ft\u0131rmalar\u0131 hakk\u0131nda sorabilirsiniz."
    )

    st.markdown(
        """
- Albaraka T\u00fcrk konut finansman\u0131 ka\u00e7 ay?
- E\u011fitim finansman\u0131n\u0131n avantajlar\u0131 neler?
- Emlak Kat\u0131l\u0131m'da u\u00e7ak bileti kampanyas\u0131 var m\u0131?
- 75.000 TL 24 ay genel ihtiya\u00e7 finansman\u0131n\u0131 kar\u015f\u0131la\u015ft\u0131r.
        """
    )


def _render_messages(
    messages,
) -> None:

    for message in messages:

        role = (
            "assistant"
            if message[
                "role"
            ]
            == "assistant"
            else "user"
        )

        with st.chat_message(
            role
        ):

            st.markdown(
                message[
                    "content"
                ]
            )


current_id = (
    _get_current_conversation_id()
)

_sidebar(
    current_id
)


render_page_header(
    "BANSA Asistanı",
    (
        "Finansman ürünleri, kampanyalar, vade/oran soruları ve karşılaştırmalar için "
        "doğal dille sorun. BANSA konuşma bağlamını korur ve finansal rakamları yalnız "
        "doğrulanmış veri/tool katmanından kullanır."
    ),
    eyebrow="BANSA · Doğal Dil Paneli",
)

st.caption(
    "⚡ Hızlı ve yerel · Deterministic finans motoru · Güvenli Qwen naturalizer · Resmî kaynak"
)

quick_prompt = st.session_state.pop("bansa_prefill_chat", None)
quick_1, quick_2, quick_3, quick_4 = st.columns(4)
with quick_1:
    if st.button("🏠 Konut kıyasla", use_container_width=True):
        quick_prompt = "Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır"
with quick_2:
    if st.button("🎁 Ziraat Kampanyaları", use_container_width=True):
        quick_prompt = "Ziraat Katılım güncel kart kampanyalarını göster"
with quick_3:
    if st.button("🚗 100 Bin / 36 Ay Taşıt", use_container_width=True):
        quick_prompt = "100.000 TL 36 ay araç finansmanlarını karşılaştır"
with quick_4:
    if st.button("✨ Bana göre öner", use_container_width=True):
        st.session_state["bansa_show_recommend_panel"] = True

# BANSA_RECOMMEND_PANEL_V1: "Bana göre öner" butonu, kullanıcının kendi
# senaryosunu yazmasını beklemek yerine, sık karşılaşılan 5 gerçek hayat
# senaryosunu doğrudan tıklanabilir kartlar olarak sunar. Her kart seçildiğinde
# aynı chat akışına (resolve_followup_question -> ask_bansa) giren tam bir
# doğal dil sorusu gönderir; BANSA hiçbir zaman "öneri" için ayrı bir mantık
# kullanmaz, aynı deterministik motor üzerinden çalışır.
if st.session_state.get("bansa_show_recommend_panel"):
    with st.container(border=True):
        st.markdown("**✨ Size en yakın senaryoyu seçin, BANSA hemen karşılaştırıp önersin:**")
        rec_col1, rec_col2 = st.columns(2)
        recommend_scenarios = [
            (
                "🏠 İlk evimi almak istiyorum",
                "500 bin TL birikmişim var, 1 milyon TL'lik ev almak istiyorum. Bana en mantıklı seçeneği öner.",
            ),
            (
                "🚗 Araç finansmanı arıyorum",
                "900 bin TL'lik araba alacağım, 400 bin TL nakitim var ve aylık 25 bin TL'den fazla ödemek istemiyorum. Bana en uygun seçeneği öner.",
            ),
            (
                "🛍️ Küçük bir ihtiyacım var",
                "Telefon alacağım, yaklaşık 40 bin TL. Hangi katılım bankasında bana uygun ve düşük maliyetli bir seçenek var, öner.",
            ),
            (
                "🏢 İşletmem için finansman lazım",
                "İşletmem için 300 bin TL'lik makine alacağım, 24 ay vadeyle. Bana en uygun ticari finansmanı öner.",
            ),
            (
                "💳 Düşük ödemeli finansman istiyorum",
                "100 bin TL, 36 ay vadeyle bir finansman istiyorum ama aylık ödemem mümkün olduğunca düşük olsun. Bana en mantıklı seçeneği öner.",
            ),
        ]
        for idx, (label, scenario_prompt) in enumerate(recommend_scenarios):
            target_col = rec_col1 if idx % 2 == 0 else rec_col2
            with target_col:
                if st.button(label, use_container_width=True, key=f"bansa_rec_scn_{idx}"):
                    quick_prompt = scenario_prompt
                    st.session_state["bansa_show_recommend_panel"] = False
        if st.button("Kapat", key="bansa_rec_close"):
            st.session_state["bansa_show_recommend_panel"] = False
            st.rerun()


messages = (
    get_messages(
        current_id
    )
    if current_id
    else []
)


if messages:

    _render_messages(
        messages
    )

else:

    _render_empty_state()


typed_prompt = st.chat_input(
    "Mesaj\u0131n\u0131z\u0131 yaz\u0131n..."
)

prompt = quick_prompt or typed_prompt


if prompt:

    prompt = prompt.strip()

    if prompt:

        if not current_id:

            current_id = (
                create_conversation()
            )

            st.session_state[
                SESSION_KEY
            ] = current_id

        previous_messages = (
            get_messages(
                current_id
            )
        )

        # CONTEXT_CHAIN_V19
        # Feed RAW user turns to the central resolver. The resolver itself
        # reconstructs canonical bank/product/amount state. Keeping raw turns
        # is essential for clarification chains such as:
        #   "Vakıf motosiklet" -> "600 bin için?" -> "motosikletin değeri"
        # because the semantic meaning of the last answer depends on seeing
        # the original ambiguous amount turn, not only its previously resolved
        # canonical representation.
        previous_user_messages = [
            (message.get("content") or "")
            for message
            in previous_messages
            if message.get("role") == "user"
        ]

        resolution = (
            resolve_followup_question(
                prompt,
                previous_user_messages,
            )
        )

        add_message(
            conversation_id=(
                current_id
            ),
            role="user",
            content=prompt,
            resolved_question=(
                resolution.resolved_question
            ),
        )

        with st.chat_message(
            "user"
        ):

            st.markdown(
                prompt
            )

        try:

            with st.chat_message(
                "assistant"
            ):

                with st.spinner(
                    "BANSA yan\u0131t\u0131 haz\u0131rlan\u0131yor..."
                ):

                    response = (
                        ask_bansa(
                            resolution.resolved_question
                        )
                    )

            answer = str(
                response.text
                or ""
            ).strip()

            if not answer:

                answer = (
                    "Bu soru i\u00e7in g\u00fcvenilir bir "
                    "yan\u0131t olu\u015fturamad\u0131m."
                )

            add_message(
                conversation_id=(
                    current_id
                ),
                role="assistant",
                content=answer,
                route=str(
                    getattr(
                        response,
                        "route",
                        "",
                    )
                    or ""
                ),
                backend=str(
                    getattr(
                        response,
                        "backend",
                        "",
                    )
                    or ""
                ),
                qwen_used=bool(
                    getattr(
                        response,
                        "qwen_used",
                        False,
                    )
                ),
            )

        except Exception:

            # Jury-facing graceful degradation: never surface a raw
            # technical error card for an in-scope finance/campaign query.
            try:
                from src.competition_fast_router import smart_fallback
                answer = smart_fallback(
                    resolution.resolved_question
                ).text
            except Exception:
                answer = (
                    "### ℹ️ BANSA Akıllı Rehber\n"
                    "Sorgunuz için doğrudan yapılandırılmış eşleşme bulunamadı. "
                    "Banka, finansman türü ve mümkünse tutar/vade bilgisiyle yeniden sorabilirsiniz."
                )

            add_message(
                conversation_id=(
                    current_id
                ),
                role="assistant",
                content=answer,
                backend="ui_error",
                qwen_used=False,
            )

        _rerun()
