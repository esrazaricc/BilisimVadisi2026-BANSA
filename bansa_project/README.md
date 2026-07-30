# BANSA Katılım Bankacılığı Kampanya Analiz Sistemi

Bu aşamadaki proje, katılım bankalarının resmî web sayfalarını analiz ederek sayfaları `campaign`, `standard_product` ve `other` olarak sınıflandırır. Yalnızca gerçek kampanya olarak belirlenen sayfalardan yapılandırılmış alanlar çıkarılır ve kampanya ekranına aktarılır.

## Bu aşamadaki kapsam

- BDDK kapsamındaki 10 katılım bankası seçim listesinde bulunur.
- Albaraka Türk için otomatik kampanya bağlantısı keşfi hazırdır.
- Diğer dokuz banka listede görünür ancak otomatik tarama kuralları henüz kapalıdır.
- URL veya yapıştırılan metin üzerinden analiz yapılabilir.
- Kampanya / standart ürün / diğer sayfa ayrımı yapılır.
- Kampanya tarihi, kâr payı, vade, taksit, ödül, indirim, puan ve hedef kitle alanları çıkarılır.
- Sonuçlar SQLite veritabanında saklanır.
- Kampanya listesi, karşılaştırma ekranı, temel yerel chatbot ve ham sayfa ekranı bulunur.

## Kurulum

```powershell
cd C:\Users\Esra\Desktop\bansa_campaign_ai
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\init_db.py
python -m streamlit run app.py
```

Örnek verileri yüklemek isterseniz:

```powershell
python scripts\load_demo.py
```

Testleri çalıştırmak için:

```powershell
python -m pytest
```

## Klasör yapısı

```text
bansa_campaign_ai/
├── app.py
├── requirements.txt
├── config/
│   └── banks.json
├── pages/
│   ├── 1_Metin_Analizi.py
│   ├── 2_Kampanyalar.py
│   ├── 3_Karsilastirma.py
│   ├── 4_Chatbot.py
│   ├── 5_Ham_Sayfalar.py
│   └── 6_Banka_Taramasi.py
├── scripts/
│   ├── init_db.py
│   └── load_demo.py
├── src/
│   ├── banks.py
│   ├── chatbot.py
│   ├── config.py
│   ├── db.py
│   ├── pipeline.py
│   ├── repository.py
│   ├── classification/
│   │   └── campaign_detector.py
│   ├── extraction/
│   │   ├── normalizers.py
│   │   └── rule_extractor.py
│   └── scraping/
│       ├── campaign_discovery.py
│       └── http_client.py
└── tests/
    ├── test_detector.py
    ├── test_discovery.py
    └── test_extractor.py
```
