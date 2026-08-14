# Scripts

## Ana giriş noktaları

- `run_all_banks_live_update.py` - kampanya canlı güncelleme
- `run_standard_products_live_update.py` - standart finansman canlı güncelleme
- `scan_standard_products.py` - ürün discovery/extraction
- `sync_standard_products_to_db.py` - standart ürün SQLite sync
- `sync_finance_rule_engine.py` - rule engine tabloları
- `migrate_sqlite_to_postgresql.py` - PostgreSQL migration
- `audit_postgresql_migration.py` - migration doğrulama
- `run_streamlit_postgresql.ps1` - PostgreSQL ile dashboard başlatma
- `export_public_dataset.py` - GitHub veri seti CSV export

Bu klasörde yarışma geliştirme sürecinde oluşmuş banka bazlı audit/repair scriptleri de bilinçli olarak korunmaktadır. Bunlar geliştirme geçmişi ve yeniden üretilebilirlik için repoda tutulur; ana runtime giriş noktaları yukarıdaki listedir.
