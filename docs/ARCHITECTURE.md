# Sistem Mimarisi ve Veri Akışı

BANSA iki ayrı veri akışını bilinçli olarak ayırır:

1. **Kampanyalar** - süreli avantaj/ödül/indirim/finansman kampanyaları.
2. **Standart finansman ürünleri** - bankaların sürekli ürün katalogları ve ürün kuralları.

```text
Resmî banka web siteleri
        |
        v
Discovery / requests / BeautifulSoup / gerektiğinde Selenium
        |
        v
Metin temizleme ve ön işleme
        |
        +--> Kampanya sınıflandırma + finansal bilgi çıkarımı
        |
        +--> Standart ürün discovery + rule engine + nitel özellik çıkarımı
        |
        v
SQLite çalışma snapshot'ı ----> PostgreSQL ilişkisel şema
                                      |
                                      v
                                Streamlit dashboard
                                      |
                                      v
                           Karşılaştırma / chatbot arayüzü
```

## PostgreSQL

ER şeması `postgresql/schema.sql` altında; görsel diyagram `postgresql/BANSA_ER_DIAGRAM.png` dosyasındadır. Finansman Karşılaştırması sayfası `src/postgres_repository.py` üzerinden PostgreSQL okur ve bağlantı yoksa SQLite'a sessiz fallback yapmaz.

## Canlı güncelleme

- Kampanya ana runner: `scripts/run_all_banks_live_update.py`
- Standart ürün runner: `scripts/run_standard_products_live_update.py`
- Değişiklik tipleri: yeni ürün/kampanya, içerik/koşul değişimi, yeniden görünme ve olası kaldırılma.
- Tek missing scan ile kayıt silinmez; güvenli kaldırma yaklaşımı kullanılır.

## Geçiş durumu

PostgreSQL'e veri taşıma şeması ve migration tamamlanmıştır. Finansman Karşılaştırması PostgreSQL okuma katmanını kullanır. Diğer bazı legacy sayfalar ve canlı yazma pipeline'ları SQLite geçiş katmanını kullanmaya devam etmektedir; bu durum `PROJECT_STATUS.md` içinde açıkça belirtilir.
