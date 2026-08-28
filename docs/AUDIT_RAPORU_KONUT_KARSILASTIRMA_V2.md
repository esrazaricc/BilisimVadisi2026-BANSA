# BANSA — Konut Finansmanı Karşılaştırma ve Veri Kalitesi Audit V2

Tarih: 14 Ağustos 2026

## Neden bu audit yapıldı?

Konut Finansmanı ana karşılaştırma tablosunda üç farklı problem aynı anda görülüyordu:

1. **Karşılaştırma tasarımı sorunu:** `Taksit Sayısı`, generic `Finansman Tutarı`, `Masraf Bilgisi` gibi alanlar çoğu üründe anlamsız placeholder metinlerle doluyor ve gerçek banka farklarını görünmez hale getiriyordu.
2. **Veri kalitesi sorunu:** Türkiye Finans Konut Finansmanı için eski extractor kaydı `general_expense / Masraf / waived=1` ürettiği için uygulama yanlış biçimde **“Masraf: Alınmıyor”** gösteriyordu.
3. **Ürün ailesi sınıflandırma sorunu:** Kuveyt Türk `2B Finansmanı`, `Arsa Finansmanı` ve `İş Yeri Finansmanı`, URL klasörü `konut-finansmanlari` altında olduğu için yanlışlıkla `Konut Finansmanı` ailesine giriyordu.

Bu sürüm yalnız ekranı değiştirmez. **Kaynak sınıflandırması → extractor/normalizasyon → SQLite → PostgreSQL → Streamlit** zincirini birlikte düzeltir.

---

## Yeni ana Konut Finansmanı tablosu

Ana tablo sadece doğrudan karşılaştırılabilir ve karar vermeye yarayan alanları gösterir:

- Banka
- Ürün Adı
- **Kâr Payı / Fiyatlama**
- **Azami Vade**
- **Finansman Oranı**
- **Tahsis Ücreti**
- **Ekspertiz Ücreti**
- **İpotek Tesis Ücreti**
- Resmî Kaynak

Ana tablodan çıkarılanlar:

- Taksit Sayısı — konut finansmanında çoğu zaman aylık vadenin tekrarıdır.
- Generic Finansman Tutarı — çoğu üründe ekspertiz/enerji/konut sahipliğine göre değişir ve tek sayı değildir.
- Generic Masraf Bilgisi — farklı masraf kalemlerini tek hücrede karıştırır ve yanlış `Alınmıyor` çıkarımına açıktır.
- Gayrimenkul/Ekspertiz Değeri — banka ürün özelliği değil, kullanıcı girdisidir.
- Orana Göre Finansman Tutarı — kullanıcı girdisine bağlı hesap sonucudur.

Ekspertiz değeri ve hesaplanan finansman tutarı **Ürün Detayı → Bankaya Özgü Konut Finansmanı Hesabı** altında kalır.

---

## Türkiye Finans — kritik düzeltme

Eski veride:

- `allocation` → `%0,50`
- `general_expense / Masraf` → `waived=1`

bulunuyordu. İkinci satır yanlış olduğu için uygulama `Masraf: Alınmıyor` gösteriyordu.

Audit sonrası doğrulanmış kayıtlar:

- **Tahsis Ücreti:** `%0,50`; 100.000 TL örnek tabloda 500 TL.
- **Ekspertiz (Değerleme):** 100.000 TL örnek tabloda **16.500 TL**; minimum maliyet örneğidir ve resmî harç, taşınmaz alanı, mevcut durum ve lokasyona göre değişebilir.
- **İpotek Tesis Ücreti:** 100.000 TL örnek tabloda **3.000 TL**.
- Ekspertiz maliyetinin **1,5 katı** kadar hesapta bloke tesis edilmesi koşulu detayda tutulur.
- DASK/Konut Sigortası/Finansman Güvence Sigortası değişken maliyetleri ayrı koşul olarak tutulur.
- Fiyatlama tablosunun Yedek Hesap + DASK + Ferdi Kaza + Konut Sigortası + Otomatik Fatura Talimatı şartına bağlı olduğu detayda gösterilir.
- Mevcut **40 fiyatlama satırı korunur**; kâr oranı ana tabloda tek sayıya indirgenmez.

Ana tablo fiyatlama özeti yaklaşık olarak:

`%2,95–%4,42 · vade/sigorta/konut`

