# Kalite kapısı taraması (2026-11-25)

Taban: `origin/main` `56111e4e` (dalga 3 sonu, main CI "AI-DND bounded verification" ve "AI-DND quality gate" yeşil). Plan: `docs/superpowers/plans/2026-11-25-kalite-kapisi-ve-defter-plani.md`.

Bu tarama kod değiştirmez. Bulgular borç defterine (`docs/agents/debt-register.md`) bağlandı; çözümleri ikinci planın (borç sıfırlama) işidir. `kalite-taramasi-20261125/baseline.json` başlangıç ölçümüdür: ikinci plan sonunda aynı komutlar yeniden koşulur ve sayılar bununla karşılaştırılır ("yeni borç açılmadı" kanıtı).

## Araçlar, sürümler, lisanslar

| Araç | Sürüm | Lisans | Rol |
|---|---|---|---|
| ruff | 0.17.5 | MIT | kapı (F, E9) + ek tarama (B, BLE, SIM) |
| vulture | 2.14 | MIT | kapı (güven 80) + ek tarama (60) |
| size_lock_shrink + boyut testleri | repo | — | kapı |
| gitleaks | 8.30.1 (Windows ikilisi, sha256 release checksums.txt ile doğrulandı) | MIT | kapı |
| knip | 6.48.0 | — (bu taramada bakılmadı; önceden kurulu kapı aracı) | kapı |
| fallow | 3.45.0 | — | rapor |
| skylos | 5.8.0 | Apache-2.0 | rapor (`--no-upload`) |
| tsc (`pnpm run typecheck`) | repo | — | kapı (CI build) |
| bandit | 1.9.4 | Apache-2.0 | yeni (desloppify içinde de var) |
| pyright | 1.1.414 | MIT | yeni |
| import-linter | 2.17 | BSD-2 | yeni |
| radon | 6.0.1 | MIT | yeni |
| deptry | 0.25.1 | MIT | yeni |
| pip-audit | 2.10.1 | Apache-2.0 | yeni (yalnız paket adı+sürüm OSV/PyPI'ye gider; `--no-deps --disable-pip`, hiçbir paket kurulmaz) |
| pnpm audit | pnpm 12.15.0 | — | yeni (lock özeti npm registry'ye gider) |
| desloppify | yerel | — | mekanik tarama + T6 öznel inceleme |

Python araçları repo dışında `AI-DND-TOOLS/gate-venv-20261125` (Python 3.14.2) içinde. Yerelde Python 3.13 yok; CI 3.13 ile koşar. Yerel node 26.13.1 / pnpm 12.15.0, CI node 24 / pnpm 10.26.1. Engelleyen kapılar için asıl kanıt CI sonucudur. Ham çıktılar repo dışında (`AI-DND-TOOLS/gate-20261125/raw/`), sır değeri içermez (gitleaks `--redact`, bandit `code` alanı silindi).

## Sonuçlar

### Engelleyen kapılar (CI ile aynı komutlar)

| Kontrol | Sonuç |
|---|---|
| ruff F,E9 baseline'a karşı (baseline 113) | yeni bulgu 0 |
| ruff / knip baseline yalnız küçülür, vulture listesi yalnız küçülür, gitleaks baseline yalnız küçülür, size_lock yalnız küçülür | hepsi 0 (geçti) |
| vulture güven 80 + beyaz liste | 0 aday |
| boyut testleri + komşu set (slot 9) | 192 test, 0 hata |
| gitleaks tüm geçmiş | 2593 commit, yeni sızıntı yok |
| knip baseline'a karşı (baseline 332) | yeni bulgu 0 |
| tsc typecheck | 0 hata |
| tam paket | main CI 56111e4e yeşil (yerelde tam paket koşulmaz) |

### Rapor araçları ve yeni araçlar

| Araç | Bulgu | Defter |
|---|---|---|
| fallow (baseline 271) | yeni bulgu 0 | — |
| skylos | ilk iki koşu bitmedi (makinede gerçek `rg` yoktu); ripgrep 16.0.0 kurulunca 289 s'de bitti (2026-11-26): kullanılmayan işlev 19 (17'si yanlış alarm), import 7, değişken 22, döngü 3, analiz hatası 0; CI ile aynı | D-600, D-601 |
| ruff B/BLE/SIM (kapı dışı) | 1239: B023 589 (kaynak 17), SIM117 183, B905 167 (kaynak 12), BLE001 156 (kaynak 74), SIM102 50, … | D-591, D-584 eki |
| vulture güven 60 | 1483 aday (kaynak 475) | D-594 |
| bandit | kaynakta orta/yüksek önemde bulgu yok; testlerde B108 (sabit /tmp) ve B310; düşük önem kaynakta B105 7, B101 (assert) desloppify'de 101 | D-598 |
| pyright (standard) | 15171 hata: kaynak 1804, test 13210, scripts 105, eski kanıt 52; kaynakta "possibly unbound" 51 | D-588, D-589, D-595 |
| radon cc | kaynakta F 109, E 63, D 151, C 633 | D-592 |
| import-linter | iki sözleşme de kırık: motor paketleri -> api; routes_* bağımsızlığı (`campaign_store -> auth -> local_play -> main` döngüsü) | D-583 eki, D-590 |
| AST kenar sayımı (düz motor modülleri -> api) | 20 kenar, 14'ü `api.dnd_2024_rules` | D-583 eki |
| deptry | pypdf bildirilmemiş; pydantic/starlette geçişli | D-593 |
| pip-audit | certifi 2026.7.22 PYSEC-2026-4320 | D-587 |
| pnpm audit | toplam 23 (1 kritik, 8 yüksek, 10 orta, 4 düşük); üretimde 4 (1 kritik, 2 yüksek, 1 orta) | D-585, D-586 |
| desloppify mekanik | objective 74.9 (değişmedi); üretimde açık kümeler: özel içe aktarma 988, dict anahtarı 353, koku 265, büyük dosya 112, testsiz modül 101, assert 101 | D-598 |
| desloppify öznel (T6) | 72 açık bulgu, 20 boyut; genel 64.6 | D-599 |

### Ledger kaynaklı yeni satırlar

D-596 (world_threads kayıtta None → TypeError), D-597 (T4/T4b artıkları).

## Bulgu eşleme (G6)

| Kova | Sayı |
|---|---|
| Mevcut satıra ek | 2 (D-583, D-584) |
| Yeni satır | 17 (D-585 … D-601) |
| Yanlış alarm | vulture 60–79 adaylarının çoğu ve deptry DEP001 kardeş içe aktarmaları gürültü olarak satırlarında not edildi; ayrı satır açılmadı |

## Açık/kısmi satır durum tazeleme (G7)

290 açık/kısmi satır 10 Sonnet ajanıyla bugünkü koda göre denetlendi; her "kapandı" önerisi ikinci bir ajan tarafından reddedilmeye çalışıldı (para/kayıt/Geri Al satırı içeren parçalarda Opus).

| Karar | Sayı |
|---|---|
| Hâlâ açık | 205 (değiştirilmedi) |
| Kısmen kapalı (not eklendi) | 41 |
| Metni eski (doğru yer eklendi) | 18 |
| Kapanma önerildi | 26 |
| Doğrulayıcının onayladığı kapanma | 24 (D-065, D-155, D-175, D-227, D-228, D-232, D-339, D-345, D-378, D-387, D-426, D-470, D-474, D-497, D-499, D-510, D-519, D-521, D-522, D-527, D-533, D-541, D-542, D-543) |
| Reddedilen kapanma (açık kaldı) | 2 (D-218, D-236) |

D-470'in düzelten commit'i doğrulayıcının düzeltmesiyle 7bceb323/d7966c68 yazıldı. D-218 reddi önemli: kök `ai-dnd/test_*.py` altındaki 36 test modülü `scripts/full_python_suite.py` tarafından bulunmuyor; çoğu CI'da hiç koşmuyor.

Kapanma kuralı defterin kendi kuralıdır: düzelten commit sha'sı + doğrulayıcı onayı. Kısmen kapalı kararları doğrulayıcıdan geçmedi; yalnız not olarak yazıldı.

## Başlangıç ölçümü

`kalite-taramasi-20261125/baseline.json`: araç başına komut, kural×dosya sayıları, açık kimlikleri. Üretici: `make_baseline.py`. Yeniden üretmek için aynı klasördeki `pyrightconfig.json`, `importlinter.ini`, `engine_api_edges.py` kullanılır. Açık veritabanları zamanla değişir: ikinci plan "yeni bağımlılık" ile "yeni yayımlanmış açık"ı açık kimliğiyle ayırır.
