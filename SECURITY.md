# Security Notes

- Finansal cevaplarda doğrulanmamış sayısal değer üretmeyin.
- `.env`, parola, token, API anahtarı ve PostgreSQL connection string'i commit etmeyin.
- `data/runtime/chat_history.sqlite` kullanıcı konuşma geçmişi içerebildiği için repository dışında tutulur.
- Banka kaynak linkleri resmî detay sayfalarına çözülür; yeni source resolver değişikliklerinde generic kategori sayfalarına fallback davranışı test edilmelidir.
- Live calculator sonucu ile ürün uygunluk/vade kuralları birbirinden ayrı kanıt türleridir.
