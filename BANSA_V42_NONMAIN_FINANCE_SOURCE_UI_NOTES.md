# BANSA V42 — Non-Main Finance Source UI & Coverage Refresh

## Amaç

V41 sürümündeki çalışan finansman hesaplama, chatbot, kampanya ve kart mimarisi korunarak; konut/taşıt/ihtiyaç dışındaki finansman türleri için kullanıcı dostu kaynak/kapsam ekranı eklendi.

## Korunan alanlar

- V41 iç finansman hesaplama motoru korunmuştur.
- Konut, taşıt ve ihtiyaç finansmanı için tutar/vade bazlı senaryo hesabı korunmuştur.
- Chatbot, kampanya karşılaştırması ve kart karşılaştırması akışlarına dokunulmamıştır.

## Yeni UI davranışı

Konut, taşıt ve ihtiyaç finansmanı dışındaki finansman türlerinde:

- Kullanıcıdan `Tutar (TL)` alınmaz.
- Tutar/vade senaryosu üretilmez.
- Ekran, resmî kaynaklı ürün/kapsam listesine dönüşür.
- Detay tabloda tutar, oran, taksit ve masraf odaklı kolonlar gizlenir.
- “Kişiye özel teklif” yerine kaynak doğrulama dili kullanılır.
- Net ürünü bulunan bankalar “Kaynaklı ürünler ve kapsam” tablosunda gösterilir.
- Net ürün bulunamayan bankalar ayrı ve kapalı bir “Açık kaynakta net ürün bulunamayan bankalar” bölümünde tutulur.

## Yeni doğrulanan ürünler

Aşağıdaki satırlar bankaya özel arama alanından çıkarılıp doğrulanmış ürün/kaynak statüsüne alındı:

1. Albaraka Türk — Sürdürülebilir Finans Ürünleri
2. Dünya Katılım — Taksitli Ticari Finansman / İş yeri kapsamı
3. Dünya Katılım — Leasing / Finansal Kiralama
4. Dünya Katılım — Sürdürülebilir Finansman Çözümleri
5. Türkiye Finans — Hızlı Finansman Çözümleri

## Bilerek değiştirilmeden bırakılanlar

Resmî ürün sayfası veya kategoriyle birebir eşleşen kaynak doğrulanamayan satırlar hesaplanabilir/doğrulanmış ürün olarak işaretlenmedi. Bunlar kullanıcıya “kişiye özel teklif” gibi sunulmaz; yalnızca kaynak doğrulaması bekleyen bankalar bölümünde tutulur.

## Test

- `python -m compileall -q pages src`
- `PYTHONPATH=. pytest -q tests/test_v40_internal_finance_calculation.py tests/test_v39_campaign_ui_refresh.py tests/test_v33_card_dashboard.py tests/test_v24_placeholders_and_detail_links.py tests/test_campaign_compare.py tests/test_campaign_chatbot_integration.py`

Sonuç: 42 passed.
