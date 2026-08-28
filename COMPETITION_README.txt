BANSA - COMPETITION FINAL
=========================

1) Yerel Qwen server'i (bansa-qwen-local, 127.0.0.1:8000/v1) acik tutun.
2) RUN_BANSA_COMPETITION.bat dosyasina cift tiklayin.
3) PostgreSQL parolasi istenirse terminale girin.
4) Streamlit acildiginda:
   - BANSA 360: normalize finansman + kampanya tablolari
   - Chatbot: hizli aksiyonlar ve serbest soru

Yarisma guvenlik davranisi:
- Finansal sayi uydurulmaz.
- Exact dogrulanmis hesaplama varsa exact sonuc gosterilir.
- Exact sonuc yoksa urun kosullari + dogrulanmis hesaplama ornegi gosterilir.
- Ham UNVERIFIED / teknik hata mesaji jury UI'ina basılmaz; akilli rehber fallback kullanilir.
- Kampanyalarda aktiflik + tarih kapisi uygulanir.
- Finansman/kampanya yapilandirilmis sorulari once yerel hizli router'dan gecerek Qwen gecikmesini azaltir.

ACIL DURUM / YEDEK DEMO
-----------------------
PostgreSQL veya ağ/servis sorunu olursa RUN_BANSA_OFFLINE_DEMO.bat kullanin.
Bu mod, projedeki doğrulanmış SQLite/portable snapshot verileriyle finansman ve
kampanya chatbotunun yapılandırılmış sorularını çalıştırır. Qwen kapalı olsa bile
hızlı finansman/kampanya yolları cevap verir; serbest RAG soruları için Qwen önerilir.

FINAL V3 NATURAL CHAT LAYER
---------------------------
The competition build now uses src/competition_natural_chat.py before the
legacy/fast renderers. It keeps verified numerical data deterministic while
making single-product, scenario, campaign and follow-up answers conversational.
