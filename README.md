# BANSA  
## Doğrulanabilir Katılım Bankacılığı Yapay Zekâ Ajanı

> **Resmî banka verisini, yapılandırılmış ve doğrulanabilir finansal bilgiye; ardından kullanıcı odaklı karar desteğine dönüştüren hibrit yapay zekâ platformu.**

**TEKNOFEST 2026 — Yapay Zekâ Dil Ajanları Yarışması / 2. Senaryo**  
**Etiket:** `BilisimVadisi2026`

---

## BANSA Nedir?

BANSA; BDDK kapsamındaki katılım bankalarının resmî web kaynaklarında yayımlanan:

- finansman ürünlerini,
- finansman kampanyalarını,
- kart kampanyalarını,
- kart özelliklerini,
- vade ve kâr payı bilgilerini,
- masraf ve ücretleri,
- avantaj ve ödülleri,
- müşteri koşullarını

otomatik olarak toplayan, temizleyen, standartlaştıran, yapılandıran ve karşılaştırılabilir hale getiren **yerel yapay zekâ destekli finansal karar destek platformudur**.

BANSA yalnızca bir chatbot değildir.

Sistem;

**veri toplama → veri temizleme → normalizasyon → bilgi çıkarımı → veri doğrulama → Hybrid RAG → deterministik finans motoru → agent orchestration → grounding verification → dashboard/chatbot**

katmanlarından oluşan uçtan uca bir mimariye sahiptir.

---

# Temel Tasarım Prensibi

> ## Yapay zekâ finansal gerçeği üretmez.  
> ## Doğrulanmış finansal gerçeği anlar ve kullanıcıya anlatır.

LLM;

- kullanıcı niyetini anlamak,
- banka / ürün / tutar / vade gibi alanları çıkarmak,
- konuşma bağlamını yönetmek,
- uygun aracı seçmek,
- doğrulanmış sonucu doğal Türkçe ile sunmak

için kullanılır.

LLM;

- kâr payı oranı uydurmaz,
- taksit hesaplamaz,
- toplam geri ödeme uydurmaz,
- kaynak URL üretmez,
- doğrulanmamış bankaları “en iyi” diye sıralamaz.

Finansal gerçeklik **deterministik ve doğrulanmış BANSA araçlarından** gelir.

---

# Sistem Mimarisi

```text
                    RESMÎ BANKA KAYNAKLARI
                             │
                             ▼
                    VERİ TOPLAMA KATMANI
             Requests · BeautifulSoup · Selenium
                             │
                             ▼
                TEMİZLEME + NORMALİZASYON
                             │
                             ▼
                   STRUCTURED EXTRACTION
                             │
                             ▼
                POSTGRESQL / VERIFIED DATA
                             │
             ┌───────────────┴───────────────┐
             │                               │
             ▼                               ▼
        HYBRID RAG                     FINANCE ENGINE
             │                               │
 Structure-Aware Chunking              Eligibility Rules
 Semantic Chunking                     Amount Semantics
 Qwen3 Embedding                       Verified Pricing
 BM25                                  Live Calculators
 RRF                                   Deterministic Calc.
 Qwen3 Reranker                        Exact Scenario
 Evidence Pack                         Verified Ranking
 Retrieval Verifier
             │                               │
             └───────────────┬───────────────┘
                             ▼
                    QWEN LOCAL AGENT
                             │
                             ▼
                   VERIFIED FACT PACK
                             │
                             ▼
               NUMERIC / GROUNDING VERIFIER
                             │
                             ▼
                    KAYNAKLI SONUÇ
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         FİNANSMAN       KAMPANYA          KART
       KARŞILAŞTIRMA   KARŞILAŞTIRMA   KARŞILAŞTIRMA
              └──────────────┼──────────────┘
                             ▼
                 KULLANICI ODAKLI DENEYİM
```

---

# 1. Resmî Veri Toplama

BANSA veri evrenini rastgele banka listesinden oluşturmaz.

Sistem, BDDK Katılım Bankaları kapsamındaki **10 bankayı** temel alır:

