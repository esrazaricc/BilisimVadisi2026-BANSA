# BANSA V14 — Conversational Finance Reliability Patch

Bu sürüm, kullanıcı tarafından gerçek Streamlit konuşma çıktılarında tespit edilen follow-up, intent, ürün/banka override ve doğal metin sorunlarını düzeltir.

## Düzeltilen davranışlar

1. **Türkiye Finans rate → maturity → calculation zinciri**
   - `sigortalı taşıt kâr payı` bağlamı `36 ay` ve `100 bin TL için aylık taksit` devamlarında korunur.
   - Yeni `aylık taksit` intent'i eski `kâr payı` intent'inin yerini alır.
   - Aynı finansal sonucu taşıyan 0 km / 2. el satırları kullanıcı çıktısında tekrarlanmaz.

2. **Araç/motosiklet değer bantları**
   - Dünya Katılım ve Türkiye Emlak Katılım için araç değeri bantları genel ürün azami vadesinden önce değerlendirilir.
   - 300k/600k/900k/1.5m değerleri sırasıyla 48/36/24/12 ay bandına düşer.
   - `1 milyon 500 bin TL` bileşik Türkçe tutar parser'ı 1.500.000 TL olarak okunur.

3. **Emlak Katılım exact fiyatlama güvenliği**
   - Araç değeri → azami finansman/vade tablosu aylık taksit tablosu gibi kullanılmaz.
   - İstenen tutar/vade için doğrulanmış fiyatlama yoksa taksit uydurulmaz.
   - Konut live endpoint erişilemezse yeni/sıfır konut mapping kapsamı korunur, sayısal değer sıralamaya eklenmez.

4. **Kampanya follow-up state**
   - `Ziraat Teknosa → Ne zamana kadar? → şartı ne?` aynı kampanyada kalır.
   - Kampanya detail follow-up'ları başka bankanın kampanyasına atlamaz.
   - MediaMarkt gibi yeterli eşleşme bulunmayan isimlerde alakasız kampanya fallback'i yapılmaz.

5. **Explicit product / bank override**
   - `Vakıf konut → motosiklet` eski konut family state'ini ezer, bankayı korur.
   - `Vakıf motosiklet → Peki Ziraat'ta?` bankayı değiştirir, Vakıf kurallarını Ziraat'a kopyalamaz.
   - Bankada ayrı doğrulanmış motosiklet ürünü yoksa genel taşıt kaydı ayrı ürünmüş gibi sunulmaz.
   - `Albaraka konut → Peki eğitim finansmanının avantajları?` yalnız bankayı devralır, eski konutu taşımaz.

6. **Comparison follow-up**
   - `100k / 36 ay araç karşılaştır` sonrası `En düşük geri ödeme hangisinde?` önceki senaryoyu korur ve kampanya router'ına düşmez.
   - Kazanan yalnız birebir doğrulanmış toplam geri ödeme sonuçları arasında söylenir.

7. **Scraping text sanitization**
   - FAQ başlıkları (`... Kullanmalıyım?`, `Kredi Notu Önemli mi?`) ürün açıklaması olarak basılmaz.
   - `Sıkça Sorulan Sorular`, `Diğer Finansman Türleri`, menü/başvuru navigasyonu gibi parçalar başvuru metnine sızmaz.
   - Generic taşıt sayfasındaki başka specialty ürün teaser'ı seçili ürün açıklaması sanılmaz.

8. **Legacy / competition service ayrımı**
   - Jury-facing natural/fast routing yalnız `competition_response_service` içinde kalır.
   - Legacy `chatbot_response_service` eski deterministic/RAG route/backend sözleşmesini korur.
   - Böylece fallback davranışı ve eski renderer regresyonları competition katmanı tarafından sessizce ezilmez.

## Yeni testler

- `tests/test_competition_conversation_state_v14.py`
- `tests/test_competition_natural_sanitization_v14.py`

Testler; gerçek kullanıcı konuşma zincirleri, kampanya context'i, ürün/banka override, bileşik Türkçe tutar parser'ı, Emlak/Dünya değer bantları, sigortalı varyantı ve metin sanitization davranışlarını kapsar.

## Güvenlik prensibi

LLM veya doğal cevap katmanı finansal rakam üretmez. Oran/taksit/toplam geri ödeme yalnız doğrulanmış deterministic kayıt, resmî fiyatlama tablosu veya doğrulanmış hesaplayıcı sonucundan gelir. Araç değeri tablosu fiyatlama tablosu yerine kullanılamaz.
