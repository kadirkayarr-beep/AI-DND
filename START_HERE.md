# Start here — AI-DND

## Okuma sırası

1. [CLAUDE.md](CLAUDE.md): kurallar (tek kaynak).
2. [AGENTS.md](AGENTS.md): nerede ve nasıl çalışılır, test başlatıcısı, modeller.
3. [docs/design/INDEX.md](docs/design/INDEX.md): güncel plan ve devir belgeleri.
4. [docs/agents/debt-register.md](docs/agents/debt-register.md): açık parklar.
5. Yalnız gerektiğinde: [API guide](ai-dnd/api/README.md), [engine guide](ai-dnd/README.md), `lib/api-spec/openapi.yaml`, [development docs](ai-dnd/docs/README.md).

## Güncel durum

Güncel ortak dal `main`'dir; işler `task/*` dallarında ve ayrı worktree'lerde yapılır, `main`'e pull request ile girer. Bu dosya anlık durum tutmaz: çalışan süreçler, portlar ve son koşu sonuçları devir belgesindedir.

## Eski kayıtlar

- 22 Ekim 2026 ortak taban, o günkü bilinen kırıklar (`TwoPlayerIsolationTests`) ve doğrulama ayrıntıları: [COMMON_BASELINE_2026-10-22.md](COMMON_BASELINE_2026-10-22.md). Tarihsel kayıttır; güncel geçiş iddiası değildir.
- Depo dışına taşınan kitaplar ve teslimatlar: [EXTERNAL_SOURCES.md](EXTERNAL_SOURCES.md).
- Eski kanıt ve arşiv toplu okunmaz; yalnız adı verilen tek kayıt açılır.
- Bu dosyanın 22 Ekim tarihli eski hâli (çalışan süreç numaraları, `dev/ai-dnd` ortak dalı, `dev.ps1` günlük kontrolleri) 12 Kasım 2026'da çıkarıldı; eski metin git geçmişindedir.
