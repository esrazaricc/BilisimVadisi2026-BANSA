# BANSA - Katılım Bankacılığı Kampanya ve Finansman Analiz Sistemi

**TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması - 2. Senaryo** kapsamında geliştirilen BANSA; katılım bankalarının resmî web sitelerindeki kampanya ve standart finansman ürünlerini toplar, metinleri işler, finansal bilgileri yapılandırır, değişiklikleri takip eder ve Streamlit üzerinden karşılaştırılabilir hale getirir.

> GitHub topic/etiketi: `BilisimVadisi2026`

## Mevcut teknik durum

- Güncel sınıflandırılmış kampanya snapshot'ı: **527**
- Standart finansman ürünü snapshot'ı: **124**
- Kampanya/standart ürün ayrımı yapılmıştır.
- Canlı güncelleme ve değişiklik takibi vardır.
- PostgreSQL için ilişkisel ER şeması ve migration vardır.
- Finansman Karşılaştırması PostgreSQL repository üzerinden okur.
- Chatbot mevcut sürümde ağırlıklı olarak **kural tabanlıdır**; gerçek lokal LLM/ajan entegrasyonu sonraki aşamadır.

## Mimari

```text
Resmî banka siteleri
      |
      v
Scraping / Discovery
(requests + BeautifulSoup + gerektiğinde Selenium)
      |
      v
Metin ön işleme
      |
      +--> Kampanya sınıflandırma + bilgi çıkarımı
      |
      +--> Standart ürün extraction + finance rule engine
      |
      v
SQLite yarışma snapshot'ı -> PostgreSQL ilişkisel model
                                  |
                                  v
                           Streamlit Dashboard
```

Ayrıntı: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Hızlı kurulum

Python 3.12 önerilir.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PostgreSQL 17+ üzerinde `bansa_db` oluşturun ve şemayı kurun:

```sql
CREATE DATABASE bansa_db;
```

```text
\c bansa_db
\i 'C:/path/to/BANSA/postgresql/schema.sql'
```

PostgreSQL bağlantısını tanımlayın ve snapshot'ı taşıyın:

```powershell
$env:POSTGRES_DSN="postgresql://postgres:PAROLA@127.0.0.1:5432/bansa_db"
python -X utf8 .\scripts\migrate_sqlite_to_postgresql.py --replace
python -X utf8 .\scripts\audit_postgresql_migration.py
```

Dashboard:

```powershell
python -m streamlit run .\Ana_Sayfa.py
```

veya parolayı gizli soran yardımcı script:

```powershell
.\scripts\run_streamlit_postgresql.ps1
```

Tam kurulum: [`docs/INSTALLATION.md`](docs/INSTALLATION.md)

## Canlı veri güncelleme

Kampanyalar:

```powershell
python -X utf8 .\scripts\run_all_banks_live_update.py
```

Tek banka:

```powershell
python -X utf8 .\scripts\run_all_banks_live_update.py --bank "Albaraka Türk" --skip-removals
```

Standart finansman ürünleri:

```powershell
python -X utf8 .\scripts\run_standard_products_live_update.py --bank "Albaraka Türk"
```

## Veri seti

- Yarışma SQLite snapshot'ı: `data/campaigns.db`
- CSV/JSON dışa aktarımlar: [`dataset/`](dataset/)
- Veri kapsamı ve açıklar: [`docs/DATASET.md`](docs/DATASET.md)

Dataset'i tekrar üretmek için:

```powershell
python -X utf8 .\scripts\export_public_dataset.py
```

## PostgreSQL / ER diyagramı

- [`postgresql/schema.sql`](postgresql/schema.sql)
- [`postgresql/ER_DIAGRAM.md`](postgresql/ER_DIAGRAM.md)
- [`postgresql/BANSA_ER_DIAGRAM.png`](postgresql/BANSA_ER_DIAGRAM.png)

## NLP yaklaşımı

Mevcut sistem kural tabanlı NLP, metin madenciliği, sınıflandırma, bilgi çıkarımı ve finansal alan normalizasyonu kullanır. Ayrıntı: [`docs/NLP_APPROACH.md`](docs/NLP_APPROACH.md)

## Test / audit

```powershell
python -m pytest
python -X utf8 .\scripts\audit_jury_readiness_v4.py
python -X utf8 .\scripts\audit_standard_products_global_quality.py
```

## Yarışma uyumu ve açık maddeler

- [`docs/COMPETITION_COMPLIANCE.md`](docs/COMPETITION_COMPLIANCE.md)
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
- [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)
- [`GITHUB_UPLOAD_CHECKLIST.md`](GITHUB_UPLOAD_CHECKLIST.md)

Önemli: repo, mevcut ilerlemeyi olduğundan fazla göstermemek için LLM entegrasyonu ve eksik banka kapsamını açıkça **tamamlanmamış** olarak işaretler.

## Lisans

Apache License 2.0 - bkz. [`LICENSE`](LICENSE).