şeklinde görünür.

---

## Albaraka Türk — Konut Finansmanı

Doğrulanan yapı:

- Azami vade: **120 ay**.
- Finansman oranları ekspertiz değeri + enerji sınıfı + standart/ilave konut alımına göre değişir.
- Tahsis ücreti: **%0,50**.
- Ekspertiz: **3. kişiye ödenen gerçek maliyet**.
- Taşınmaz rehin/ipotek maliyeti: **3. kişiye ödenen gerçek maliyet**.
- Resmî yıllık maliyet dokümanındaki `%2,95` oranı **100.000 TL örnek maliyet tablosudur**; genel ürün oranı yapılmaz.
- Örnek fiyatlama 12 / 48 / 60 / 72 / 84 / 120 ay olarak altı satır halinde korunur.

Ana tabloda `%2,95 · 100.000 TL örnek` şeklinde etiketlenir.

---

## Dünya Katılım — Konut Finansmanı

Doğrulanan yapı:

- İlk ev ve ikinci/sonraki konut için ekspertiz + enerji sınıfına göre ayrı finansman oran tabloları vardır.
- Tahsis ücreti: **%0,50**.
- Ekspertiz tarifesi: **20.778 TL**, değer/brüt alan/resmî tarifelere göre değişebilir; üçüncü kişi maliyeti yansıtılabilir.
- İpotek tesis: **3.000 TL**, taşınmaz sayısına göre değişebilir; üçüncü kişi maliyeti yansıtılabilir.
- İpotek fek: **3.000 TL** detayda korunur.

Önemli konservatif karar: Ürün sayfasındaki genel hesaplama komponentinin 1–36 değerlerini ve `İhtiyaç Finansmanı` etiketini **Konut Finansmanı azami vadesi olarak kabul etmiyoruz**. Güvenilir sayısal ürün vadesi doğrulanmadığı için `Azami Vade = Kaynakta doğrulanmadı` gösterilir.

---

## Kuveyt Türk — gerçek konut ürünleri

Konut ailesinde kalan ürünler:

- Konut Finansmanı
- İlk Evim Konut Finansmanı
- Yeşil Konut Finansmanı
- Gurbetten Sılaya Gayrimenkul Finansmanı

### Konut Finansmanı

- Azami vade: **120 ay**.
- Mevcut konutu olanlar için finansman oranları ekspertiz/enerji sınıfına göre `%5–%22,5` bandındadır.
- Tahsis ücreti: **%0,50**.
- Resmî hesaplama aracındaki ücretler örnek olarak etiketlenir; sabit tarife gibi sunulmaz.

### İlk Evim

- Azami vade: **120 ay**.
- İlk ev finansman oranları ekspertiz/enerji sınıfına göre `%20–%90` bandındadır.
- Tahsis ücreti: **%0,50**.

### Yeşil Konut

- Azami vade: **120 ay**.
- Finansman tutarı ekspertiz, sıfır/ikinci el, enerji sınıfı ve mevcut konut sahipliğine göre değişir.
- Sayısal oran tablosu parser tarafından güvenilir şekilde alınamazsa oran **uydurulmaz**; ana tabloda `Koşullara göre · detayda` gösterilir.
- Web kâr oranlarının 3.000.000 TL finansman talebi eşiğine ilişkin doğrulanmış not, ekspertiz değeriyle karıştırılmadan ürün detayında tutulur.

### Gurbetten Sılaya

- Resmî sayfa ürünü özel şartlı bir **konut finansmanı** olarak tanımlar.
- Finansman oranı: ekspertiz değerinin **%50'si**.
- Tahsis ücreti: **%0,50**.

---

## Kuveyt Türk — Konut ailesinden çıkarılan ürünler

Bunlar aynı web klasöründe olsalar da ekonomik olarak konut finansmanı karşılaştırmasına ait değildir:

- **2B Finansmanı** → `Arsa Finansmanı`
  - 2B arazisi alımı
  - Arazi değerinin `%100`üne kadar
  - 60 aya kadar
  - Ticari tahsis ücreti azami `%1,10`
- **Arsa Finansmanı** → `Arsa Finansmanı`
  - 60 aya kadar
  - Ticari tahsis ücreti azami `%1,10`