- Adil Katılım
- Albaraka Türk
- Dünya Katılım
- Hayat Finans
- Kuveyt Türk
- T.O.M. Katılım
- Türkiye Emlak Katılım
- Türkiye Finans
- Vakıf Katılım
- Ziraat Katılım

Veri toplama katmanında:

- `requests`
- `BeautifulSoup`
- `Selenium`
- dinamik URL discovery
- JavaScript/AJAX sayfa işleme
- banka bazlı scraper/adaptör yaklaşımı

kullanılır.

Her bankanın web yapısı farklı olduğu için tek bir kırılgan “universal scraper” yerine:

```text
Ortak Scraping Contract
        +
Banka Bazlı Discovery / Fetch Adaptörleri
```

kullanılmıştır.

---

# 2. Safe Sync ve Kaynak Değişikliklerine Dayanıklılık

Bir banka sayfasına geçici olarak erişilememesi, ürünün veya kampanyanın silindiği anlamına gelmez.

BANSA bu nedenle **Safe Removal** yaklaşımı kullanır.

```text
Kaynak erişilemedi
        ↓
Discovery doğrulanamadı
        ↓
Mevcut veri hemen silinmez
        ↓
Yeni URL / redirect araştırılır
        ↓
Kaynak yeniden doğrulanır
```

Sistem ayrıca:

- source URL,
- kontrol zamanı,
- içerik hash'i,
- oluşturulma,
- değişiklik,
- kaldırılma,
- yeniden aktif olma

gibi değişimleri izleyebilir.

---

# 3. Temizleme ve Normalizasyon

Banka sitelerinden gelen ham HTML doğrudan modele verilmez.

Öncelikle;

- menü,
- footer,
- breadcrumb,
- cookie metinleri,
- benzer ürün kartları,
- alakasız kampanya alanları,
- calculator widget gürültüsü

temizlenir.

Ardından Türkçe normalizasyon uygulanır.

Örneğin:

```text
Vakıf
Vakıf Katılım
Vakıf Katılım Bankası
        ↓
VAKIF_KATILIM
```

ve:

```text
araç
taşıt
otomobil
binek
        ↓
ARAÇ
```

Aynı şekilde:

```text
100.000 TL
100000 TL
100.000,00 TL
₺100.000
```

ortak sayısal temsile dönüştürülebilir.

---

# 4. Structured Information Extraction

Ham banka metinlerinden karar vermede kullanılabilecek bilgiler yapılandırılmış alanlara dönüştürülür.

Örnek alanlar:

```text
bank
product_family
product_name
profit_share_rate
maximum_maturity_months
financing_amount
financing_ratio
monthly_installment
total_payment
allocation_fee
appraisal_fee
mortgage_fee
campaign_start_date
campaign_end_date
installment_count
benefit
audience
eligibility
source_url
last_checked
```

Kritik finansal ayrım:

```text
ELIGIBILITY ≠ PRICING
```

Örneğin:

- azami finansman oranı,
- araç değer limiti,
- maksimum vade

**uygunluk kurallarıdır.**

Buna karşılık:

- kâr payı,
- aylık taksit,
- toplam geri ödeme

**fiyatlama verileridir.**

BANSA bu iki veri sınıfını birbirine karıştırmaz.

---

# 5. Veri Omurgası

Projenin ana veri omurgasında PostgreSQL ve portable SQLite yaklaşımı birlikte kullanılmaktadır.

### PostgreSQL

Production/source-of-truth katmanıdır.

Örnek veri yapıları:

- banks
- source_pages
- source_snapshots
- campaigns
- campaign benefits
- campaign audiences
- campaign installment terms
- standard products
- finance rules
- pricing tiers
- fees
- verified finance evidence
- change history

### Portable Runtime

Yarışma ve offline demo güvenilirliği için doğrulanmış veriler SQLite snapshot'larına aktarılabilir.

Bu sayede runtime sırasında:

- PostgreSQL zorunlu değildir,
- veritabanı parolası zorunlu değildir,
- uzak sunucu bağlantısı zorunlu değildir.

---

# Mevcut Veri Ölçeği

V49 paketinde:

