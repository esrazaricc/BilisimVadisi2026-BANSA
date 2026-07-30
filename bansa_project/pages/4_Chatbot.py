import streamlit as st

from src.chatbot import answer_question

st.set_page_config(page_title="Chatbot", page_icon="💬", layout="wide")
st.title("Kampanya Chatbotu")
st.caption("Cevaplar yalnızca yerel veritabanındaki kampanya kayıtlarından hazırlanır.")

question = st.text_input(
    "Sorunuz",
    placeholder="Örnek: En düşük kâr paylı konut kampanyası hangisi?",
)

if st.button("Sor", type="primary"):
    if not question.strip():
        st.warning("Önce bir soru yazın.")
    else:
        st.write(answer_question(question.strip()))
