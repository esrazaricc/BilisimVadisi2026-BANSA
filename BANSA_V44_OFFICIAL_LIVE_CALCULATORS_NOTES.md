# BANSA V44 — Resmî Canlı Finansman Hesaplama Entegrasyonu

## Amaç
Konut, taşıt ve ihtiyaç finansmanı ekranlarında kullanıcı tarafından girilen **tutar + vade** için mümkün olan bankalarda bankanın resmî hesaplama aracına birebir sorgu gönderilir. Canlı sonuç yalnız BANSA'nın katı `LiveCalculationResult` sözleşmesini geçerse tabloya girer.

V44, V43 mimarisini bozmaz. Öncelik sırası:

1. **Resmî banka hesaplama aracı — exact canlı sonuç**
2. **Mevcut doğrulanmış V43 deterministik kaynak modeli / snapshot**
3. **Sayısal sonuç yoksa kişiye özel teklif / güvenli abstention**

LLM hiçbir aşamada oran, taksit veya toplam geri ödeme üretmez.

## V44 ile yapılan temel değişiklikler

### 1. Ortak canlı hesaplama servisi
`src/finance_official_calculator_service.py`

Dashboard ve chatbot aynı resolver'ı kullanır. Böylece UI'da görülen canlı oran/taksit ile chatbot cevabı aynı kaynaktan gelir.

Bir canlı sonuç tabloya ancak şu koşullarda girer:
- `status == VERIFIED`
- hesaplanan tutar == kullanıcının girdiği tutar
- hesaplanan vade == kullanıcının girdiği vade
- kâr payı, aylık taksit ve toplam geri ödeme boş değil

Başka tutar/vade sonucu, eski snapshot veya tahmin canlı sonuç diye gösterilmez.

### 2. Türkiye Emlak Katılım canlı entegrasyonu
Mevcut doğrulanmış resmî adapter korunup dashboard/chatbot akışının önüne alındı.

Resmî endpoint sözleşmesi mevcut adapter'da doğrulanır:
- ürün/katalog ve vade property endpoint'i
- hesaplama endpoint'i
- ödeme planı satır sayısı
- ödeme planı toplamı
- kalan anaparanın sıfırlanması
- masraf bileşenleri

Eşlenen bireysel senaryolar:
- Konut Finansmanı
- Taşıt Finansmanı — 0 km / 2. el varyantları
- İhtiyaç ailesinde Ev/Ofis Gereçleri Tüketici Finansmanı

### 3. Vakıf Katılım adapter'ı üç ana aileye genişletildi
`src/finance_live_adapters/vakif_katilim.py`

Önceden yalnız ihtiyaç finansmanı mapping'i vardı. V44'te:
- Konut Finansmanı — product_id 296
- Taşıt Finansmanı — product_id 286
- İhtiyaç Finansmanı — product_id 318

Desteklenir.

**Önemli güvenlik kararı:** Bankanın dahili `financingType` kodları tahmin edilmez. Adapter her çalıştırmada resmî hesaplama formunu okur, ürün adını label üzerinden bulur ve option `value` değerini canlı formdan çözer. Banka iç kodu değişirse yanlış ürüne sorgu atmak yerine eşleme doğrulanamaz ve sistem fail-closed davranır.

### 4. Diğer mevcut doğrulanmış canlı adapter'lar korunuyor
Canonical senaryo ekranında mevcut doğrulanmış teknik mapping'ler:

**Konut**
- Dünya Katılım
- Albaraka Türk
- Türkiye Emlak Katılım
- Vakıf Katılım

**Taşıt**
- Türkiye Emlak Katılım
- Vakıf Katılım

**İhtiyaç**
- Türkiye Emlak Katılım
- Vakıf Katılım

Bu liste “bankanın sitesinde bir hesaplama aracı var” listesi değildir. Yalnız BANSA içinde endpoint/form sözleşmesi teknik olarak doğrulanmış ve güvenli adapter'ı bulunan canonical ürünleri gösterir.