| Veri Katmanı | Ölçek |
|---|---:|
| BDDK banka evreni | **10 banka** |
| Doğrulanmış standart finansman snapshot'ı | **274** |
| Doğrulanmış finansman senaryosu | **57** |
| RAG dokümanı | **740** |
| RAG chunk | **2.397** |
| Semantic chunk | **858** |
| Dense vector | **2.328** |
| Embedding boyutu | **1024** |
| Kart karşılaştırma kaydı | **56** |
| Test dosyası | **176** |
| Test fonksiyonu | **1.000+** |

---

# 6. Structure-Aware Chunking

BANSA klasik sabit uzunlukta chunking yaklaşımını temel yöntem olarak kullanmaz.

Finansal belgelerde:

- oran,
- vade,
- koşul,
- ücret,
- kampanya avantajı

aynı başlık veya tablo içerisinde birbirine bağlı olabilir.

Örneğin sabit karakter bölme:

```text
Konut Finansmanı
Azami Vade:
--------- CHUNK BÖLÜNDÜ ---------
120 ay
```

gibi anlam kaybına neden olabilir.

BANSA bunun yerine:

## Structure-Aware Chunking

kullanır.

Korunan yapılar arasında:

- HTML başlıkları,
- ürün bölümleri,
- tablolar,
- avantajlar,
- koşullar,
- ücretler,
- başvuru bölümleri,
- kaynak metadata

bulunur.

Büyük yapısal bloklarda ayrıca **semantic chunking** uygulanır.

---

# 7. Hybrid RAG

BANSA yalnızca vector search kullanmaz.

Retrieval pipeline:

```text
Structure-Aware Chunking
          ↓
Semantic Split
          ↓
 ┌────────┴────────┐
 ▼                 ▼
Dense Search      BM25
Qwen3 Embedding   Exact Keyword
 └────────┬────────┘
          ↓
          RRF
          ↓
   Qwen3 Reranker
          ↓
    Evidence Pack
          ↓
 Retrieval Verifier
```

---

## Dense Retrieval

Model:

```text
Qwen/Qwen3-Embedding-0.6B
```

Embedding boyutu:

```text
1024
```

Dense retrieval semantik benzerliği yakalar.

Örneğin:

```text
"ev almak için finansman"
```

ile:

```text
"konut finansmanı"
```

arasındaki anlamsal yakınlığı değerlendirebilir.

---

## BM25

Finans alanında bazı ifadelerde tam kelime eşleşmesi kritik öneme sahiptir.

Örneğin:

- banka isimleri,
- kart isimleri,
- kampanya isimleri,
- TROY,
- ürün adları,
- özel finansman isimleri.

Bu nedenle dense retrieval yanında **BM25 lexical retrieval** kullanılır.

---

# RRF — Reciprocal Rank Fusion

Dense retrieval ve BM25 farklı skor sistemlerine sahiptir.

BANSA sonuçları doğrudan toplamak yerine:

```text
Reciprocal Rank Fusion
```

ile sıralama seviyesinde birleştirir.

Bu sayede:

> semantic recall + lexical precision

aynı retrieval pipeline içerisinde kullanılabilir.

---

# Qwen3 Reranker

İlk retrieval sonuçları:

```text
Qwen/Qwen3-Reranker-0.6B
```

ile yeniden sıralanır.

Reranker;

- banka,
- ürün,
- vade,
- tutar,
- koşul,
- kampanya,
- eligibility

ilişkisini query ile birlikte değerlendirir.

---

# Evidence Pack

Retrieval'dan gelen bütün belgeler LLM'e gönderilmez.

En güçlü ve en alakalı kanıtlardan **Evidence Pack** oluşturulur.

Evidence Pack içerisinde:

- kaynak,
- belge,
- chunk,
- retrieval sonucu,
- provenance bilgisi

korunur.

---

# Retrieval Verifier

Bir dokümanın retrieval'da üst sırada çıkması tek başına yeterli değildir.

BANSA Retrieval Verifier;

- query coverage,
- source type,
- grounding policy,
- lexical/dense agreement,
- evidence kalitesi

gibi kontroller uygular.

Sonuç:

