# BANSA V39 · Kampanya + UI Final Notları

Bu sürüm, `BANSA_V38_User_Friendly_Finance_Final` baz alınarak hazırlanmıştır.

## Korunan alanlar

- Chatbot akışı, `pages/4_Chatbot.py` içinde çalışan `resolve_followup_question -> ask_bansa` hattı korunmuştur.
- Finansman karşılaştırmasında V38 ile gelen tutar/vade/finansman türü ekranı korunmuştur.
- Finance engine, verifier, RAG, dense/BM25/RRF ve deterministic hesaplama dosyalarına dokunulmamıştır.

## Eklenen / iyileştirilen alanlar

- Kampanya karşılaştırması artık önce özet kartları ve `BANSA önerisi` kutusu gösterir.
- Büyük kampanya tablosu varsayılan olarak gizlenmiştir; kullanıcı `Detaylı kampanya karşılaştırma tablosunu göster` alanından açar.
- Kullanıcı artık kampanya tarafında kategori, banka, harcama tutarı, kullanım tipi, öncelik, kart ilgisi ve yeni müşteri ilgisi seçebilir.
- Kampanyalar kullanıcı senaryosuna göre açıklanabilir bir BANSA skoru ile sıralanır.
- Kategoriye göre dinamik sütun görünümü kullanılır; tablo duvarı yerine en anlamlı sütunlar öne çıkarılır.
- `Bilgi yok` gibi ham veri ifadeleri kampanya ve kart UI yüzeyinde kullanıcı dostu yönlendirme metinleriyle değiştirilmiştir.
- Ortak tasarım katmanına yeni insight card ve öneri kutusu bileşenleri eklenmiştir.

## Kontroller

- `python -m compileall -q pages src`
- `PYTHONPATH=. pytest -q tests/test_v33_card_dashboard.py tests/test_v23_dense_type_specific_dashboards.py tests/test_v24_placeholders_and_detail_links.py`

Son test sonucu: `17 passed`.
