# Veri Seti ve Kapsam

Kaynak snapshot: `data/campaigns.db`  
Okunabilir dışa aktarımlar: `dataset/`

## 14 Ağustos 2026 snapshot kapsamı

- Güncel sınıflandırılmış kampanya: **527**
- Standart finansman ürünü: **124**

### Kampanya kapsamı

- Albaraka Türk: 104
- Dünya Katılım: 42
- Hayat Finans: 11
- Kuveyt Türk: 110
- T.O.M. Katılım: 75
- Türkiye Emlak Katılım: 64
- Türkiye Finans: 49
- Ziraat Katılım: 72

### Standart ürün kapsamı

- Albaraka Türk: 41
- Dünya Katılım: 10
- Hayat Finans: 7
- Kuveyt Türk: 43
- Türkiye Finans: 23

## Bilinen kapsam açıkları

- Adil Katılım `config/banks.json` içinde bulunuyor ancak `scanner_ready=false`; final veri kapsamı açısından tamamlanmalıdır.
- Vakıf Katılım için snapshot'ta **23** güncel `unclassified` kayıt bulunuyor; kampanya sınıflandırması kapanmadan final kapsamı tamamlanmış sayılmamalıdır.
- Standart finansman ürünleri bu snapshot'ta 5 bankada tamamlanmış/işlenmiş durumdadır; diğer katılım bankalarının standart ürün katalogları final öncesinde tamamlanmalıdır.

Bu dosya özellikle yarışma tesliminde kapsamın olduğundan daha geniş gösterilmemesi için mevcut durumu şeffaf biçimde kaydeder.
