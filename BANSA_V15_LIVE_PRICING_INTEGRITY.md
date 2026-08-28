# BANSA V15 — Live Pricing Integrity & Evidence Separation

## Amaç
V15, finansal fiyatlama ile ürün uygunluk kurallarını kesin biçimde ayırır.

### Kaynak önceliği
1. Resmî canlı hesaplama aracı (adapter mevcutsa)
2. Güncel resmî statik fiyatlama tablosu
3. Aynı oranı güncel resmî tablo tarafından tekrar doğrulanmış exact calculator snapshot
4. Son 72 saat içindeki exact portable calculator snapshot
5. Ürün/araç-değeri uygunluk kuralı — yalnız uygunluk/vade/azami oran için

Eski snapshot'lar audit için saklanır; güncel kazanan sıralamasında kullanılmaz.

## Kritik düzeltmeler
- Dünya Katılım `%70/%50/%30/%20` tablosu yalnız araç değeri uygunluğu olarak kullanılır; fiyatlama değildir.
- Dünya genel Araç Finansmanı tablosu ayrı motosiklet ürünü doğrulanmadan motosiklete uygulanmaz.
- Dünya/Emlak/Vakıf/Albaraka adapter'ları karşılaştırmada live-first denenir.
- Vakıf Katılım güncel 36 ay taşıt oranı `%3,40`; eski `%3,19` calculator snapshot'ı artık güncel sonuç sayılmaz.
- Vakıf genel azami taşıt vadesi 48 ay olarak güncellenmiştir.
- Türkiye Emlak Katılım araç-değeri bantları eligibility olarak tutulur; taksit hesabında kullanılmaz.
- Taşıt statik oranlarından genel annüite formülü ile aylık taksit türetme kapatıldı. Banka calculator formülü doğrulanmadan ödeme rakamı üretilmez.
- Explicit `kampanya` soruları eski finans/motosiklet context'ini sıfırlar.
- Teknosa follow-up (`Ne zamana kadar?`, `Şartı ne?`) aynı kampanyada kalır.
- Vatan kampanyasında başlıktaki `3 Taksit`, related-card kaynaklı yanlış `5 taksit` alanından üstün tutulur.
- Comparison follow-up state; en düşük aylık, ikinci sıra, ilk üç ve banka farkı taleplerini finans karşılaştırması içinde tutar.

## Test
`tests/test_competition_pricing_integrity_v15.py`: 6/6 PASS.
`python -m compileall -q src`: PASS.

Not: Selenium ve sentence-transformers isteyen opsiyonel testler, bu çalışma ortamında paketler kurulu değilse collection aşamasında çalışmayabilir.