- **İş Yeri Finansmanı** → `İş Yeri Finansmanı`
  - ticari gayrimenkul
  - 60 aya kadar
  - Ticari tahsis ücreti azami `%1,10`

`config/standard_product_sources.json` içinde bu üç ürün için **generic konut URL kuralından önce exact-path aile kuralları** eklenir. Böylece sonraki taramalarda hata geri gelmez.

---

## Gelecek taramalar için extractor iyileştirmeleri

Pakette güncellenen scanner/extractor katmanı da bulunur. Önceki housing audit ile eklenen ve bu sürümde korunan iyileştirmeler:

- `%90` ve `90%` oran biçimlerini okuyabilme.
- `Konut Değeri`, `Konut Ekspertiz Değeri`, `Ekspertiz Değeri/Enerji Sınıfı` başlıklarını tanıma.
- İlk konut / ilave konut matrislerini canonical JSON'a çevirme.
- `60 aya kadar fark vade` ifadesini 60 ay olarak çıkarma.
- `Arazi değerinin %100'ü` / `Ekspertiz değerinin %50'si` biçimlerini çıkarma.
- `maksimum %1,10` tahsis ifadesini kesin oran değil **azami oran** olarak etiketleme.
- Resmî kaynakla doğrulanmış konut override'larını scan sonunda uygulama.

---

## Veri güvenliği ilkeleri

Bu audit'te aşağıdaki kurallar bilinçli olarak uygulanır:

1. `Kaynakta doğrulanmadı` ≠ `Alınmıyor`.
2. Bir masrafın `waived=True` olması başka bir masraf kalemini sıfırlamaz.
3. Hesaplama aracındaki örnek ücret ≠ sabit tarife.
4. Örnek maliyet tablosundaki tutar ≠ ürün finansman limiti.
5. Ekspertiz değeri ≠ finansman talebi tutarı.
6. Sayısal kaynak yoksa oran/vade uydurulmaz.
7. Ana tabloda karşılaştırılabilir kısa özet; uzun koşullar detayda tutulur.

---

## Test sonucu

Düzeltilmiş snapshot üzerinde repair iki kez çalıştırıldı.

- İlk çalıştırma: 7 gerçek housing ürün auditi + 3 ürün yeniden sınıflandırma.
- İkinci çalıştırma: kayıt sayıları çoğalmadı.
- Albaraka fiyatlama: **6 satır** kaldı.
- Türkiye Finans fiyatlama: **40 satır** kaldı.
- Focused extractor tests: **11 passed**.
- Veri/UI audit: **PASS=45, FAIL=0**.

Tam repo `pytest -q` bu konteynerde iki eksik runtime bağımlılığı nedeniyle collection aşamasında durdu:

- `psycopg` yok
- `selenium` yok

Bu nedenle burada tüm repo için “tamamı geçti” iddiası yapılmamaktadır. Kullanıcının Windows ortamında bu bağımlılıklar mevcutken genel pytest tekrar çalıştırılmalıdır.

---

## Başlıca resmî kaynaklar

- Türkiye Finans Konut Finansmanı:
  https://www.turkiyefinans.com.tr/tr-tr/bireysel/konut-finansmani/sayfalar/konut-finansmani.aspx
- Dünya Katılım Konut Finansmanı:
  https://dunyakatilim.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/konut-finansmani
- Dünya Katılım Finansal Tüketici Ücret Tablosu:
  https://dunyakatilim.com.tr/content/files/uploads/2516/dk-bireysel-ucrt11-180526.pdf
- Albaraka Konut Finansmanı:
  https://www.albaraka.com.tr/tr/bireysel/finansmanlar/konut-finansmani/konut-finansmani
- Albaraka Ürün ve Hizmet Ücretleri:
  https://www.albaraka.com.tr/tr/urun-ve-hizmet-ucretleri
- Kuveyt Türk Konut Finansmanı:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/konut-finansmani
- Kuveyt Türk İlk Evim:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/ilk-evim-konut-finansmani
- Kuveyt Türk Yeşil Konut:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/yesil-konut-finansmani
- Kuveyt Türk Gurbetten Sılaya:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/gurbetten-silaya-gayrimenkul-finansmani
- Kuveyt Türk 2B:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/2b-finansmani
- Kuveyt Türk Arsa:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/arsa-finansmani
- Kuveyt Türk İş Yeri:
  https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/is-yeri-finansmani
