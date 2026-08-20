# BANSA — Katılım Bankacılığı Kampanya ve Finansman Karşılaştırma Sistemi

BANSA, katılım bankalarının resmî web kaynaklarındaki **kampanya** ve **finansman**
içeriklerini toplayan, normalize eden, kaynak izlenebilirliğiyle saklayan ve Streamlit
üzerinden karşılaştırılabilir biçimde sunan açık kaynak bir yarışma projesidir.

## Mimari

```text
Resmî banka web kaynakları
        │
        ├── Kampanya keşif / fetch / sınıflandırma
        │        └── SQLite: data/campaigns.db
        │
        └── Finansman ürün / kural / fiyatlama çıkarımı
                 └── PostgreSQL: bansa şeması
                          ├── standard_products
                          ├── pricing / rule / evidence tabloları
                          └── product_finance_scenarios

Streamlit UI
  ├── Kampanyalar
  ├── Kampanya karşılaştırma
  ├── Finansman karşılaştırma
  └── Chatbot (geliştirme aşamasında)
```

Finansal sayısal karşılaştırmalarda LLM'e hesap yaptırılmaz. Tutar, vade, oran,
taksit ve toplam geri ödeme gibi alanlar yapılandırılmış veri olarak ele alınır.
Strict ortak-senaryo modunda farklı tutar veya farklı vadeye ait bir benchmark
fallback olarak kullanılmaz.

## Güncel finansman güvenlik katmanı

Projede şu korumalar bulunur:

- aynı **finansman tutarı + vade** için exact scenario filtresi,
- doğrulanmamış scenario'ların sayısal sıralamaya girmesini engelleyen contract,
- `VERIFIED / INELIGIBLE / UNVERIFIED` durum modeli,
- canonical ürün verisinin calculator snapshot'ları tarafından ezilmemesi,
- kaynak URL ve kontrol zamanı saklama,
- Türkiye Emlak Katılım için dinamik tutar/vade kabul eden canlı calculator adapterı.

`sync_emlak_katilim.py`, `sync_hayat_finans.py` ve `sync_tom_katilim.py` resmî
calculator entegrasyonlarının doğrulama/snapshot scriptleridir. Dinamik adapter
katmanı banka banka genişletilmektedir; tüm bankalar için dinamik calculator
adapterı tamamlanmış gibi kabul edilmemelidir.

## Veri katmanları

### Kampanyalar — SQLite

`data/campaigns.db` repoda bulunan temizlenmiş çalışma snapshot'ıdır. İçerik,
bankaların kamuya açık resmî sayfalarından üretilen kampanya/ürün kayıtlarından
oluşur. `data/campaign_pages/` resmî sayfa metin snapshot'larını,
`data/standard_products/` ise standart ürün çıktılarının banka bazlı JSON
kayıtlarını içerir.

### Finansman — PostgreSQL

Finansman karşılaştırma ekranının source-of-truth katmanı PostgreSQL'deki `bansa`
şemasıdır. Temel şema `postgresql/schema.sql` içindedir. Mevcut SQLite snapshot'ı
PostgreSQL'e taşımak için:

```powershell
$env:POSTGRES_DSN = "postgresql://postgres:PASSWORD@127.0.0.1:5432/bansa_db"
python -X utf8 .\scripts\migrate_sqlite_to_postgresql.py --replace
```

`postgresql/002_finance_scenarios.sql`, mevcut bir BANSA PostgreSQL kurulumuna
finance scenario tablosu/view'i eklemek için ayrıca çalıştırılabilir. Yeni kurulumda
aynı yapı zaten `schema.sql` içindedir.

> `product_finance_scenarios` bir doğrulama/cache katmanıdır. Yerel PostgreSQL'de
> daha önce üretilmiş tüm runtime scenario satırları Git deposuna taşınmaz; ilgili
> resmî calculator sync/adapter scriptleri ile yeniden üretilebilir. Canonical ürün
> verisi bunlardan bağımsızdır.

## Kurulum

Python 3.11+ önerilir.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`.env.example` yalnızca örnektir. Gerçek PostgreSQL parolasını veya başka bir gizli
bilgiyi Git'e eklemeyin.

## Dashboard'u çalıştırma

PostgreSQL hazırsa Windows'ta:

```powershell
powershell -ExecutionPolicy Bypass -File .\scriptsun_streamlit_postgresql.ps1
```

Script `POSTGRES_DSN` tanımlı değilse parolayı güvenli şekilde ister ve ardından
`Ana_Sayfa.py` üzerinden Streamlit'i başlatır.

Kampanya SQLite kontrol paneli ayrıca doğrudan açılabilir:

```powershell
python -m streamlit run streamlit_app.py
```

## Kampanya canlı güncelleme

Önce dry-run / güvenli kontrol:

```powershell
python -X utf8 .\scriptsun_all_banks_live_update.py --dry-run
```

Normal güncelleme:

```powershell
python -X utf8 .\scriptsun_all_banks_live_update.py
```

Banka bazlı ve banka-özel post-sync scriptleri `scripts/` altında tutulur.

## Finansman calculator scriptleri

```text
scripts/finance_scenarios/common.py
scripts/finance_scenarios/sync_emlak_katilim.py
scripts/finance_scenarios/sync_hayat_finans.py
scripts/finance_scenarios/sync_tom_katilim.py
src/finance_live_contract.py
src/finance_live_adapters/emlak_katilim.py
```

Sync scriptleri varsayılan olarak READ ONLY tasarlanmıştır; veritabanı yazımı
scriptin açık `--write` seçeneği gerektirdiğinde ancak bu seçenekle yapılmalıdır.

## Test

```powershell
python -m pytest
```

Bazı scraping/browser testleri internet bağlantısı veya yerel Chrome/Selenium
ortamı gerektirebilir. Kaynak kodun syntax kontrolü ayrıca CI'da yapılabilir.

## Proje yapısı

```text
BANSA/
├── Ana_Sayfa.py
├── pages/
├── src/
│   ├── scraping/
│   ├── extraction/
│   ├── classification/
│   ├── processing/
│   ├── finance_live_adapters/
│   ├── finance_common_scenario.py
│   └── finance_live_contract.py
├── scripts/
│   └── finance_scenarios/
├── config/
├── data/
│   ├── campaigns.db
│   ├── campaign_pages/
│   └── standard_products/
├── postgresql/
│   ├── schema.sql
│   ├── 002_finance_scenarios.sql
│   └── ER_DIAGRAM.md
├── tests/
├── requirements.txt
├── .env.example
└── LICENSE
```

## Güvenlik ve veri ilkeleri

- Gerçek `.env` ve veritabanı parolaları commit edilmez.
- Finansal değerler kanıt olmadan tahmin edilmez.
- Doğrulanmamış sonuçlar sayısal sıralamaya alınmaz.
- Farklı tutar/vade snapshot'ları exact kullanıcı sorgusunun yerine geçirilmez.
- Kaynak metin ve resmî URL izlenebilirliği korunur.
- Son kullanıcıya ait kişisel veri bu repoda tutulmaz.

## Lisans

Apache License 2.0 — ayrıntılar için `LICENSE` dosyasına bakın.
