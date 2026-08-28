# BANSA V38 Finance UI Revision

Bu sürümde yalnız finansman karşılaştırması kullanıcı deneyimi revize edildi; kampanya, kart, chatbot ve mevcut doğrulama motoru korunmuştur.

## Yapılan değişiklikler

- Finansman sayfasında büyük ürün karşılaştırma tablosu varsayılan olarak gizlendi.
- Kullanıcıya `Detaylı ürün karşılaştırma tablosunu göster` başlıklı açılır alan eklendi.
- Sabit `100.000 TL / 36 ay` görünümü yerine kullanıcı tarafından değiştirilebilir `Finansman türü + Tutar + Vade` senaryo ekranı eklendi.
- Sayısal taksit karşılaştırması yalnız birebir doğrulanmış veya güvenli BANSA projeksiyonu üretilebilen ürünler için gösterilir.
- Sayısal sonucu doğrulanamayan ürünler ayrı bir `Kişiye özel teklif gerektiren bankalar` alanına taşındı.
- Finansman dashboard verilerindeki kullanıcıya sert görünen `Bilgi yok` ibareleri kaldırıldı.
- Kamuya açık olmayan finansman oranı, limit, masraf ve vade alanları için kullanıcı dostu `Kişiye özel teklif — banka ile görüşün` dili kullanıldı.
- Eski 100.000 TL / 36 ay snapshotı tamamen silinmedi; denetim amacıyla kapalı referans bölümüne alındı.

## Kontrol

- `python -m compileall -q pages src` başarılı.
- Finansman sayfası ve finansman dashboard CSV dosyalarında `Bilgi yok` ibaresi kalmadı.
- İlgili dashboard/regresyon testleri: `tests/test_v24_placeholders_and_detail_links.py` ve `tests/test_v33_card_dashboard.py` başarılı.
