# GitHub'a Yükleme Rehberi

Bu klasör BANSA V24'ün GitHub için temizlenmiş sürümüdür.

## 1. Yeni repository oluştur

GitHub üzerinde boş bir repository oluştur. README / .gitignore ekleme; bu klasörde ikisi de hazır.

## 2. İlk push

Proje klasöründe:

```bash
git init
git branch -M main
git add .
git status
git commit -m "BANSA V24 initial release"
git remote add origin <GITHUB_REPOSITORY_URL>
git push -u origin main
```

## 3. Commit öncesi kontrol

Aşağıdakiler Git'e girmemelidir:

- `.env`
- `.venv/`
- `__pycache__/`
- `data/logs/`
- `data/backups/`
- `data/runtime/chat_history.sqlite`
- kişisel PostgreSQL parolaları veya connection string'leri

Aşağıdakiler portable demo için repository'de tutulur:

- `data/campaigns.db`
- `data/campaign_page_index.json`
- `data/standard_products/*.json`
- `data/runtime/finance_snapshot.sqlite`
- `data/runtime/finance_snapshot_manifest.json`
- `data/rag/rag_chunks.jsonl`
- `data/rag/rag_dense_vectors.npy`
- RAG manifest dosyaları

## 4. Kurulum testi

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run Ana_Sayfa.py
```

Alternatif olarak `RUN_BANSA_FINAL_UI.bat` kullanılabilir.

## 5. Ortam değişkenleri

`.env.example` dosyasını kopyalayıp yerelde `.env` olarak kullan. `.env` Git tarafından yok sayılır.

Yerel Qwen naturalizer çalışmıyorsa BANSA doğrulanmış/deterministik doğal fallback cevabına döner.

## 6. PostgreSQL

Portable demo SQLite snapshot ile açılır. PostgreSQL kullanmak istersen parola repository'ye yazılmamalı; `POSTGRES_DSN` yalnız yerel ortam değişkeni olarak verilmelidir.
