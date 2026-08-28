# BANSA V25 Accuracy-First Jury Final

Bu paket, kullanıcının 27.08.2026 tarihinde paylaştığı jüri test sorularında görülen V25 hata sınıflarına yönelik doğruluk odaklı düzeltmeleri içerir.

Başlıca düzeltmeler:
- Genel “bütün/hangi katılım bankaları” sorguları artık önceki banka bağlamını devralmaz.
- Laptop/bilgisayar gibi açık yeni alışveriş amacı içeren sorular önceki banka karşılaştırmasına zehirlenmez.
- Konut ürün listesi tutar/vade istemeden tüm doğrulanmış ürünleri listeler.
- İki banka arasında genel koşul karşılaştırması, sayısal senaryo zorlamadan çalışır.
- Türkiye Finans sigortalı/sigortasız taşıt oranları yayımlanmış vade tablosuyla karşılaştırılır.
- İlk konut finansman oranı sorusu değer/enerji sınıfı matrisini doğrudan yanıtlar.
- Konut masraf sorusu tahsis/ekspertiz/ipotek tablosuna yönlenir.
- Dünya Katılım 600.000 TL araç değeri örneğinde %50, 300.000 TL azami finansman ve 36 ay kuralı uygulanır.
- Hayat Finans Bana Bunu Al ve T.O.M. Mağazadan Alışveriş vade karşılaştırması tutar istemeden cevaplanır.
- Alışveriş finansmanı kapsamı kullanım amacına göre 9 bankaya genişletilir.
- Laptop finansmanı 9 bankadaki doğrulanmış ilgili ürünleri bulur; eski banka bağlamına düşmez.
- Enerya Karz-ı Hasen takip sorularında konu bağlamı korunur.
- Teknoloji/elektronik kampanyaları tek kampanyaya düşmeden çoklu sonuç verir.

Doğruluk politikası:
- Eksik sayısal veri tahmin edilmez.
- Farklı tutar/vade örnekleri kullanıcının senaryosuymuş gibi ölçeklenmez.
- Ürün uygunluğu ile kâr payı/taksit fiyatlaması birbirinden ayrılır.
- Kullanıcı üç öneri isterse, aynı senaryoda yalnız doğrulanabilen sayıda banka varsa sonuç uydurularak üçe tamamlanmaz.

Hedef regresyon testleri: `tests/test_v25_accuracy_user_regressions.py` ve `tests/test_v25_verified_catalog.py`.
