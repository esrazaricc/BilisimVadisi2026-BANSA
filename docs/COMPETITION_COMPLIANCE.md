# TEKNOFEST 2026 Şartname Uyum Kontrolü

Bu kontrol listesi 2. Senaryo teknik şartnamesine göre hazırlanmıştır.

| Beklenti | Repo karşılığı | Durum |
|---|---|---|
| Çalışan proje kaynak kodu | `src/`, `scripts/`, `pages/`, `Ana_Sayfa.py` | Var |
| Metin ön işleme | `src/processing/`, extraction yardımcıları | Var |
| Finansal bilgi çıkarımı | `src/extraction/` | Var |
| Kampanya sınıflandırma | `src/classification/`, config override'ları | Var |
| Veri normalizasyonu | extraction + rule engine | Var |
| Bankalar arası karşılaştırma | Streamlit karşılaştırma sayfaları | Var |
| Dashboard | Streamlit | Var |
| Chatbot | `pages/4_Chatbot.py`, `src/chatbot.py` | Var; mevcut sürüm kural tabanlı |
| On-prem DB | PostgreSQL + SQLite snapshot | Var |
| ER şeması | `postgresql/` | Var |
| Açık kaynak lisans | `LICENSE` Apache-2.0 | Var |
| Bağımlılık listesi | `requirements.txt` | Var |
| Adım adım kurulum | `docs/INSTALLATION.md` | Var |
| Veri seti | `dataset/` + `data/campaigns.db` | Var |
| Model/LLM lokal çalıştırma | - | **Açık** |
| Tüm BDDK kapsamındaki bankalar | - | **Açık** |
| Demo videosu | `demo/` | **Hazırlanmalı** |
| Sunum PDF/PPTX | `presentation/` | **Hazırlanmalı** |
| Haftalık GitHub güncellemesi | Git commit geçmişi | Süreçte takip edilmeli |
| GitHub etiketi/topic | `BilisimVadisi2026` | Repo ayarlarında eklenmeli |
