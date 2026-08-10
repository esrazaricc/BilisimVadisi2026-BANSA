BANSA – Katılım Bankacılığı Kampanya Analiz Sistemi
Katılım bankalarının resmî web sayfalarındaki kampanya ve finansman içeriklerini keşfeden, detay sayfalarını canlı olarak güncelleyen, verileri SQLite'a aktaran ve Streamlit üzerinden karşılaştırılabilir biçimde sunan sistem.

Güncel canlı entegrasyon
config/banks.json içindeki scanner_ready=true bankalar:

Albaraka Türk
Dünya Katılım
Hayat Finans
Kuveyt Türk
Türkiye Finans
Vakıf Katılım
Ziraat Katılım
Henüz otomatik taraması aktif olmayan bankalar:

Adil Katılım
T.O.M. Katılım
Türkiye Emlak Katılım
Temel özellikler
Resmî banka kampanya sayfalarından otomatik keşif
Dinamik/Selenium ve JSON API tabanlı kaynak desteği
Kampanya detay sayfalarının canlı yenilenmesi
SQLite (data/campaigns.db) üzerinde güncel kayıt yönetimi
Kampanya / hizmet bilgisi / duplicate ayrımı
Kampanya sınıflandırması ve banka özelindeki kalite guardrail'leri
Finansman alanları:
kâr payı oranı
finansman tutarı
vade
taksit
tahsis ücreti
masraf bilgisi
Kampanya alanları:
ödül
indirim
puan
kampanya süresi
hedef kitle / koşullar
Streamlit dashboard ve karşılaştırma ekranı
Güvenli banka bazlı DB yedeği ve rollback
Kampanya kaldırmalarında tek taramada silmeme yaklaşımı
UTF-8/emoji güvenli canlı tarama
Kurulum
PowerShell:

python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Bu GitHub sürümünde güncel data/campaigns.db snapshot'ı bulunduğu için dashboard doğrudan açılabilir:

python -m streamlit run streamlit_app.py
Alternatif:

.\start_dashboard.cmd
Tüm bankaları canlı güncelleme
Önce güvenli test:

python -X utf8 .\scripts\run_all_banks_live_update.py --dry-run
İlk manuel canlı testte kaldırmaları devre dışı bırakmak için:

python -X utf8 .\scripts\run_all_banks_live_update.py --skip-removals
Normal güncelleme:

python -X utf8 .\scripts\run_all_banks_live_update.py
Tek banka:

python -X utf8 .\scripts\run_all_banks_live_update.py --bank "Albaraka Türk" --skip-removals
Önemli veri dosyaları
data/campaigns.db: Streamlit'in kullandığı güncel SQLite snapshot'ı.
Diğer data/ çıktıları (log, backup, audit, fetch snapshot, report vb.) çalışma sırasında otomatik üretilir ve Git'e alınmaz.
Test
python -m pytest
Haftalık GitHub güncellemesi
git status
git add -A
git status
git commit -m "Weekly project update"
git push origin main
Commit öncesinde data/backups, data/logs, data/campaign_pages, __pycache__ veya .pytest_cache gibi çalışma çıktılarının staged listesinde olmaması gerekir.