Türkiye Finans ve Kuveyt Türk gibi bankalarda kullanıcı tarafından kâr oranı girilebilen hesaplama ekranları veya ayrı fiyatlama tabloları bulunduğu için, doğrulanmış programatik default-rate endpoint sözleşmesi kurulmadan bunlar sahte “canlı banka sonucu” olarak etiketlenmez. V43 doğrulanmış kaynak modeli güvenli fallback olarak korunur.

### 5. Dashboard metrikleri düzeltildi
Eski ürün/satır sayıları yerine senaryoyu anlatan metrikler kullanılır:
- **BDDK banka evreni**
- **Bu türde doğrulanmış banka**
- **Resmî hesaplama aracı eşlemesi**
- **Bu senaryoda hesaplanan banka**

Sonuç geldiğinde ayrıca:
- **Resmî canlı sonuç** — exact live sonucu gelen banka sayısı
- **Doğrulanmış BANSA modeli** — canlı çıkmadığında güvenli V43 kaynak modeliyle hesaplanan banka sayısı
- **En düşük aylık taksit** — yalnız oluşmuş sayısal sonuçlar içinde

Tabloda canlı satırlar açıkça:
- `Durum = Resmî canlı hesaplama`
- `Sonuç Türü = Resmî banka hesaplama aracı · birebir senaryo`

olarak etiketlenir.

### 6. Chatbot da live-first oldu
`src/competition_natural_chat.py`

Exact tutar/vade içeren finans sorularında:
1. resmî canlı hesaplama,
2. V43 deterministic projection,
3. mevcut exact portable scenario

sırası uygulanır.

Böylece Türkiye Emlak Katılım gibi canlı mapping bulunan bir banka için dashboard başka, chatbot başka rakam üretmez.

### 7. Banka arızası bütün karşılaştırmayı bekletmez
`live_records_for_rows()` bankaları paralel sorgular. Bir bankanın timeout olması diğer bankaların sonuçlarını engellemez.

HTTP timeout:
`BANSA_LIVE_CALCULATOR_TIMEOUT_SECONDS`

Varsayılan: **8 saniye**. Minimum 2, maksimum 30 saniye.

Streamlit scenario sonucu 60 saniye cache'lenir; aynı tutar/vade için her rerun'da bankalara tekrar gereksiz istek atılmaz.

## Fail-closed kuralları
- HTTP/HTML/API sözleşmesi değiştiyse sayı yok.
- Exact amount/maturity uyuşmuyorsa sayı yok.
- Kâr payı / aylık / toplamdan biri eksikse sayı yok.
- Variant gerekiyorsa yalnız açıkça doğrulanmış varyant mapping'i çalışır.
- Canlı endpoint erişilemezse “0 TL”, “muaf”, “yaklaşık oran” üretilmez.
- Canlı sonuç yokken V43 doğrulanmış model varsa o, ayrı etiketle gösterilir.
- İkisi de yoksa banka kişiye özel teklif alanına gider.

## Test
Yeni V44 test dosyası:
`tests/test_v44_official_live_calculators.py`

Kontrol edilenler:
- Vakıf konut/taşıt/ihtiyaç mapping'leri
- Vakıf resmi form label'ından dinamik internal code discovery
- exact VERIFIED zorunluluğu
- farklı tutar sonucunun reject edilmesi
- condition-specific variant expansion
- paralel banka hata izolasyonu
- chatbot live-first davranışı
- canonical live mapping coverage
- dashboard metrik ayrımı

V44 geliştirme doğrulama seti:
**30 test passed**

Not: Çalışma sandbox'ında dış internet DNS erişimi kapalı olduğundan gerçek banka endpoint'lerine bu ortamdan canlı HTTP smoke testi yapılamadı. Adapter sözleşmeleri ve routing mock/contract testleriyle doğrulandı. Yarışma makinesinde internet varken aşağıdaki smoke script kullanılabilir.
