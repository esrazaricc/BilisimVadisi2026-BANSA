BANSA — Katılım Bankacılığı Kampanya Analiz Sistemi

BANSA, katılım bankalarının resmî web sitelerinde yayımlanan kampanya ve finansman içeriklerini otomatik olarak keşfeden, analiz eden, yapılandırılmış veriye dönüştüren ve karşılaştırılabilir şekilde sunan bir karar destek sistemidir.

Proje; farklı bankalarda dağınık, farklı formatlarda ve sürekli değişen kampanya verilerini tek bir merkezde toplamak, güncel tutmak ve kullanıcıların bankalar arasındaki fırsatları daha kolay karşılaştırabilmesini sağlamak amacıyla geliştirilmiştir.

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması — Katılım Bankacılığı Ürün Analiz Sistemi senaryosu kapsamında geliştirilmektedir.

Özellikler

Katılım bankalarının resmî kampanya sayfalarından otomatik veri keşfi

Statik ve dinamik web sayfaları için farklı tarama yöntemleri

Selenium, HTTP istekleri ve JSON API tabanlı veri toplama desteği

Kampanya detay sayfalarının canlı olarak yenilenmesi

Yeni kampanyaların otomatik tespiti

Kampanya içerik değişikliklerinin algılanması

Güvenli kampanya kaldırma / pasife alma mekanizması

Kampanya ve hizmet kayıtlarının birbirinden ayrılması

Mükerrer kayıt kontrolü

Kampanya sınıflandırması

Finansman ve kampanya karşılaştırma alanlarının otomatik çıkarılması

Banka bazlı kalite kontrol ve veri doğrulama adımları

SQLite tabanlı merkezi veri yönetimi

Streamlit tabanlı kullanıcı arayüzü

Banka bazlı yedekleme ve hata durumunda rollback desteği

UTF-8 ve emoji içeren içeriklerde güvenli veri işleme

Entegre Bankalar

Canlı tarama altyapısı aktif olan bankalar:

Banka

Durum

Albaraka Türk

✅ Aktif

Dünya Katılım

✅ Aktif

Hayat Finans

✅ Aktif

Kuveyt Türk

✅ Aktif

Türkiye Finans

✅ Aktif

Vakıf Katılım

✅ Aktif

Ziraat Katılım

✅ Aktif

Yapılandırması bulunan ancak otomatik taraması henüz aktif olmayan bankalar:

Banka

Durum

Adil Katılım

⏳ Geliştirme aşamasında

T.O.M. Katılım

⏳ Geliştirme aşamasında

Türkiye Emlak Katılım

⏳ Geliştirme aşamasında

Banka kaynakları ve tarama ayarları config/banks.json üzerinden yönetilmektedir.

Sistem Akışı

Resmî Banka Web Siteleri
          ↓
Kampanya Keşfi
          ↓
Detay Sayfalarının Çekilmesi
          ↓
İçerik Temizleme ve Normalizasyon
          ↓
SQLite Veritabanı
          ↓
Kampanya Sınıflandırması
          ↓
Karşılaştırma Alanlarının Çıkarılması
          ↓
Banka Bazlı Kalite Kontrol
          ↓
Streamlit Dashboard

Canlı güncelleme sırasında yalnızca yeni kayıtlar eklenmez. Mevcut kampanyaların içerikleri de yeniden kontrol edilir. Örneğin bir finansman kampanyasının kâr payı oranı banka sitesinde değiştiğinde ilgili karşılaştırma alanları yeniden üretilerek Streamlit ekranına güncel değer yansıtılır.

Çıkarılan Karşılaştırma Alanları

Finansman Kampanyaları

Finansman türü

Kâr payı oranı

Finansman tutarı

Vade süresi

Taksit sayısı

Ödemesiz dönem

Tahsis ücreti

Masraf bilgisi

Diğer Kampanyalar

Kampanya türü

Ödül miktarı

İndirim oranı

Alışveriş / ödül puanı

Kampanya başlangıç ve bitiş tarihi

Kampanya avantajı

Hedef kitle

Kampanya koşulları

Proje Yapısı

