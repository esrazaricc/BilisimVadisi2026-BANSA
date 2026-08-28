# BANSA V24 — Placeholder & Detail Link Final

Bu sürüm V23'ün doğruluk sözleşmelerini koruyarak yalnız sunum/izlenebilirlik katmanını güçlendirir.

## Değişiklikler
- Yoğunluk seçimi yapıldıktan sonra görünür tablo hücrelerindeki boş/NaN/None değerler `Belirtilmedi` olarak gösterilir.
- `Belirtilmedi` değerleri sütun doluluk hesabına dahil edilmez; doluluk hâlâ gerçek doğrulanmış içerik üzerinden hesaplanır.
- Finansman ana tablosu, banka detay tablosu ve senaryo karşılaştırması aynı placeholder kuralını kullanır.
- Kampanya ana tablosu, banka detay tablosu ve kampanya detay alanları aynı placeholder kuralını kullanır.
- Kampanya kaynakları yerel canlı kampanya dizini + kampanya detay index'i üzerinden mümkün olan en spesifik resmî detay sayfasına çözülür.
- Finansman ürün kaynakları yerel standart ürün kataloğu / exact-path kaynak konfigürasyonundan ürünün kendi resmî detay sayfasına çözülür.
- Seçili finansman ürünü ve kampanya için ayrıca doğrudan `resmî detay sayfasını aç` butonu bulunur.
- Chatbot kampanya renderer ve market runtime kaynakları da aynı detail-link resolver'ı kullanır.

## Korunan doğruluk kuralı
Dünya Katılım Araç Finansmanı için mevcut doğrulanmış kaynak sözleşmesi korunur: araç değer bantları vade belirlemek için kullanılır; kaynaktan doğrulanmayan `%70/%50/%30/%20` oranları gösterilmez ve `600.000 x %50 = 300.000 TL` türetmesi yapılmaz. Calculator'daki 400.000 TL yalnız hesaplama aracı giriş sınırı olarak tutulur.
