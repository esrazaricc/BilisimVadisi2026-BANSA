# BANSA V23 — Dense Type-Aware Dashboard

## Amaç
Canlı demo tablolarında NaN / None / Belirtilmedi / Doğrulanmadı tekrarlarını kaldırmak ve her finansman/kampanya türü için yalnız karar vermede anlamlı, gerçek veri doluluğu yüksek sütunları göstermek.

## Finansman dashboard
- Aileye özel sütun profili: konut, taşıt, ihtiyaç, alışveriş, arsa, iş yeri, ticari, gayri nakdi, tarım, leasing vb.
- %100 boş veya düşük doluluklu gereksiz sütunlar otomatik gizlenir.
- Eksik hücreler boş gösterilir; NaN/None/Belirtilmedi yazılmaz.
- `finance_rules_json.display_metadata` içindeki mevcut doğrulanmış limit/vade/para birimi/kullanım amacı/ödeme yapısı/devlet desteği/özel koşullar UI'a taşınır.
- Dünya Katılım taşıtta eski yüzdesel finansman oranı geri getirilmez.
- Senaryo tablosunda eksik sayısal sonuçlar hücre hücre tekrarlanmaz; tek `Durum` alanı kullanılır.
- Tablo doluluk yüzdesi ve gösterilen karar sütunu sayısı dashboard metric'i olarak gösterilir.

## Kampanya dashboard
- Kampanya türüne özel sütun profilleri: Kart/Taksit, İndirim, Puan, Yeni Müşteri, Finansman kampanyaları, Sigorta vb.
- Kaynaktan türetilen `Ana Fayda` kolonu (taksit / indirim / puan / ödül / finansman tutarı-vade) ile tablo okunabilirliği artırılır; yeni finansal sayı üretilmez.
- Seçilen kategoriye göre düşük doluluklu alanlar gizlenir.
- NaN/None/Belirtilmedi hücreleri gösterilmez.
- Tüm aktif eşleşmeler ana tabloda kalır, banka detay görünümü korunur.

## Güvenlik
- UI katmanı finansal hesap yapmaz.
- Kaynakta olmayan finansal değer tahmin edilmez.
- Calculator giriş limiti ürün finansman oranı/ürün limiti olarak yorumlanmaz.
- Doğrulanmış scenario sonuçları ve mevcut structured metadata dışında sayı üretilmez.

## Test
- V16.4 + housing + V17 + V18 + V21 + V22 + V23 + live campaign + pricing guardrail kritik grubu: 64 PASS.
- compileall: PASS.
- Tam tarihsel test paketi bu ortamda Selenium ve sentence-transformers bağımlılıkları eksik olduğu için collection aşamasında çalıştırılamadı; ayrıca bazı eski tarihsel testler artık bilinçli olarak değiştirilen sözleşmeleri bekliyor.
