## BANSA V25 — Doğrulanmış Kaynak Kataloğu

Finansman ve kampanya karşılaştırma ekranları artık `data/verified_catalog/` altındaki resmî kaynak bağlantılı katalogları kullanır. Finansman türüne/kampanya türüne göre sütunlar değişir; 100.000 TL / 36 ay örnek senaryosu yalnız birebir doğrulanmış resmî hesaplama kayıtlarını gösterir. Ayrıntılar için `BANSA_V25_VERIFIED_SOURCE_CATALOG.md` dosyasına bakın.

# BANSA V24 — Katılım Bankacılığı Yapay Zekâ Asistanı

BANSA; BDDK kapsamındaki katılım bankalarının resmî web kaynaklarından toplanan kampanya ve finansman verilerini, doğrulanmış finans kuralları, banka hesaplama araçları, hybrid RAG ve yerel Qwen tabanlı doğal dil katmanıyla birleştiren finans asistanıdır.

Bu repository **V24 GitHub-ready** sürümüdür. Canlı demo için üç ana kullanıcı paneli bulunur:

1. **BANSA Asistanı** — doğal, çok turlu chatbot
2. **Finansman Karşılaştırması** — tür bazlı yoğun banka/ürün tabloları + tutar/vade senaryoları
3. **Kampanya Karşılaştırması** — aktif kampanyalar, banka/tür filtreleri ve detay görünümü

## V24'te öne çıkanlar

- Tablolarda görünür fakat kaynağında bulunmayan değerler **`Belirtilmedi`** olarak gösterilir; `NaN`, `None` veya boş/bozuk placeholder kullanıcıya gösterilmez.
- Finansman ve kampanya tablolarında sütunlar **seçilen türe göre** düzenlenir; karar vermede anlamlı ve doğrulanmış alanlar öne alınır.
- Finansman ürünlerinin kaynak bağlantıları mümkün olduğunda ürünün **kendi resmî detay sayfasına** gider.
- Kampanya bağlantıları kategori/kampanyalar ana sayfası yerine mümkün olduğunda **ilgili kampanyanın resmî detay sayfasına** çözülür.
- Seçilen finansman/kampanya için doğrudan resmî detay sayfasını açma aksiyonu vardır.
- Dünya Katılım araç değer bantları yalnız **vade belirleme kuralı** olarak kullanılır; kaynaktan doğrulanmayan `%70/%50/%30/%20` oranları ve `600.000 × %50 = 300.000 TL` türetmesi yapılmaz.
- Calculator giriş limiti, ürünün azami finansman oranı/limiti olarak yorumlanmaz.
- Enerya Karz-ı Hasen gibi ürünlerde yeni açık ürün/entity eski konuşma bağlamını geçersiz kılar.
- Kullanıcı bankaları karşılaştırmak isteyip tutar/vade vermediyse chatbot eksik slotları doğal biçimde sorar.

Ayrıntılı V24 notları: [`BANSA_V24_PLACEHOLDERS_AND_DETAIL_LINKS.md`](BANSA_V24_PLACEHOLDERS_AND_DETAIL_LINKS.md)

---

## Hızlı başlangıç

### Gereksinimler

- Python 3.11 veya 3.12 önerilir
- Windows'ta live Selenium tarayıcı işlemleri için güncel Chrome/Chromium gerekir
- Yerel LLM opsiyoneldir; model servisi yoksa deterministic güvenli fallback kullanılır

### Kurulum

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Uygulamayı aç

```bash
python -m streamlit run Ana_Sayfa.py
```

Windows'ta ayrıca:

```text
RUN_BANSA_FINAL_UI.bat
```

kullanılabilir.

Portable GitHub snapshot'ı `data/campaigns.db`, standart ürün JSON'ları, finance snapshot ve RAG index'ini içerdiği için ilk açılışta veri tabanını yeniden oluşturmak gerekmez.

---

## Ortam ayarları

`.env.example` örnek konfigürasyondur. Gerçek değerleri `.env` içinde tutun; `.env` repository'ye alınmaz.

Örnek local naturalizer ayarları:

```env
BANSA_FAST_NATURALIZER_ENABLED=1
BANSA_FAST_NATURALIZER_TIMEOUT_SECONDS=0.8
BANSA_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1
BANSA_LOCAL_LLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
```

Naturalizer cevap yolunu uzun süre bloklamaz; model hazır değilse BANSA doğrulanmış deterministic cevaba geri döner.

---

## Temel mimari