```text
PASS
RETRIEVE_MORE
ABSTAIN
```

olabilir.

Yeterli kanıt yoksa sistem **cevap üretmemeyi tercih edebilir.**

---

# 8. RAG Finansal Güvenlik Politikası

Banka hesaplama araçlarında görülen dinamik sayılar normal RAG kanıtı olarak kullanılmaz.

Örneğin bir hesaplama widget'ında:

```text
100.000 TL
36 ay
%3,20
```

görülmesi, `%3,20` değerinin bütün müşteriler için bankanın genel güncel oranı olduğu anlamına gelmez.

Bu nedenle calculator kaynakları gerektiğinde:

```text
live_only
```

olarak işaretlenir.

Finansal hesaplamanın sahibi RAG değil:

```text
Finance Engine / Live Calculator Adapter
```

katmanıdır.

---

# 9. Deterministic Finance Engine

BANSA'nın en önemli güvenlik prensiplerinden biri:

> **Finansal hesaplama LLM'e bırakılmaz.**

Finans motoru;

- tutar,
- vade,
- kâr payı,
- uygunluk,
- finansman oranı,
- aylık ödeme,
- toplam geri ödeme,
- ücretler

için doğrulanmış veri ve deterministik hesaplama kullanır.

---

# Exact Scenario Matching

Bir sonuç:

```text
100.000 TL / 36 ay
```

için doğrulanmışsa:

```text
100.000 TL / 24 ay
```

sonucu yerine kullanılamaz.

BANSA:

```text
exact amount
+
exact maturity
```

eşleşmesine öncelik verir.

---

# Maturity Interpolation Yapılmaz

Örneğin:

```text
24 ay → %3,20
48 ay → %3,80
```

bilgisi varsa BANSA:

```text
36 ay → yaklaşık %3,50
```

diye finansal oran uydurmaz.

---

# Amount Semantics

Aşağıdaki iki cümle aynı değildir:

```text
"500 bin TL'lik araç alacağım."
```

ve:

```text
"500 bin TL araç finansmanı istiyorum."
```

İlkinde:

```text
ASSET_VALUE
```

İkincisinde:

```text
REQUESTED_FINANCING_AMOUNT
```

semantiği bulunur.

BANSA araç değerini finansman talebi gibi yorumlamamak için bu ayrımı ayrıca takip eder.

---

# Calculator Constraint ≠ Product Constraint

Bir bankanın hesaplama aracının:

```text
50.000 – 1.000.000 TL
```

girdi kabul etmesi;

ürünün gerçek azami finansman limitinin 1.000.000 TL olduğu anlamına gelmez.

BANSA calculator input limitini ürün finansman limiti olarak kullanmaz.

---

# Verified Subset Ranking

BANSA bütün bankaları kör şekilde sıralamaz.

Önce aynı senaryoda gerçekten karşılaştırılabilir sonuçları belirler.

```text
VERIFIED      → sıralamaya katılabilir
UNVERIFIED    → sıralamaya katılmaz
INELIGIBLE    → sıralamaya katılmaz
```

Daha sonra:

- en düşük kâr payı,
- en düşük aylık taksit,
- en düşük toplam geri ödeme

gibi öneriler yalnız doğrulanmış karşılaştırılabilir küme üzerinden oluşturulur.

---

# 10. Resmî Banka Hesaplama Araçları

BANSA uygun bankalarda resmî finansal hesaplama araçlarından exact senaryo sonucu almaya çalışır.

Yaklaşım:

```text
Kullanıcı tutar + vade girer
        ↓
Resmî Calculator Adapter
        ↓
Exact scenario doğrulama
        ↓
VERIFIED ise kullan
        ↓
Değilse güvenli fallback
```

Live calculator sonucu yalnız şu alanlar senaryoyla uyumluysa kabul edilir:

- tutar,
- vade,
- kâr payı,
- aylık taksit,
- toplam geri ödeme.

Bir banka hesaplama aracı geçici olarak yanıt vermezse eski oran kullanıcıya “güncel” diye sunulmaz.

---

# 11. Local Agent ve Tool Orchestration

