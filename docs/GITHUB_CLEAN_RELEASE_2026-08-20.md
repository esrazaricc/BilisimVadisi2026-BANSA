# GitHub Clean Release — 2026-08-20

Bu paket, kullanıcının tam `bansa_project1` arşivinden hazırlanmıştır ve hem kampanya
hem finansman modüllerini içerir.

## Temizlenenler

- `backups/`, `data/backups/`, loglar ve cache klasörleri
- `__pycache__`, `.pytest_cache`
- `*_before_*` tarihî kaynak/config kopyaları
- eski SQLite backup dosyaları
- kök dizindeki üretilmiş audit/search `.txt` ve `.csv` çıktıları
- gerçek `.env` / yerel credential dosyaları

## Korunanlar

- kampanya scraping / discovery / extraction / classification kodu
- finansman normalizasyonu, PostgreSQL repository ve rule engine
- tüm Streamlit sayfaları
- testler ve banka-özel operasyon scriptleri
- `data/campaigns.db`
- `data/campaign_pages/` ve `data/standard_products/`
- PostgreSQL şeması ve ER diyagramı
- finance live contract ve Türkiye Emlak canlı adapterı

## Eklenen/düzeltilen GitHub dosyaları

- Apache 2.0 `LICENSE`
- güncel `README.md`
- güncel `.env.example`, `.gitignore`, `requirements.txt`
- taşınabilir Windows launcher
- `product_finance_scenarios` şeması ve latest view
- syntax-only GitHub Actions workflow

## Bilinen durum

Yerel PostgreSQL'de daha önce hesaplanmış tüm runtime finance scenario satırlarının
ayrı bir dump'ı kaynak ZIP içinde bulunmadığı için GitHub paketine eklenmemiştir.
Canonical kampanya/ürün snapshot'ı `data/campaigns.db` ile taşınabilir; scenario
satırları resmî calculator sync/adapter katmanı tarafından yeniden üretilecek runtime
kanıt/cache verisi olarak ele alınır.

## Doğrulama

- 304 Python kaynak dosyası syntax kontrolünden geçti.
- SQLite `PRAGMA integrity_check` sonucu `ok`.
- Temel offline test paketi: 22/22 PASS.
- Statik secret taramasında hard-coded parola/API anahtarı bulunmadı.
- Tam pytest çalışması, test ortamında `psycopg` ve `selenium` kurulu olmasını gerektirir; bu bağımlılıklar `requirements.txt` içinde tanımlıdır.
