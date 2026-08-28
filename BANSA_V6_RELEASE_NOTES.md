# BANSA Competition Final V6 — 26 Ağustos 2026

Bu paket V5 üzerine jüri öncesi son hata sınıflarını kapatır.

- Yeni soruda açık ürün ailesi (araç/taşıt/konut/ihtiyaç/motosiklet) eski konuşma ailesini ezer; konut bağlamının araç sorusuna sızması engellendi.
- “sigortalı taşıt kâr payı oranı” fiyatlama niyeti olarak çözülür; sigorta masrafına sapmaz.
- Türkiye Finans konut için 25 Ağustos 2026 güncel resmî fiyatlama tablosu overlay’i eklendi. 36 ay İlk Konut Sigortalı %3,35; Sigortasız %3,81; tahsis %0,50.
- Türkiye Finans taşıt için güncel resmî fiyatlama tablosu eklendi. 36 ay Sigortalı %3,48; Sigortasız %4,08; tahsis %0,50.
- Yeni resmî fiyatlama tablosu, daha eski exact/calculator snapshot oranından daha yeniyse senaryo hesabında yeni tablo önceliklidir.
- Araç finansmanında güncel ve zaman damgalı resmî fiyatlama tablosu varsa istenen finansman tutarı/vade için BANSA deterministik taksit hesabı üretir; eski/untimestamped araç tablolarını “güncel” diye ölçeklemez.
- Ziraat Katılım “Teknosa'da 3 Taksit” kampanyası güncel resmî kaynak overlay’iyle eklendi (11–31 Ağustos 2026).
- Kampanya/marka bulunamadığında aynı bankadan PETLAS vb. alakasız kampanyaya atlama engellendi; güçlü eşleşme yoksa no-match + doğru bankadaki olası eşleşme belirtilir.
- “Schafer 9 Taksit” gibi merchant+taksit soruları finansmana değil kampanya motoruna gider.
- Ziraat kampanya sayfalarındaki kategori/menu sayaç çöpü kullanıcı cevabından temizlenir.
- “ilk konut için” gibi kısa aile sorgularında ham katalog ve “11 ürün daha” dökümü yerine yorumlanmış seçenek özeti gösterilir.
- Güncel fiyatlama tablosu daha yeni ise eski calculator snapshotı “güncel örnek” gibi tekrar gösterilmez.
- Ham UNVERIFIED/teknik hata jüri ekranına verilmez; graceful degradation korunur.

Hedefli final regression: 64 passed.
V6 hotfix acceptance: 10 passed.