Ana yerel LLM hedefi:

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Modelin görevi finansal gerçeği üretmek değil, **hangi doğrulanmış aracın kullanılacağını seçmektir.**

Örnek:

```text
Kullanıcı
   ↓
Intent / Entity / Slot
   ↓
Qwen Local Agent
   ↓
┌─────────────┬──────────────┬─────────────┬──────────────┐
│ Campaign    │ Finance      │ Product RAG │ Live Calc    │
│ Search      │ Engine       │             │ Adapter      │
│ Compare     │              │             │              │
└─────────────┴──────────────┴─────────────┴──────────────┘
   ↓
Verified Fact Pack
```

Agent serbest SQL çalıştırmaz.

Agent yalnız tanımlı tool contract'ları üzerinden işlem yapar.

---

# 12. Numeric / Grounding Verification

Naturalizer'ın oluşturduğu son cevap da kontrol edilir.

Örneğin Verified Fact Pack:

```text
Kâr payı: %2,99
Aylık taksit: 4.573,55 TL
```

içeriyorsa model:

```text
Kâr payı %2,75
```

şeklinde yeni bir sayı üretemez.

Numeric/Grounding Verifier kaynakta bulunmayan kritik finansal rakamları engeller.

---

# 13. Conversation State

BANSA çok turlu konuşmaları structured state ile yönetir.

Örneğin:

```text
Kullanıcı:
"100 bin TL 36 ay finansman istiyorum,
aylık ödeme düşük olsun."

BANSA:
"Hangi finansman türü?"

Kullanıcı:
"Konut."

BANSA:
→ 100.000 TL korunur
→ 36 ay korunur
→ düşük aylık ödeme hedefi korunur
→ ürün ailesi konut olarak atanır
→ öneri buna göre yapılır
```

---

# Context Poisoning Koruması

Önce:

```text
"Konut finansmanı"
```

sorulup ardından:

```text
"100 bin 24 ay araç finansmanı"
```

denirse eski `konut` context'i yeni açık kullanıcı talebinin önüne geçmez.

Kural:

```text
Yeni explicit intent/product > eski conversation context
```

---

# 14. Kullanıcı Odaklı Öneri Motoru

BANSA yalnızca banka listesi göstermez.

Kullanıcı “öner” dediğinde uygun veri varsa:

- en düşük kâr payını,
- en düşük aylık taksiti,
- en düşük toplam geri ödemeyi,
- kullanıcının önceliğine en uygun seçeneği

ayrı ayrı değerlendirebilir.

Örneğin:

```text
"Aylık ödemem mümkün olduğunca düşük olsun."
```

talebi ile:

```text
"Toplam geri ödemem mümkün olduğunca düşük olsun."
```

aynı objective değildir.

Recommendation engine kullanıcının hedefini conversation state içerisinde korur.

---

# 15. Finansman Karşılaştırması

Dashboard üzerinde kullanıcı:

- finansman türü,
- banka,
- tutar,
- vade

seçebilir.

Ana kategoriler arasında:

- Konut Finansmanı
- Taşıt Finansmanı
- İhtiyaç Finansmanı
- Ticari Finansman
- Tarım Finansmanı
- Alışveriş Finansmanı
- Leasing
- İş Yeri Finansmanı
- Gayrimenkul / Arsa
- diğer amaç bazlı ürünler

bulunur.

Kullanıcı yüzlerce veri alanıyla doğrudan karşılaştırılmaz.

Önce karar vermede önemli bilgiler gösterilir; detaylı tablo gerektiğinde açılır.

---

# 16. Kampanya Karşılaştırması

BANSA aktif kampanyaları:

- banka,
- kategori,
- avantaj,
- taksit,
- son tarih,
- müşteri tipi,
- kullanım koşulları

gibi alanlarla analiz eder.

Kampanya detay bağlantılarında mümkün olduğunca:

```text
/kampanyalar
```

gibi genel liste sayfası yerine doğrudan ilgili kampanyanın **resmî detay URL'si** kullanılır.

Follow-up context korunur.

Örneğin:

```text
"Gree Klima kampanyasında kaç taksit var?"
        ↓
"Ne zamana kadar geçerli?"
```

