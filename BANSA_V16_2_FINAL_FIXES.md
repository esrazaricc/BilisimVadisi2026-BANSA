# BANSA V16.2 Final Fixes

Bu paket V16.1 üzerine aşağıdaki son regresyon düzeltmelerini ekler:

- Dünya Katılım: `600 bin TL araç için en fazla ne kadar finansman / kaç ay?` gibi doğal sorular araç-değeri sorusu olarak yorumlanır ve genel 48 ay tavanına düşmez. Doğrulanmış bant: %50, yaklaşık 300.000 TL, 36 ay.
- Türkiye Emlak Katılım: aynı amount-aware araç-değeri davranışı; 600 bin TL için %50 / yaklaşık 300.000 TL / 36 ay.
- Güvenlik: `600 bin TL araç finansmanı kullanmak istiyorum` gibi finansman-prensibi belirten ifade otomatik olarak araç değeri sayılmaz.
- Karşılaştırma: yalnız bir bankanın güncel sayısal toplam/aylık sonucu varsa BANSA onu `en düşük/kazanan` ilan etmez; karşılaştırılabilir ikinci güncel sonuç bekler, eski snapshot kullanmaz.
- Vakıf Katılım: güncel resmî 36 ay oranı %3,40 biliniyorsa, exact taksit doğrulanamasa bile oran kullanıcıdan saklanmaz; aylık taksit/toplam ödeme yine uydurulmaz.
- Albaraka Türk: `eğitim finansmanı` açık ürün isteği taşıt veya eğitim kampanyasına kaymaz; Eğitim Finansmanı ürününe gider.

Targeted regression: 18/18 PASS
compileall(src): PASS
