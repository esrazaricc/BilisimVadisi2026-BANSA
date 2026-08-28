# BANSA V31 – Şema Odaklı Statik Dashboardlar

- BDDK 27.08.2026 listesine göre 10 katılım bankası sabittir.
- Finansman dashboardu 12 kategori için kullanıcı tarafından belirlenen kategori-özel sütunları kullanır.
- Kampanya dashboardu 18 kategori için kategori-özel sütunları kullanır.
- Runtime web scraping yoktur; veriler statik CSV snapshotlarından okunur.
- Eksik bilgi boş/NaN yerine “Bilgi yok – resmî kaynakta yayımlanmamış” olarak gösterilir.
- Örnek finansman senaryoları ana tablonun altında ve yalnız birebir doğrulanmışsa sayısal gösterilir.
- Kampanya örnekleri minimum harcama/limit/vade gibi açık uygunluk koşulları kontrol edilerek oluşturulur; güvenli değilse sayısal sonuç üretilmez.