ikinci soru aynı kampanyaya bağlı olarak cevaplanır.

---

# 17. Kart Karşılaştırması

BANSA yalnız finansman ve kampanyaları değil, katılım bankalarının kartlarını da karşılaştırabilir.

Kart veri setinde örnek alanlar:

- kart adı,
- kart türü,
- müşteri segmenti,
- ödeme ağı,
- ödül programı,
- yıllık kart ücreti,
- taksit,
- puan / nakit iade / mil,
- temassız,
- QR / NFC,
- internet alışverişi,
- yurt dışı kullanım,
- öne çıkan avantaj,
- resmî kaynak.

Mevcut portable kart snapshot'ında:

```text
56 kart kaydı
```

bulunmaktadır.

Doğrulanmayan bir kart özelliği:

```text
Var
Yok
0 TL
```

şeklinde tahmin edilmez.

---

# 18. Kullanıcı Arayüzü

Uygulama Streamlit ile geliştirilmiştir.

Ana kullanıcı deneyimi:

```text
BANSA
├── BANSA Asistanı
├── Finansman Karşılaştırması
├── Kampanya Karşılaştırması
└── Kart Karşılaştırması
```

Amaç yalnız veri göstermek değil, kullanıcıya **karar desteği** sağlamaktır.

---

# 19. Graceful Degradation

BANSA'nın temel fonksiyonları tek bir modele veya tek bir servise bağımlı değildir.

```text
Tier 1
Exact / Live Verified Result
        ↓
Tier 2
Verified Deterministic Finance Data
        ↓
Tier 3
Local Qwen + RAG
        ↓
Tier 4
Safe Guidance / Abstention
```

Örneğin:

- internet giderse portable snapshot kullanılabilir,
- PostgreSQL çalışmazsa runtime SQLite kullanılabilir,
- LLM hazır değilse deterministic cevap çalışabilir,
- banka calculator'ı yanıt vermezse eski oran güncel diye gösterilmez.

---

# 20. On-Premise Mimari

BANSA kurum içi çalıştırılabilir şekilde tasarlanmıştır.

Local model endpoint'i varsayılan olarak loopback üzerinden kullanılabilir:

```env
BANSA_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1
BANSA_LOCAL_LLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
```

Böylece:

- müşteri verilerinin kurum dışına çıkmaması,
- harici LLM API bağımlılığının azaltılması,
- model altyapısının kurum tarafından kontrol edilmesi

amaçlanmaktadır.

---

# Kullanılan Teknolojiler

## Uygulama

- Python 3.11+
- Streamlit
- Pandas
- NumPy

## Veri Toplama

- Requests
- BeautifulSoup4
- Selenium

## Veri Katmanı

- PostgreSQL
- SQLite

## NLP / Yapay Zekâ

- PyTorch
- Transformers
- Sentence Transformers
- Qwen3 Embedding
- Qwen3 Reranker
- Qwen3 Local LLM

## Retrieval

- Structure-Aware Chunking
- Semantic Chunking
- Dense Retrieval
- BM25
- Reciprocal Rank Fusion
- Reranking
- Evidence Verification

## Diğer

- RapidFuzz
- Pytest
- Docker
- GitHub Actions

---

# Repository Yapısı

```text
BilisimVadisi2026-BANSA/
│
├── Ana_Sayfa.py
├── app.py
├── streamlit_app.py
│
├── src/
│   ├── scraping/
│   ├── rag/
│   ├── finance/
│   ├── chatbot/
│   └── ...
│
├── pages/
│   ├── Chatbot
│   ├── Finansman Karşılaştırması
│   ├── Kampanya Karşılaştırması
│   └── Kart Karşılaştırması
│
├── config/
│   └── banka ve source konfigürasyonları
│
├── data/
│   ├── campaigns.db
│   ├── curated_dashboard/
│   ├── verified_catalog/
│   ├── runtime/
│   └── rag/
│
├── postgresql/
│   └── schema / migration / yardımcı araçlar
│
├── scripts/
│   └── sync / audit / maintenance / test scriptleri
│
├── tests/
│   └── regresyon ve davranış testleri
│
├── docs/
│
├── .streamlit/
├── .github/
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── SECURITY.md
└── README.md
```

