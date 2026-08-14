# Kurulum ve Çalıştırma

## Gereksinimler

- Windows/Linux/macOS
- Python 3.12 önerilir
- PostgreSQL 17+
- Chromium tabanlı tarayıcı (Selenium gereken banka akışları için)

## Python ortamı

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## PostgreSQL oluşturma

```sql
CREATE DATABASE bansa_db;
```

Şema:

```text
\c bansa_db
\i 'C:/path/to/project/postgresql/schema.sql'
```

PowerShell oturumunda bağlantı değişkeni:

```powershell
$env:POSTGRES_DSN="postgresql://postgres:PAROLA@127.0.0.1:5432/bansa_db"
```

SQLite yarışma snapshot'ını PostgreSQL'e taşıma:

```powershell
python -X utf8 .\scripts\migrate_sqlite_to_postgresql.py --replace
python -X utf8 .\scripts\audit_postgresql_migration.py
```

## Dashboard

PostgreSQL parolasını komut satırına açık yazmadan başlatmak için:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\run_streamlit_postgresql.ps1
```

veya `POSTGRES_DSN` zaten tanımlıysa:

```powershell
python -m streamlit run .\Ana_Sayfa.py
```

## Test

```powershell
python -m pytest
```
