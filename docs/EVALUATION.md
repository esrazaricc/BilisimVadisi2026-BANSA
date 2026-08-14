# Değerlendirme / Kalite Doğrulama

Projede banka ve ürün bazlı audit scriptleri, değişiklik takibi ve unit/integration testleri bulunur.

Öne çıkan kontroller:

- Kampanya sınıflandırma doğruluğu ve karşılaştırma uygunluğu
- Finansal bilgi çıkarımı (kâr payı, tutar, vade, taksit, masraf)
- Standart ürün discovery eksiksizliği
- Tutar-vade ve kategori-taksit semantik ayrımı
- Cross-product contamination kontrolleri
- PostgreSQL migration satır sayısı/audit kontrolü
- Kaynak URL ve `source_text` kanıtlarının korunması

Komutlar:

```powershell
python -m pytest
python -X utf8 .\scripts\audit_jury_readiness_v4.py
python -X utf8 .\scripts\audit_standard_products_global_quality.py
python -X utf8 .\scripts\audit_postgresql_migration.py
```

Not: Banka siteleri zaman içinde değişebildiği için canlı scraper audit sonuçları tarih bağımlıdır.
