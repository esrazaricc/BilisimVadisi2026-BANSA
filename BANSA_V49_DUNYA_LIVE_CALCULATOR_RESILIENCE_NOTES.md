# BANSA V49 — Dünya Katılım Live Calculator Resilience

## Amaç
Dünya Katılım'ın resmî Konut Finansmanı sayfasında bulunan Finansal Hesaplama aracının, banka DOM/product-code değişikliklerinde BANSA tarafından yanlışlıkla "yok" veya "desteklenmiyor" kabul edilmesini engellemek.

## Değişiklikler
- Dünya Katılım konut live adapter'ı artık `KONUTTUKETICI` / `2ELKONUTTUKETICI` kodlarına zorunlu olarak bağlı değil.
- Güncel resmî formdaki option etiketlerinden konut ürün kodları dinamik keşfedilir.
- `loanForm` / `loanSelect` DOM kimlikleri değişirse semantik form/select fallback'i uygulanır.
- Ürün detay sayfası hazırlanamazsa Dünya Katılım ana sayfasındaki resmî Finansman Hesaplama alanı ikinci kaynak olarak denenir.
- Banka tek bir generic Konut Finansmanı seçeneği yayımlarsa BANSA bunu canlı hesaplama kabiliyeti olarak korur; sırf ikinci varyant ayrı option değil diye bankayı dışarı atmaz.
- Live sonuç yine yalnız `VERIFIED + exact amount + exact maturity + rate + monthly + total` contract'ı geçerse sıralamaya girer.
- Chatbot ve dashboard, live bağlantı geçici olarak doğrulanamazsa artık bankanın hesaplama aracının mevcut/eşlenmiş olduğunu açıkça söyler; eski oranı güncelmiş gibi göstermez.

## Test
- Yeni Dünya ürün kodlarının label'dan keşfi
- Tek generic housing option fallback'i
- Historical product-code compatibility fallback'i
- Mevcut Dünya adapter mapping testi

Not: Banka endpointlerinin gerçek canlı sonucu yarışma/runtime bilgisayarında internet erişimi ile `scripts/test_official_live_calculators_v45.py` veya dashboard üzerinden smoke-test edilmelidir.
