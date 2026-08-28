from __future__ import annotations

import os

import streamlit as st

from src.db import init_db
from src.repository import dashboard_metrics
from src.ui_theme import (
    apply_bansa_theme,
    render_hero,
    render_panel_card,
    render_section_lead,
    render_sidebar_navigation,
    render_status_badge,
)


st.set_page_config(
    page_title="BANSA · Katılım Bankacılığı Asistanı",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_bansa_theme()
render_sidebar_navigation("home")


# Home must stay fast. Heavy RAG/model prewarm is opt-in; the chatbot
# lazily prepares those layers only when a question actually needs them.
if os.getenv("BANSA_PREWARM_RAG_ON_STARTUP", "0").strip() == "1":
    @st.cache_resource(show_spinner="BANSA yapay zekâ motoru hazırlanıyor...")
    def _prewarm():
        from src.chatbot_rag_orchestrator import prewarm_rag_runtime_and_models

        return prewarm_rag_runtime_and_models()

    try:
        _prewarm()
    except Exception:
        pass

try:
    init_db()
except Exception:
    # The shell must remain usable even if a secondary data source is down.
    pass

render_hero(
    "Katılım bankacılığında doğru veriye, tek ekrandan ulaşın.",
    (
        "BANSA; finansman ürünlerini, güncel kampanyaları ve banka "
        "karşılaştırmalarını resmî kaynaklara dayalı deterministic veri "
        "katmanı ile yerel yapay zekâyı birleştirerek açık ve anlaşılır "
        "biçimde sunar."
    ),
    kicker="BANSA · BDDK Kapsamlı Yerel Finans Asistanı",
)

status_col, info_col = st.columns([1.25, 4.75], vertical_alignment="center")
with status_col:
    render_status_badge("Sistem hazır")
with info_col:
    st.caption(
        "Finansal rakamlar doğrulanmış BANSA veri/tool katmanından gelir; "
        "yerel Qwen yalnızca niyet, bağlam ve doğal anlatım için kullanılır."
    )

render_section_lead(
    "Dört ana çalışma paneli",
    "Finansman, kampanya, kart karşılaştırması ve doğal dil asistanı tek arayüzde birleştirilmiştir.",
)

left, middle, right, cards_col = st.columns(4, gap="large")

with left:
    render_panel_card(
        "💬",
        "BANSA Asistanı",
        "Finansman, kampanya, oran, vade ve takip sorularını doğal dille sorun. Konuşma bağlamı korunur.",
        "Doğal dil",
    )
    if st.button("Asistanı aç", key="home_chat", type="primary", use_container_width=True):
        st.switch_page("pages/4_Chatbot.py")

with middle:
    render_panel_card(
        "🏦",
        "Finansman Karşılaştırması",
        "Tutar, vade, finansman türü ve bankaları seçin. BANSA aynı senaryoda doğrulanabilen güncel sonuçları karşılaştırsın.",
        "Calculator-first",
    )
    if st.button("Finansmanları karşılaştır", key="home_finance", use_container_width=True):
        st.switch_page("pages/2_Finansman_Karsilastirmasi.py")

with right:
    render_panel_card(
        "🎁",
        "Kampanya Karşılaştırması",
        "Aktif banka kampanyalarını banka, kategori ve fayda kriterlerine göre sade bir tabloda karşılaştırın.",
        "Aktif kampanyalar",
    )
    if st.button("Kampanyaları karşılaştır", key="home_campaign", use_container_width=True):
        st.switch_page("pages/3_Kampanya_Karsilastirmasi.py")

with cards_col:
    render_panel_card(
        "💳",
        "Kart Karşılaştırması",
        "Katılım bankalarının kredi, banka, dijital ve özel kartlarını aidat, ödül, taksit ve dijital özelliklere göre karşılaştırın.",
        "Kaynaklı kart verisi",
    )
    if st.button("Kartları karşılaştır", key="home_cards", use_container_width=True):
        st.switch_page("pages/4_Kart_Karsilastirmasi.py")

render_section_lead("Sistem görünümü")

try:
    metrics = dashboard_metrics()
except Exception:
    metrics = {
        "total_pages": 0,
        "total_campaigns": 0,
        "active_campaigns": 0,
        "standard_products": 0,
    }

m1, m2, m3, m4 = st.columns(4)
m1.metric("İzlenen sayfa", metrics.get("total_pages", 0))
m2.metric("Kampanya kaydı", metrics.get("total_campaigns", 0))
m3.metric("Aktif kampanya", metrics.get("active_campaigns", 0))
m4.metric("Standart ürün", metrics.get("standard_products", 0))

st.markdown("")
with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**🔐 Finansal güvenlik**")
        st.caption("LLM yeni oran, taksit veya masraf üretemez; doğrulanmayan sayı gösterilmez.")
    with c2:
        st.markdown("**⚡ Hızlı çalışma**")
        st.caption("Ağır model açılışta yüklenmez; deterministic yanıtlar ve hızlı local naturalizer önceliklidir.")
    with c3:
        st.markdown("**🔎 Kaynak izlenebilirliği**")
        st.caption("Ürün ve kampanya cevapları mümkün olduğunda resmî banka kaynağıyla birlikte sunulur.")
