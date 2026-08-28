# BANSA V33 — Finansman + Kampanya + Kart Karşılaştırması

Kontrol tarihi: 2026-08-27

## Kapsam
- BDDK'nın güncel listesinde yer alan 10 katılım bankası.
- 12 finansman dashboard grubu.
- 18 kampanya kategorisi.
- Yeni: statik, kaynaklı Kart Karşılaştırması dashboardu.

## Kart Karşılaştırması
- Kredi kartı, banka kartı, sanal/dijital kart, premium kart, ticari ve tarım kartları.
- Yıllık kart ücreti / aidat.
- Kart programı ve ödül yapısı.
- Taksit / vade farksız özellikleri.
- Temassız, QR/NFC, sanal kart, ek kart, internet ve yurt dışı kullanımı.
- Resmî kaynak ve kontrol tarihi.

## Doğruluk İlkesi
- Runtime scraping yok.
- Doğrulanmayan özellik Var/Yok veya 0 TL diye tahmin edilmez.
- Eksik değer: `Bilgi yok – resmî kaynakta yayımlanmamış`.
- Kart ürünü yayımlamayan banka evrenden çıkarılmaz; durum açıkça gösterilir.
