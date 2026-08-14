# Bilinen Açıklar / Sonraki Adımlar

1. **LLM entegrasyonu henüz yok.** Mevcut chatbot ve extraction ağırlıklı olarak kural tabanlıdır. Yarışma şartnamesindeki dil ajanı hedefi için lokal/açık kaynak bir LLM katmanı ve yapılandırılmış PostgreSQL sorgulama aracı eklenmelidir.
2. **PostgreSQL geçişi hibrit aşamada.** Finansman Karşılaştırması PostgreSQL'den okur; bazı kampanya sayfaları ve canlı write pipeline'ları SQLite kullanmaya devam eder.
3. **Adil Katılım scraper kapsamı açık.** `scanner_ready=false`.
4. **Vakıf Katılım sınıflandırması açık.** Snapshot'ta güncel unclassified kayıtlar vardır.
5. **Standart ürün kapsamı 5 banka ile sınırlı.** Final öncesi BDDK kapsamındaki diğer bankalar tamamlanmalıdır.
6. **Sunum ve demo teslimleri henüz bu repoda gerçek dosya olarak yok.** `presentation/` ve `demo/` klasörlerindeki kontrol listeleri takip edilmelidir.
