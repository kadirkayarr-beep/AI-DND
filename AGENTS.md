# Agent guide

Kurallar için tek kaynak `CLAUDE.md`'dir ("Çalışma ve test disiplini", "Sahibin kuralları"). Bu dosya yalnızca nerede ve nasıl çalışıldığını söyler; çelişkide `CLAUDE.md` kazanır.

## Güncel çalışma (2026-11-12)

- Depo: `kadirkayarr-beep/AI-DND`. Güncel ortak dal `main`'dir; işler `task/<ad>-<tarih>` dallarında yapılır ve `main`'e pull request ile girer.
- Her iş kendi worktree'sinde yapılır, aynı klasörde tek yazıcı çalışır. Açık worktree'ler: `git worktree list`.
- Push, merge ve PR yalnızca Kadir'in o işlem için taze onayıyla yapılır; force push ve dal silme yoktur. İzinler `.claude/settings.json` dosyasındadır.
- Plan, kapsam ve harcama değişikliklerini Kadir onaylar. Güncel plan ve devir belgeleri: `docs/design/INDEX.md`.
- Açık parklar için tek defter: `docs/agents/debt-register.md`.

## Test

- Python ürün testleri yalnız korumalı WSL başlatıcısıyla koşulur (Git Bash'ten): `bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <slot> <worktree> test|par|node|codegen ...`. Düz Windows Python ya da `dev.ps1` ile ürün testi koşulmaz; `linux_guarded_launcher.py` ve koruma değiştirilmez.
- Hangi set ne zaman koşulur: `CLAUDE.md` ve `docs/agents/implementer-preamble.md`.
- CI: 'AI-DND bounded verification', `main` push ve pull request'te çalışır.

## Modeller ve anahtarlar

- Oyun modeli zinciri: Gemini, sonra Claude Haiku, sonra yerel Gemma; yalnız yerel oyunda açıktır (`.\start_local.ps1 -LocalPlay`).
- Anahtarlar depo dışında durur; okunmaz, yazdırılmaz, commit edilmez.

## Arayüz

- Kampanya ve oyun arayüzü: `artifacts/ai-dnd-experience`
- `artifacts/ai-dnd-web`: yalnız oturum yüzeyi, kampanya özelliği yok
- `artifacts/api-server`: oyun API'si değildir

## Eski kayıtlar

Cursor ve Replit dönemine ait kurallar (ortak dal `dev/ai-dnd`, `AI-DND-c-merge` klasörü, "main'e asla push/merge yok") 12 Kasım 2026'da bu dosyadan çıkarıldı; eski metin git geçmişindedir. `attached_assets/` tarihsel istem arşividir, güncel şartname değildir.
