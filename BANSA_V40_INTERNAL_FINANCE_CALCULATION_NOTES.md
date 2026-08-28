# BANSA V40 · İç Finansman Hesaplama Entegrasyonu

Bu sürüm, V39 kampanya/UI final paketinin üzerine yalnız finansman hesaplama katmanını genişletir. Chatbot ana akışı korunmuş, konut/taşıt/ihtiyaç için BANSA'nın kendi içinde tutar-vade bazlı hesaplama yapması sağlanmıştır.

## Ana kararlar

- Kullanıcıya ana aksiyon olarak **“hesaplama aracını aç”** denmez.
- Resmî banka linkleri arka planda kaynak/provenance olarak tutulur.
- BANSA, kâr payı oranı ve vade üzerinden aylık taksit/toplam geri ödeme hesaplar.
- Sonuçlar **BANSA hesapladı** veya **resmî fiyat tablosundan hesaplandı** şeklinde etiketlenir.
- Nihai oran, masraf, sigorta/kasko, belge ve onay koşullarının banka değerlendirmesine göre değişebileceği notu korunur.

## Konut finansmanı

BANSA içinde hesaplanır:
- Albaraka Türk
- Kuveyt Türk
- Dünya Katılım
- Türkiye Finans
- Vakıf Katılım

Kişiye özel teklif olarak kalır:
- Türkiye Emlak Katılım
- Ziraat Katılım

## Taşıt finansmanı

BANSA içinde hesaplanır:
- Albaraka Türk
- Kuveyt Türk
- Dünya Katılım
- Türkiye Finans
- Vakıf Katılım

Kişiye özel teklif olarak kalır:
- Türkiye Emlak Katılım
- Ziraat Katılım

## İhtiyaç finansmanı

BANSA içinde hesaplanır:
- Albaraka Türk
- Dünya Katılım
- Kuveyt Türk alt ürünleri
- Türkiye Finans
- Vakıf Katılım

Kişiye özel teklif / hesaplamaya alınmayan grup:
- Türkiye Emlak Katılım
- Ziraat Katılım
- Adil Katılım
- Hayat Finans

## Teknik değişiklikler

- `src/bansa_v40_finance_catalog.py` eklendi.
- `src/finance_scenario_projection.py` V40 managed calculation layer ile genişletildi.
- `pages/2_Finansman_Karsilastirmasi.py` scenario tablosu artık V40 hesaplanan sonuçları gösterir; kişiye özel teklifler ayrı expander'da kalır.
- `src/competition_natural_chat.py` chatbot compare/single-bank cevaplarında managed projection kayıtlarını kullanacak şekilde güncellendi.
- `src/competition_fast_router.py` kaynak URL overlay'i V40 kararlarıyla hizalandı.
- `src/v25_accuracy_layer.py` eski taşıt “kural çerçevesi” cevabının sayısal taşıt karşılaştırmasını engellemesi kapatıldı.
- `src/chat_followup_context.py` kampanya bağlamını koruyan final guard eklendi.

## Test edilenler

- `python -m compileall -q pages src`
- `PYTHONPATH=. pytest -q tests/test_v40_internal_finance_calculation.py`
- `PYTHONPATH=. pytest -q tests/test_competition_scenario_projection_v5.py tests/test_competition_v16_housing_mixed_live_compare.py tests/test_v40_internal_finance_calculation.py`
- `PYTHONPATH=. pytest -q tests/test_v39_campaign_ui_refresh.py tests/test_v33_card_dashboard.py tests/test_v24_placeholders_and_detail_links.py tests/test_campaign_compare.py`

Not: Tam test suite bu sandbox ortamında `selenium` ve `sentence_transformers` eksikleri nedeniyle koleksiyon aşamasında kesilir; bu nedenle V40 ile doğrudan ilgili finansman/chatbot/UI ve V39 kampanya-kart regresyon testleri hedefli koşturulmuştur.
