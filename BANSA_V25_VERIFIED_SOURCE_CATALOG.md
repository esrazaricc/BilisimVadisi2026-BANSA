# BANSA V25 — Resmî Kaynak Kataloğu ve Yoğun Karşılaştırma Arayüzü

Bu sürüm, finansman ve kampanya karşılaştırmalarında düşük doluluklu genel tablo yaklaşımını kaldırır. Kullanıcı arayüzü uygulama koduna gömülü finansal değerlerden değil, `data/verified_catalog/` altındaki resmî kaynak bağlantılı kataloglardan beslenir.

## Finansman kataloğu

- 10 katılım bankası, 274 finansman ürünü.
- Her kayıtta doğrudan resmî ürün / finansman sayfası bağlantısı bulunur.
- Runtime snapshot'ta kaybolmuş ürün metinleri resmî kaynak kayıtlarıyla tamamlanmıştır.
- Finansman türüne göre karar sütunları farklıdır. Konut, taşıt, ihtiyaç, alışveriş, arsa, iş yeri, ticari, gayri nakdi, tarım, leasing ve sürdürülebilir finansman aynı şemaya zorlanmaz.
- Düşük doluluklu opsiyonel sütunlar ana tabloda otomatik bastırılır; ürün detayında mevcut doğrulanmış alanlar korunur.
- Eksik finansal sayı tahmin edilmez veya başka bir bankadan taşınmaz.

## Örnek senaryo

- Varsayılan senaryo 100.000 TL / 36 aydır.
- Aylık taksit, kâr payı ve toplam geri ödeme yalnız resmî banka hesaplama aracı / resmî fiyatlama tablosundan birebir doğrulanmış kayıt varsa gösterilir.
- Aynı ürünün sigortalı/sigortasız, ilk konut/mevcut konut veya 0 km/2. el gibi doğrulanmış varyantları ayrı satır olarak korunur.
- Resmî sonucu olmayan tutar/vade için sayısal tahmin üretilmez.

## Kampanya kataloğu

- 27 Ağustos 2026 tarih kapısı uygulanmıştır; bitiş tarihi geçmiş kampanyalar ana katalogdan çıkarılmıştır.
- Her kampanyada resmî kaynak URL'si, ana fayda ve koşul özeti bulunur.
- Kart/taksit, indirim, puan, yeni müşteri, sigorta ve finansman kampanyaları kendi karar sütunlarıyla gösterilir.
- Taksit/indirim/ödül gibi sayısal faydalarda kampanya başlığı ve sayfanın ilk koşul kanıtı önceliklidir; sayfanın altındaki genel yasal azami değerlerin kampanya faydası sanılması engellenmiştir.

## Veri dosyaları

- `data/verified_catalog/finance_products.csv`
- `data/verified_catalog/verified_scenarios.csv`
- `data/verified_catalog/campaigns_active.csv`
- `data/verified_catalog/finance_coverage.csv`
- `data/verified_catalog/campaign_coverage.csv`

Her kayıt kendi resmî kaynak bağlantısını taşır. Bu katman bir “canlıymış gibi gösterilen” veri değildir; yarışma demosunda güvenilir, tekrar üretilebilir ve kaynak denetlenebilir bir pazar görünümü sağlamak için hazırlanmış doğrulanmış kaynak kataloğudur.
