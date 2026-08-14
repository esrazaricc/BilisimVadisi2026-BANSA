# GitHub'a Yayınlama

## 1. Yeni repo oluştur

Repo public olmalı. Repo açıklamasında TEKNOFEST 2026 Yapay Zekâ Dil Ajanları - 2. Senaryo ve takım adı yer almalıdır.

GitHub repository **Topics** alanına en az:

- `BilisimVadisi2026`
- `teknofest-2026`
- `nlp`
- `participation-banking`

eklenmesi önerilir.

## 2. İlk commit

```powershell
git init
git branch -M main
git add -A
git status
git commit -m "TEKNOFEST 2026 - BANSA project snapshot"
git remote add origin GITHUB_REPO_URL

git push -u origin main
```

`git status` çıktısında `.env`, backup DB'ler, loglar veya `__pycache__` görünmemelidir.

## 3. Yarışma boyunca

Şartname doğrultusunda en az haftalık güncelleme geçmişi korunmalıdır:

```powershell
git add -A
git commit -m "Weekly project update: ..."
git push
```

## 4. Final öncesi

- `presentation/` içine PPTX + PDF
- `demo/README.md` içine demo video bağlantısı
- README içine takım adı/üyeler ve görevleri
- Veri seti public erişim kontrolü
- Apache-2.0 lisans kontrolü
- `python -m pytest`
- PostgreSQL migration audit
- Repo topic: `BilisimVadisi2026`
