# GitHub Hazırlık Raporu

Kaynak: `bansa_project114august.zip`  
Hazırlama tarihi: 14 Ağustos 2026

## Temizlenenler

- `data/backups/` ve yüzlerce tarihsel DB yedeği kaldırıldı.
- `data/logs/`, `data/campaign_pages/` ve yeniden üretilebilir runtime raporları kaldırıldı.
- `config/backups/` kaldırıldı.
- `__pycache__`, `.pyc`, `.pytest_cache` kaldırıldı.
- Eski root patch/audit scriptleri **silinmedi**; `archive/legacy_root_scripts/` altına taşındı.
- Eski deployment dosyaları `archive/legacy_deployment/` altına taşındı.
- Mevcut yarışma snapshot'ı `data/campaigns.db` korundu.

## Eklenenler

- Apache License 2.0 `LICENSE`
- Güncel `.gitignore` ve `.env.example`
- Eksik runtime bağımlılıkları (`selenium`, `psycopg`) içeren `requirements.txt`
- `dataset/` CSV/JSON dışa aktarımları
- Şartname odaklı `docs/` dokümantasyonu
- `GITHUB_UPLOAD_CHECKLIST.md`
- Sunum/demo klasörleri için teslim kontrol notları

## Snapshot

- Güncel kampanya: 527
- Standart ürün: 124