---

# Kurulum

## 1. Repository'yi klonlayın

```bash
git clone REPOSITORY_URL
cd BilisimVadisi2026-BANSA
```

## 2. Virtual environment oluşturun

```bash
python -m venv .venv
```

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
source .venv/bin/activate
```

## 3. Bağımlılıkları yükleyin

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

# Uygulamayı Çalıştırma

```bash
python -m streamlit run Ana_Sayfa.py
```

Windows için repository içerisindeki:

```text
RUN_BANSA_FINAL_UI.bat
```

dosyası da kullanılabilir.

---

# Ortam Değişkenleri

`.env.example` örnek konfigürasyonu içerir.

Örnek:

```env
APP_DB_PATH=data/campaigns.db

REQUEST_TIMEOUT=20
USER_AGENT=BANSA-Campaign-Research/0.1

BANSA_FAST_NATURALIZER_ENABLED=1
BANSA_FAST_NATURALIZER_TIMEOUT_SECONDS=0.8

BANSA_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1
BANSA_LOCAL_LLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
```

> Gerçek parola, token ve gizli bilgiler `.env` içerisinde tutulmalı ve GitHub'a commit edilmemelidir.

---

# Veri Seti

BANSA verileri ağırlıklı olarak BDDK kapsamındaki katılım bankalarının **kamuya açık resmî web sayfalarından** oluşturulmuştur.

Portable yarışma veri seti repository içerisinde:

```text
data/
```

klasörü altında bulunmaktadır.

Önemli bileşenler:

```text
data/campaigns.db
data/verified_catalog/
data/runtime/
data/rag/
data/curated_dashboard/
```

Ana banka evreni:

```text
config/bddk_participation_bank_scope.json
```

ile tanımlıdır.

Kaynak verilerin provenance bilgileri mümkün olduğunca veri kayıtları ile birlikte tutulmaktadır.

---

# Testler

Tüm testleri çalıştırmak için:

```bash
python -m pytest -q
```

Syntax kontrolü:

```bash
python -m compileall -q Ana_Sayfa.py app.py streamlit_app.py src pages scripts
```

V49 paketinde:

```text
176 test dosyası
1.000+ test fonksiyonu
```

bulunmaktadır.

Test kapsamına örnekler:

- scraping,
- dynamic discovery,
- safe removal,
- normalizasyon,
- finance extraction,
- pricing integrity,
- amount semantics,
- live calculator adapters,
- exact scenario,
- recommendation,
- conversation context,
- context poisoning,
- campaign follow-up,
- card intent,
- Hybrid RAG,
- structure-aware chunking,
- embedding,
- BM25,
- RRF,
- reranking,
- evidence verification,
- numeric grounding,
- dashboard,
- user-facing regression.

---

# Örnek Kullanıcı Soruları

### Finansman

```text
500 bin TL birikmişim var,
1 milyon TL'lik ev almak istiyorum.
Bana en mantıklı seçeneği öner.
```

```text
100 bin TL, 36 ay ihtiyaç finansmanında
aylık ödemesi en düşük olan bankayı öner.
```

```text
900 bin TL'lik araç alacağım,
400 bin TL nakitim var ve
aylık 25 bin TL'den fazla ödemek istemiyorum.
```

### Kampanya

```text
Gree Klima kampanyasında kaç taksit var?
```

```text
Ne zamana kadar geçerli?
```

### Kart

```text
Paraf Platinum kredi kartında
temassız özelliği var mı?
```

```text
DKart Debit kartın yıllık ücreti ne kadar?
```

---

# Örnek Karar Akışı

```text
Kullanıcı:
"100 bin TL 36 ay finansman istiyorum.
Aylık ödeme mümkün olduğunca düşük olsun."

BANSA:
"Finansman türünü belirtir misiniz?"

Kullanıcı:
"Konut finansmanı."

