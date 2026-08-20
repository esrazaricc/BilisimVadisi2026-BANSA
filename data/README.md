# BANSA data snapshot

Bu klasörde yalnızca GitHub için tutulması amaçlanan, kamuya açık resmî banka
kaynaklarından üretilmiş çalışma snapshot'ları yer alır.

- `campaigns.db`: kampanya ve standart ürünlerin SQLite çalışma snapshot'ı.
- `campaign_pages/`: fetch edilen resmî sayfaların metin snapshot'ları.
- `standard_products/`: banka bazlı normalize edilmiş standart ürün JSON çıktıları.
- `campaign_page_index.json`, `discovered_campaign_pages.json`: keşif/index verileri.

`backups/`, `logs/`, geçici audit raporları ve kişisel/gizli ortam dosyaları GitHub
sürümüne dahil edilmez.