```text
Kullanıcı
   ↓
Conversation State + Intent / Entity / Slot Resolver
   ↓
Tool / Route Kararı
   ├── Finansman Engine
   ├── Live Calculator Adapter'ları
   ├── Kampanya Engine
   └── Product / Campaign RAG
           ↓
      Verified Fact Pack
           ↓
    Local Qwen Naturalizer
           ↓
 Numeric / Grounding Verifier
           ↓
 Kaynaklı ve doğal BANSA cevabı
```

### Kullanılan başlıca yöntem ve modeller

- Python, Streamlit
- Requests, BeautifulSoup, Selenium
- SQLite + PostgreSQL desteği
- Structure-aware semantic chunking
- `Qwen3-Embedding-0.6B` dense embedding mimarisi
- BM25 + dense retrieval + Reciprocal Rank Fusion
- RAG + evidence verification
- Local Qwen naturalizer / on-prem LLM mimarisi
- Deterministic finance engine
- Official live calculator adapter'ları
- Exact scenario matching
- Freshness gate
- Verified-subset ranking
- Amount semantics ve conversation-state yönetimi

Finansal sayıların kaynağı LLM değildir. Kâr payı, vade, taksit, toplam geri ödeme, ücret ve kampanya sayıları doğrulanmış BANSA veri/tool katmanından gelir.

---

## Repository yapısı

```text
BANSA/
├── Ana_Sayfa.py                 # Ana Streamlit giriş noktası
├── pages/                       # Kullanıcı ve yardımcı Streamlit panelleri
├── src/                         # Chatbot, finance, RAG, scraper ve resolver katmanları
├── config/                      # Banka/source konfigürasyonları
├── data/
│   ├── campaigns.db             # Portable kampanya snapshot'ı
│   ├── standard_products/       # Doğrulanmış standart ürün katalogları
│   ├── runtime/                 # Portable finance snapshot
│   └── rag/                     # Hazır RAG index'i
├── postgresql/                  # PostgreSQL şema/migration araçları
├── scripts/                     # Crawl, sync, audit ve bakım scriptleri
├── tests/                       # Regresyon testleri
├── .streamlit/                  # UI tema/navigasyon ayarları
├── requirements.txt
└── .env.example
```

---

## Veri ve kaynak bağlantıları

V24'te kaynak linkleri `src/source_link_resolver.py` tarafından çözülür.

- Kampanya için banka + kampanya başlığı + canlı campaign index kullanılır.
- Generic `/kampanyalar` / `/kart-kampanyalari` gibi liste sayfaları yerine güçlü eşleşme varsa resmî detail URL tercih edilir.
- Finansman ürünlerinde standart ürün kataloğundaki kaynak ve exact source path'ler kullanılır.
- URL tahmin edilmez; yalnız yerel doğrulanmış source verisi kullanılır.

---

## Test

V24 GitHub paketi hazırlanırken aşağıdaki güncel davranış testleri çalıştırıldı:

```bash
python -m pytest -q \
  tests/test_v21_source_enerya_dense_ui.py \
  tests/test_v22_final_demo_dashboard.py \
  tests/test_v23_dense_type_specific_dashboards.py \
  tests/test_v24_placeholders_and_detail_links.py
```

Sonuç: **27 passed**.

Syntax kontrolü:

```bash
python -m compileall -q Ana_Sayfa.py app.py streamlit_app.py src pages
```

GitHub Actions ayrıca her push/PR'da hafif syntax kontrolü çalıştırır.

---

## Canlı veri güncelleme

Önce dry-run önerilir:

```powershell
python -X utf8 .\scripts\run_all_banks_live_update.py --dry-run
```

İlk canlı test:

```powershell
python -X utf8 .\scripts\run_all_banks_live_update.py --skip-removals
```

Normal güncelleme:

```powershell
python -X utf8 .\scripts\run_all_banks_live_update.py
```

---

## Güvenlik ve GitHub

- `.env`, parola ve token commit edilmez.
- `data/runtime/chat_history.sqlite` repository dışında tutulur.
- Log, backup, audit çıktıları `.gitignore` ile dışarıda tutulur.
- Portable demo için gerekli doğrulanmış snapshot/index dosyaları repository'de tutulur.
- Bu pakette GitHub'ın 100 MB tek dosya sınırını aşan dosya bulunmaz; mevcut snapshot için Git LFS zorunlu değildir.

Repository'yi ilk kez yayımlamak için [`GITHUB_SETUP.md`](GITHUB_SETUP.md) dosyasına bakın.
