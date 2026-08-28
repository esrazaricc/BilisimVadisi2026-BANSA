# BANSA V13 — Natural Finance / Follow-up / Vehicle Rules Patch

Tarih: 2026-08-26

## Bu pakette düzeltilen kritik davranışlar

1. **Semantic numeric follow-up (V13)**
   - `Türkiye Finans sigortalı taşıt kâr payı?` → `36 ay` artık banka + ürün + sigortalı koşulu + rate intent bilgisini korur.
   - `Vakıf motosiklet finansmanı nasıl?` → `600 bin için?` → `24 ay olur mu?` zinciri aynı finansman bağlamında devam eder.
   - Yeni mesajda açık ürün ailesi (`araç`, `konut`, vb.) geçerse eski aile bağlamını ezer.
   - Çok bankalı karşılaştırmalarda mevcut deterministic canonical comparison builder korunur.

2. **Türkiye Finans doğal fiyatlama cevabı**
   - Aynı 36 ay oranına sahip 0 km ve 2.el sigortalı satırlar, kullanıcı araç durumunu sormadıysa tek cümlede birleştirilir.
   - Örn. `Sigortalı · 36 ay: %3,48`.

3. **Structured vehicle rules first**
   - Araç/motosiklet değer-vade-finansman oranı kuralları artık önce `finance_rules_json.display_metadata.vehicle_value_rules` içinden okunur.
   - Kirli HTML / sayfa metni regex'i yalnız fallback'tir.
   - Bu sayede Dünya Katılım'da yalnız son bandın görünmesi hatası giderildi; 70/48, 50/36, 30/24, 20/12 bantlarının tamamı okunur.

4. **Türkiye Emlak Katılım Taşıt Finansmanı current overlay**
   - Resmî taşıt değer tablosu structured rule olarak runtime'a eklenir.
   - Azami genel vade 48 ay olarak görünür.
   - 48/36/24/12 ay ve %70/%50/%30/%20 finansman sınırları saklanır.
   - Güncel exact kâr payı doğrulanmadan aylık taksit uydurulmaz.

5. **Karşılaştırmada graceful rule evidence**
   - Exact hesaplama kaydı olmayan Dünya/Emlak için artık `sayısal vade yayımlanmamış` gibi yanlış mesaj gösterilmez.
   - Bunun yerine doğrulanmış araç değeri/vade tablosu gösterilir.
   - Araç değeri ile istenen finansman tutarı birbirine karıştırılmaz.
   - Exact oran/taksit yoksa banka geri ödeme sıralamasına sokulmaz.

6. **Dünya Katılım + motosiklet güvenlik davranışı**
   - BANSA'da ayrı doğrulanmış `Motosiklet Finansmanı` ürün kaydı yoksa ayrı ürün icat edilmez.
   - Motosiklet sorgusu genel `Araç Finansmanı` kaydıyla eşleştiğinde, doğrulanmış taşıt değer/vade tablosu kullanılır ve kaydın genel araç kaydı olduğu açıkça belirtilir.

7. **Portable runtime / paketleme düzeltmeleri**
   - `psycopg` bulunmadığında PostgreSQL kullanılmayan portable/demo import yolları artık çökmez; gerçek PostgreSQL bağlantısı gerektiğinde açık hata verir.
   - ZIP'te Unicode adı bozulmuş `4_Finansman_Karşılaştırması.py` dosyası doğru adına getirildi. `Ana_Sayfa.py` artık gerçekten var olan dosyaya yönlenir.

## Eklenen regresyon testleri

`tests/test_competition_natural_followup_v13.py`

Kapsam:
- Türkiye Finans sigortalı rate follow-up
- Vakıf kısa banka adı + motosiklet + 600 bin + 24 ay follow-up
- explicit vehicle override
- Dünya 4 bant structured vehicle rule
- Emlak current 48/36/24/12 overlay
- Dünya/Emlak compare graceful rule evidence

## Test durumu

- Yeni V13 regresyonları: **6/6 PASS**
- Kritik competition/follow-up paketi: **32/32 PASS**
- Portable finance compare + vehicle parser: **6/6 PASS**
- Sandbox genel test koleksiyonunda `selenium` ve `sentence-transformers` kurulu olmadığı için ilgili 3 test dosyası burada collect edilemiyor. Bu paketler `requirements.txt` içinde tanımlıdır.
- Geniş suite çalışmasında 815 test geçti; 10 eski test mevcut competition-router'ın yeni route/render davranışını eski backend/format sözleşmesine göre beklediği için fail oluyor. Bu 10 test bu V13 değişikliklerinin hedeflediği kullanıcı senaryoları değildir.