bansa_project/
│
├── config/
│   ├── banks.json
│   ├── campaign_classification_overrides.json
│   ├── campaign_content_overrides.json
│   ├── campaign_url_aliases.json
│   └── finance_extraction_overrides.json
│
├── data/
│   └── campaigns.db
│
├── pages/
│   ├── 1_Metin_Analizi.py
│   ├── 2_Kampanyalar.py
│   ├── 3_Karsilastirma.py
│   ├── 4_Chatbot.py
│   ├── 5_Ham_Sayfalar.py
│   └── 6_Banka_Taramasi.py
│
├── scripts/
│   ├── run_all_banks_live_update.py
│   ├── refresh_live_campaigns.py
│   ├── sync_campaigns_to_db.py
│   ├── classify_campaign_records.py
│   ├── extract_comparison_fields.py
│   └── ...
│
├── src/
│   ├── classification/
│   ├── database/
│   ├── extraction/
│   ├── processing/
│   └── scraping/
│
├── tests/
│
├── app.py
├── streamlit_app.py
├── requirements.txt
└── README.md

Kurulum

1. Projeyi klonlayın

git clone https://github.com/esrazaricc/bns.git
cd bns/bansa_project

2. Sanal ortam oluşturun

Windows PowerShell:

python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

3. Bağımlılıkları yükleyin

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Dinamik sayfa taraması kullanılan ortamlarda Selenium da gereklidir:

python -m pip install selenium

Streamlit Uygulamasını Çalıştırma

python -m streamlit run streamlit_app.py

Windows üzerinde alternatif olarak:

.\start_dashboard.cmd

Uygulama üzerinden kampanyalar görüntülenebilir, bankalar arasında karşılaştırma yapılabilir ve veri toplama sonuçları incelenebilir.

Canlı Banka Güncellemesi

Tüm aktif bankaları kontrol etmek için:

python -X utf8 .\scripts\run_all_banks_live_update.py

İlk veya kontrollü çalıştırmalarda kampanya kaldırma işlemlerini devre dışı bırakmak için:

python -X utf8 .\scripts\run_all_banks_live_update.py --skip-removals

Sadece belirli bir bankayı güncellemek için:

python -X utf8 .\scripts\run_all_banks_live_update.py --bank "Albaraka Türk" --skip-removals

Sistemin çalıştıracağı bankaları veri değiştirmeden görmek için:

python -X utf8 .\scripts\run_all_banks_live_update.py --dry-run

Güvenli Güncelleme Yaklaşımı

Canlı kampanya sistemi veri kaybını önlemek amacıyla kontrollü çalışır.

Bir kampanyanın tek bir taramada listede bulunmaması doğrudan silinmesi için yeterli değildir. Sistem; kampanyanın durumu, URL erişilebilirliği, önceki taramalar ve bitiş tarihi gibi sinyalleri dikkate alarak kaldırma kararını verir.

Banka bazlı güncelleme öncesinde veritabanı yedeği alınır. Bir bankanın güncellemesinde kritik hata oluşursa ilgili işlem rollback edilerek mevcut çalışan veri korunur.

Veritabanı

Ana veritabanı:

data/campaigns.db

SQLite üzerinde kampanya kayıtlarının yanı sıra karşılaştırma için çıkarılan finansman, avantaj ve hedef kitle alanları da tutulmaktadır.

Çalışma sırasında oluşan log, backup, kampanya snapshot ve rapor dosyaları Git deposunda tutulmaz.

Testler

Testleri çalıştırmak için:

python -m pytest

Test altyapısı; veri keşfi, URL normalizasyonu, kampanya sınıflandırması, finansman alanı çıkarımı, güvenli senkronizasyon, banka özelindeki guardrail'ler ve veri bütünlüğü kontrollerini kapsamaktadır.

Kullanılan Teknolojiler

Python

Streamlit

SQLite

Pandas

Requests

BeautifulSoup

Selenium

Pytest

HTML / JSON tabanlı web veri kaynakları

Veri Kaynağı

Sistem yalnızca ilgili bankaların kamuya açık resmî web sayfalarındaki kampanya ve finansman içeriklerini analiz etmek üzere tasarlanmıştır.

Banka web sayfalarındaki yapı veya içerik değişiklikleri tarama sonuçlarını etkileyebileceği için banka bazlı doğrulama ve kalite kontrol mekanizmaları kullanılmaktadır.

Proje Durumu

Proje aktif olarak geliştirilmektedir. Canlı veri toplama, veri kalitesi, yeni banka entegrasyonları ve karşılaştırma doğruluğu üzerinde çalışmalar devam etmektedir.