BANSA:
→ önceki tutarı korur
→ önceki vadeyi korur
→ aylık ödeme önceliğini korur
→ konut ürünlerini aynı senaryoda karşılaştırır
→ yalnız doğrulanmış sonuçları sıralar
→ en düşük aylık ödeme seçeneğini önerir
```

Bu davranış BANSA'nın yalnız soru-cevap değil, **structured conversational decision support** sunduğunu gösterir.

---

# Güvenlik Politikası

BANSA aşağıdaki durumlarda finansal sayı üretmemeyi tercih eder:

- kaynak doğrulanamıyorsa,
- requested amount ile source amount uyuşmuyorsa,
- vade uyuşmuyorsa,
- calculator sonucu eksikse,
- pricing evidence yeterli değilse,
- ürün uygunluk kuralı çözülemiyorsa.

Temel prensip:

```text
Yanlış kesin cevap
        <
Doğru biçimde "doğrulanamadı" demek
```

---

# Projenin Yarışma Kapsamındaki Katkısı

BANSA yarışma problemini yalnız bir bilgi çıkarımı modeli olarak ele almamıştır.

Proje;

1. resmî banka verisini toplar,
2. web gürültüsünü temizler,
3. katılım bankacılığı terminolojisini normalize eder,
4. finansal alanları yapılandırır,
5. kampanyaları sınıflandırır,
6. benzer ürünleri karşılaştırır,
7. açık uçlu metin sorularını Hybrid RAG ile çözer,
8. sayısal finansal hesaplamaları deterministik araçlara ayırır,
9. sonuçları kaynak ve grounding kontrollerinden geçirir,
10. dashboard ve chatbot üzerinden kullanıcıya sunar.

---

# BANSA'yı Farklılaştıran Noktalar

### 1. Finansal gerçek LLM'den gelmez

LLM doğal dil katmanıdır; finans motoru değildir.

### 2. Klasik Vector RAG değildir

```text
Structure-Aware Chunking
+ Semantic Chunking
+ Qwen3 Embedding
+ BM25
+ RRF
+ Qwen3 Reranker
+ Evidence Pack
+ Retrieval Verifier
```

kullanılır.

### 3. Domain-specific güvenlik vardır

- Amount Semantics
- Exact Scenario
- No Maturity Interpolation
- Calculator Constraint Separation
- Freshness
- Verified Subset Ranking
- Numeric Grounding
- Context Isolation

### 4. On-premise çalışabilir

Temel sistem harici ticari LLM API'sine bağımlı değildir.

### 5. Graceful degradation vardır

Bir bileşen çalışmadığında bütün sistemin çökmesi yerine güvenli alt katmana geçilir.

---

# Takım

## BANSA Takımı

### Esra Zariç  
**Takım Kaptanı · Teknik Lider**

- Sistem mimarisi
- Veri modeli
- Normalizasyon
- RAG / LLM
- Agent / tool orchestration
- Deterministik finans motoru
- Verifier ve güvenlik
- Sistem entegrasyonu

### Koray Demir

- Veri toplama
- Web scraping
- Banka kaynak entegrasyonları

### Gökçe Sürücü

- Streamlit kullanıcı arayüzü
- Dashboard
- Kullanıcı deneyimi

### Abdullah Güngör

- Regression test
- Quality Assurance
- Demo ve deployment hazırlığı

---

# Güvenlik

Parola, token ve gizli konfigürasyonlar repository içerisinde tutulmamalıdır.

Ayrıntılar:

```text
SECURITY.md
```

dosyasında bulunmaktadır.

---

# Lisans

Bu proje **Apache License 2.0** ile açık kaynak olarak yayımlanmaktadır.

Repository kökünde yer alan:

```text
LICENSE
```

dosyasına bakınız.

---

# TEKNOFEST 2026

**Yapay Zekâ Dil Ajanları Yarışması — 2. Senaryo**

```text
BilisimVadisi2026
```

---

## Son Söz

> **BANSA'nın farkı yalnız cevap üretmesi değil; hangi durumda cevap üretmemesi gerektiğini de bilmesidir.**

**Resmî Kaynak → Doğrulanmış Veri → Deterministik Karar → Kanıt Kontrolü → Yerel Yapay Zekâ → Açıklanabilir Sonuç**
