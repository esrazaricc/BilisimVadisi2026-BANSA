# BANSA V22 · Live Demo Final

## Amaç
V21 doğruluk/güvenlik çekirdeğini koruyup jüri canlı demosuna uygun doğal sohbet ve karar dashboard'ları sunmak.

## Chatbot
- İki veya daha fazla banka için finansman karşılaştırması tutar/vade eksikse doğrudan genel katalog cevabı vermez; eksik senaryo bilgisini ister.
- Tutar ve vade ayrı mesajlarla verilebilir. Raw history üzerinden comparison anchor korunur ve iki slot birleştirilir.
- Yeni explicit banka/ürün/topic eski bağlamı ezer.
- V21 Dünya Katılım taşıt kaynak düzeltmesi korunur: kaynak vade bantlarını yayımlar, yüzdesel finansman oranı türetilmez.
- V21 Enerya Karz-ı Hasen alias/routing düzeltmesi korunur.

## Finansman Dashboard
- Finansman ailesi seçildiği anda o ailedeki **tüm bankaların tüm standart ürünleri** ana tabloya gelir.
- Bireysel + ticari aileler dinamik olarak listelenir: konut, taşıt, ihtiyaç, alışveriş, arsa, iş yeri, ticari, gayri nakdi, tarım, leasing, sürdürülebilir, gayrimenkul vb.
- Tabloda mümkün olduğunca: banka, ürün, kapsam, fiyatlama, limit, vade, finansman oranı/kuralı, calculator constraint, ücretler, kullanım amacı, hedef kitle, finansman yapısı, ödeme yapısı, para birimi, teminat, kanal, dış ticaret, özel koşul, kaynak, son kontrol alanları yer alır.
- Kaynakta hiç veri olmayan sütunlar otomatik gizlenir; doğrulanmamış sayı üretilmez.
- Banka filtresi boşsa tüm bankalar görünür.
- Opsiyonel tutar/vade senaryosu calculator-first BANSA çekirdeğini kullanır ve doğrulanmış sayısal sonuçları ayrı tabloda gösterir.
- Banka detay seçimi: seçilen bankanın aynı ailedeki tüm ürünleri + tek ürünün tüm doğrulanmış detay alanları.
- Kritik özet: en düşük doğrulanmış aylık/toplam (senaryo varsa), en fazla ürün, en uzun yayımlanmış vade, en yüksek yayımlanmış limit/oran gibi yalnız eldeki veriden türetilen özetler.

## Kampanya Dashboard
- Yalnız aktif kampanyalar.
- Kampanya türü seçildiği anda seçilen türdeki tüm banka kampanyaları görünür; 5 kampanya sınırı kaldırılmıştır.
- Banka ve anahtar kelime filtresi opsiyoneldir.
- Tabloda taksit, vade, kâr payı/finansman alanları, indirim/iade, ödül, puan, harcama/fayda sınırları, tarih, koşullar ve kaynak bulunur.
- Banka detay seçimi seçilen bankanın tüm ilgili kampanyalarını ve tek kampanyanın tüm doğrulanmış alanlarını gösterir.
- Kritik özet: en fazla taksit, en uzun finansman vadesi, en yüksek indirim/ödül/fayda, en düşük giriş harcaması, en yakın bitiş.

## UI
- Yüksek kontrast sidebar.
- Üç jüri paneli: BANSA Asistanı / Finansman Karşılaştırması / Kampanya Karşılaştırması.
- Streamlit'in legacy sayfa navigasyonu gizli.
- Tablolar geniş ekran ve yatay kaydırma için yoğun bilgi mimarisiyle tasarlandı.
- CSV dışa aktarımı mevcut.

## Güvenlik
- LLM finansal gerçekliğin kaynağı değildir.
- Sayısal değerler verified deterministic layer / official price table / calculator adapter kaynaklıdır.
- Historical snapshot current winner üretmez.
- Calculator input ceiling ürün LTV/finansman politikasıyla karıştırılmaz.
- Product/campaign topic fallback alakasız kayıtla doldurulmaz.
