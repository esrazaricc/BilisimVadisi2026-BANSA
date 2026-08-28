# BANSA V41 · Finansman Oran Senkronizasyonu

Bu sürüm V40 iç finansman hesaplama katmanını korur; chatbot, kampanya UI ve kart karşılaştırma mantığına dokunmadan finansman oranlarının kullanıcıya daha doğru etiketlenmesini sağlar.

## Yapılan ana değişiklikler

- Türkiye Finans konut/taşıt/ihtiyaç fiyat tabloları resmî fiyat tablosu olarak korunmuştur.
- Albaraka Türk için resmî Jet Finansman ekranında görünen `Kar Oranı %0,98 (Size Özel)` değeri V41 katalog oranı olarak güncellenmiştir.
- Vakıf Katılım için Finansman Hesaplama ekranında görünen `Kar Oranı %3,99` değeri konut/taşıt/ihtiyaç hesaplama modeline güncellenmiştir.
- Kuveyt Türk ve Dünya Katılım sayfalarında kâr oranı sabit yayımlanmış tablo olarak değil, hesaplama aracında oran/senaryo girdisi olarak göründüğü için bu bankalar artık `resmî hesaplama aracındaki senaryo oranı` etiketiyle gösterilir.
- Eski `BANSA resmî kaynak modeli` etiketi tek torba olmaktan çıkarıldı; artık sonuç türü kaynak niteliğine göre ayrışır:
  - `Resmî fiyat tablosundan hesaplandı`
  - `Resmî hesaplama ekranındaki oranla hesaplandı`
  - `Senaryo oranıyla hesaplandı`

## Korunan davranışlar

- “Hesaplama aracını aç” ana aksiyon olarak kullanılmaz.
- BANSA kendi içinde aylık taksit ve toplam geri ödeme hesaplar.
- Türkiye Emlak Katılım ve Ziraat Katılım ilgili konut/taşıt/kişiye özel durumlarında sayısal karşılaştırmaya zorla sokulmaz.
- Büyük detay tabloları varsayılan kapalı kalır.
- V39 kampanya UI, kart karşılaştırma ve chatbot bağlam akışı korunmuştur.

## Doğruluk notu

Kuveyt Türk ve Dünya Katılım gibi bazı resmi sayfalarda hesaplama aracı vardır; fakat sayfa HTML'inde kâr oranı sabit, yayımlanmış fiyat tablosu gibi dönmez. Bu nedenle BANSA bu oranları “canlı banka teklifi” veya “resmî sabit oran” olarak adlandırmaz; sadece hesaplama senaryosu etiketiyle gösterir.
