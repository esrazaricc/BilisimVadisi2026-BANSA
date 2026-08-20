import pandas as pd
import streamlit as st

from src.banks import get_bank, load_banks
from src.pipeline import analyze_url
from src.scraping.campaign_discovery import DiscoveryError, discover_campaign_links
from src.scraping.http_client import ScrapeError

st.set_page_config(page_title="Banka Taraması", page_icon="🌐", layout="wide")
st.title("Banka Kampanya Sayfalarını Tara")
st.write(
    "BDDK listesinde bulunan katılım bankalarını buradan seçebiliriz. "
    "Tarama yapısı tamamlanan bankalarda kampanya bağlantıları otomatik bulunur."
)

banks = load_banks()
if not banks:
    st.error("config/banks.json dosyasında banka tanımı bulunamadı.")
    st.stop()

bank_names = [bank["name"] for bank in banks]
selected_bank_name = st.selectbox("Banka", bank_names)
selected_bank = get_bank(selected_bank_name)

st.caption(selected_bank.get("legal_name", selected_bank_name))
st.link_button("Bankanın resmî sitesini aç", selected_bank["base_url"])

scanner_ready = selected_bank.get("scanner_ready", False)
campaign_pages = selected_bank.get("campaign_pages", [])

if scanner_ready and campaign_pages:
    st.success("Bu banka için otomatik kampanya taraması hazır.")

    with st.expander("Taranacak kampanya liste sayfaları"):
        for page_url in campaign_pages:
            st.code(page_url)
else:
    st.warning(
        "Bu banka BDDK kapsam listesine eklendi. Ancak bankaya özel kampanya "
        "liste ve detay sayfası kuralları henüz hazırlanmadığı için otomatik "
        "tarama şu anda kapalıdır."
    )
    st.stop()

session_key = f"discovered_campaign_links_{selected_bank_name}"

if st.button("Kampanya bağlantılarını bul", type="primary"):
    try:
        links = discover_campaign_links(selected_bank)
        st.session_state[session_key] = links
        st.success(f"{len(links)} kampanya detay bağlantısı bulundu.")
    except DiscoveryError as error:
        st.error(str(error))

links = st.session_state.get(session_key, [])
if not links:
    st.stop()

links_df = pd.DataFrame(links)
st.dataframe(
    links_df[["title", "url"]],
    use_container_width=True,
    hide_index=True,
)

max_count = min(len(links), 100)
scan_count = st.number_input(
    "Bu çalıştırmada analiz edilecek sayfa sayısı",
    min_value=1,
    max_value=max_count,
    value=min(10, max_count),
    step=1,
)

if st.button("Seçilen sayfaları analiz et ve kaydet"):
    progress = st.progress(0)
    status = st.empty()
    results = []

    for index, item in enumerate(links[: int(scan_count)], start=1):
        status.write(f"Analiz ediliyor: {item['title']}")

        try:
            result = analyze_url(
                bank_name=selected_bank_name,
                url=item["url"],
                save=True,
            )
            results.append(
                {
                    "Başlık": result["title"],
                    "Sayfa Türü": result["classification"]["page_type"],
                    "Kampanya": (
                        "Evet" if result["classification"]["is_campaign"] else "Hayır"
                    ),
                    "Güven": result["classification"]["confidence"],
                    "URL": item["url"],
                    "Hata": "",
                }
            )
        except ScrapeError as error:
            results.append(
                {
                    "Başlık": item["title"],
                    "Sayfa Türü": "",
                    "Kampanya": "",
                    "Güven": "",
                    "URL": item["url"],
                    "Hata": str(error),
                }
            )

        progress.progress(index / int(scan_count))

    status.empty()
    st.success("Tarama tamamlandı.")
    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
