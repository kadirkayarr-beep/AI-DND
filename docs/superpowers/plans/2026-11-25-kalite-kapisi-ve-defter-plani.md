# Kalite kapısı ve borç defteri güncelleme planı (2026-11-25)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Adımlar `- [ ]` ile izlenir.

**Amaç:** main `56111e4e` üzerinde kalite kapısının bütün araçlarını sırayla koşmak, Kadir'in onayladığı yeni araçları ekleyip koşmak, her bulguyu borç defterine bağlamak ve defterdeki her açık/kısmi satırın durumunu bugünkü koda göre tazelemek.

**Bu plan kod değiştirmez.** Çıktı tek bir belge PR'ıdır: `docs/agents/debt-register.md` + yeni tarama raporu `docs/agents/kalite-taramasi-20261125.md`. Bulguların çözümü ikinci planın (borç sıfırlama planı) işidir.

**Sıra (Kadir, 2026-11-25):** dalga 3 bitti (T6) → bu plan (kapı + defter) → ikinci plan (bütün borçları çözme) → yürütme. Sert şart: borç çözümleri yeni borç ya da yeni sorun açmayacak; bu planın ürettiği "başlangıç ölçümü" o şartın karşılaştırma tabanıdır.

## Genel kısıtlar

- Worktree: `C:\Users\Kadir\Desktop\AI-DND-k2-kapi`, dal `task/kalite-kapisi-20261125`, taban `origin/main` `56111e4e`. Ana klasörde çalışma yok.
- Araç kurulumu repo dışına: Python araçları `C:\Users\Kadir\Desktop\AI-DND-TOOLS\gate-venv-20261125` (Git Bash'te `Scripts/`), gitleaks ikilisi yeni boş klasör `AI-DND-TOOLS\gitleaks-8.30.1\`. Repo'ya kurulum dosyası eklenmez.
- Ruling: makinede Python 3.13 yok (3.14 ve 3.12 var); araçlar 3.14 ile koşar, CI 3.13'tür. Fark rapora yazılır. Yanlışsa maliyeti: sürüme bağlı birkaç ruff/pyright farkı; engelleyen kapılar için asıl kanıt CI sonucudur.
- Her Python aracı `PYTHONUTF8=1` ile koşar (Türkçe kaynak). Her aracın çıkış kodu ve çıktı JSON'unun ayrıştığı kaydedilir; ayrışmayan çıktı = araç hatası.
- Ham çıktılar repo dışında `AI-DND-TOOLS\gate-20261125\raw\`; bandit çıktısından `code` alanı silinir. Repo'ya yalnız özet sayılar girer.
- Sürümler sabit (`==`). Mevcut olanlar `ai-dnd/scripts/quality_gate/tools.json` ile aynı: ruff 0.17.5, vulture 2.14, skylos 5.8.0, knip 6.48.0, fallow 3.45.0, gitleaks 8.30.1 (sha256 `551f6fc8…70eb`). bandit 1.9.4 (kurulu). pyright: makinedeki global npm sürümü, sürümü rapora yazılır.
- Yeni araçlar (Kadir onayı 2026-11-25): import-linter, radon, deptry, pip-audit; pnpm audit pnpm'in kendisinde. Kurmadan önce PyPI sayfasından lisans ve kaynak repo okunur, rapora yazılır; yalnız açık kaynak lisanslı (MIT/BSD/Apache) olan kurulur. Sürüm: kurulum günü PyPI'deki son kararlı sürüm, `==` ile.
- Dışarı veri: yalnız pip-audit (paket adı+sürüm → OSV/PyPI) ve pnpm audit (lock özeti → npm registry). Başka hiçbir araç ağa bir şey göndermez: skylos `--no-upload`, fallow `DO_NOT_TRACK=1`, telemetri açan bayrak yok.
- Anahtar dosyaları (.env, apikeys*, *.pem, ~/.aidnd-*-key) okunmaz, taranan çıktıda değer görünmez: gitleaks yalnız `--redact` ile; rapora sır değeri değil kural+dosya yazılır.
- pnpm kilit dosyasını adlandıran git komutu çalıştırılmaz.
- Testler yalnız `slot.sh` ile, slot 9 (yedek slot 2). 3/4/5 yok. Yerel tam paket yok: tam paket kanıtı main CI'daki "AI-DND bounded verification" koşusudur. Tarayıcı testi koşulmaz.
- Hiçbir dosya silinmez; ajanlar rm/Remove-Item/git clean/reset --hard/worktree remove çalıştırmaz.
- Ajanlar Monitor kullanmaz; ön plan beklemesi en çok 9 dakika.
- Defteri yalnız denetleyici (ben) yazar; ajanlar JSON döndürür.

## İnceleme odağı (bu planın en kolay yanlış gideceği beş yer)

1. **Sahte "kapandı":** durum tazelemede bir satırı kanıtsız kapatmak. Kural: "kapandı" yalnız dosya/işlev adı + commit ya da test adı kanıtıyla; kanıt yoksa satır açık kalır.
2. **Çöken aracı "sıfır bulgu" saymak.** Her aracın çıkış kodu ve çıktı boyutu rapora yazılır; boş/bozuk JSON = araç hatası, bulgu sayısı değil.
3. **Gürültü patlaması:** pyright ~1300 hata, radon yüzlerce işlev. Bunlar satır satır deftere girmez; kural+modül kümesi başına tek satır, sayı ve rapor yolu ile (G6 gruplama kuralı).
4. **Mükerrer satır:** yeni bulgu zaten açık bir satırın konusuysa yeni satır açılmaz; mevcut satıra "2026-11-25 taraması: N yer" eki yazılır.
5. **Sır sızıntısı:** gitleaks/bandit çıktısı rapora kopyalanırken değer taşıması. Rapora yalnız kural kimliği, dosya, sayı.

---

### G0: Araçları kur ve sürümleri doğrula

- [x] Sanal ortam (Python 3.14.2) kuruldu: ruff 0.17.5, vulture 2.14, skylos 5.8.0, bandit 1.9.4, import-linter 2.17, radon 6.0.1, deptry 0.25.1, pip-audit 2.10.1. pyright 1.1.414 (global npm). node 26.13.1, pnpm 12.15.0 (CI: node 24, pnpm 10.26.1; fark rapora).
- [x] Lisanslar: ruff MIT, vulture MIT, skylos Apache-2.0, bandit Apache-2.0, import-linter BSD-2, radon MIT, deptry MIT, pip-audit Apache-2.0. Rapora tablo.
- [ ] gitleaks 8.30.1 Windows ikilisi GitHub release'den yeni boş klasöre indirilir ve açılır; sha256 release'in `checksums.txt`'si ile doğrulanır (tools.json'daki sha Linux ikilisi içindir). Uyuşmazsa kullanılmaz.
- [ ] Doğrulama: her aracın `--version` çıktısı pinle aynı; tablo rapora.

### G1: Engelleyen kapılar (CI ile aynı komutlar, yerelde)

Beklenen: hepsi 0 yeni bulgu (main CI quality gate 56111e4e için yeşil). Fark = bulgu.

- [ ] `cd ai-dnd && ruff check . --select F,E9 --output-format json` (rc>1 = çökme) → `ratchet check ruff`.
- [ ] `ratchet check-shrink` ruff/knip baseline, `check-names-shrink` vulture listesi, `check-fingerprints-shrink scripts/quality_gate/gitleaks-baseline.json`, size_lock_shrink; hepsi `origin/main`'e karşı, CI'daki komutlarla aynı.
- [ ] vulture `ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 80`.
- [ ] Boyut testleri slot 9: `test_quality_size_budget`, `test_engine_size_budget` + komşu set (`test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`).
- [ ] gitleaks tüm geçmiş `--redact`, baseline'a karşı, `--report-path` repo dışına; günlükte `[1-9][0-9]* commits scanned` satırı yoksa araç hatası.
- [ ] knip: önce `pnpm install --frozen-lockfile --ignore-scripts`; env `PORT=3000 BASE_PATH=/ DATABASE_URL=postgres://localhost/unused`; `npm_config_ignore_scripts=true pnpm dlx knip@6.48.0 --reporter json` → `ratchet check knip`. Ruling: yerel pnpm 12 kilit dosyasını reddederse knip/fallow için main CI 56111e4e quality gate sonucu kanıt sayılır ve rapora öyle yazılır.

### G2: Rapor araçları

- [ ] fallow dead-code (DO_NOT_TRACK=1) → `ratchet check fallow`; yeni ve baseline sayısı.
- [ ] skylos `ai-dnd --no-upload --json` → tür başına sayı.
- [ ] `pnpm run typecheck` → hata sayısı (beklenen 0).
- [ ] Ek tarama (borç madeni, kapı değil): `cd ai-dnd && ruff check . --select B,BLE,SIM --statistics` ve vulture `--min-confidence 60` (yalnız 60–79 arası yeni adlar). Karmaşıklık yalnız radon'da.

### G3: Yeni araçlar

- [ ] bandit `-r ai-dnd -f json` (testler ayrı sayılır); orta/yüksek önem × güven tablosu; `errors` listesi boş değilse araç hatası.
- [ ] pyright: PR'a girecek `docs/agents/kalite-taramasi-20261125/pyrightconfig.json` (`include:["ai-dnd"]`, `extraPaths:["ai-dnd"]`, `pythonVersion:"3.13"`, `typeCheckingMode:"standard"`); `pyright -p <o dosya> --outputjson`; kural × modül sayıları. T4b'deki 1287 farklı komutla ölçüldü, karşılaştırılmaz.
- [ ] radon `cc -s -n C -j` (C ve üstü işlev listesi) ve `mi -n B` yalnız sayı.
- [ ] import-linter: PR'a girecek `docs/agents/kalite-taramasi-20261125/importlinter.ini`; `PYTHONPATH=ai-dnd lint-imports --config <o dosya>`; root paketler `api`, `game_parts` + motor modülleri. Sözleşmeler: (a) motor modülleri ve `game_parts` `api`'yi içe aktarmaz; (b) `api.routes_*` birbirini içe aktarmaz. Kırılan her kenar sayılır; (a) D-583 ile eşlenir.
- [ ] deptry `ai-dnd --config pyproject.toml --known-first-party api,game_parts,<motor modülleri>`; kalan DEP001/DEP004 gürültüsü tek "bilinen gürültü" satırı.
- [ ] pip-audit: `uv.lock`'tan sabit sürüm listesi çıkarılır (betik okur, kurmaz) + `ai-dnd/scripts/engine_split/requirements-dev.txt`; `pip-audit -r <dosya> --no-deps --disable-pip --format json`. Hiçbir paket indirilmez/kurulmaz. Açık kimlikleri (GHSA/PYSEC) kaydedilir: plan 2 "yeni bağımlılık" ile "yeni yayımlanmış açık"ı ayırır.
- [ ] `pnpm audit --json` ve `pnpm audit --prod --json`; sıfır olmayan çıkış = açık var (çökme değil), JSON ayrışmalı; önem başına sayı + açık kimlikleri.

### G4: desloppify mekanik tarama

- [ ] AI-DND-desloppify worktree'si zaten `56111e4e`'de (T6 dalı); orada `desloppify --lang python scan --path ./ai-dnd --force-rescan --attest "…"` (PYTHONUTF8=1); objective ve boyut başına puan. Başka worktree'ye dokunulmaz. Öznel 20 parça inceleme T6'da yapıldı, tekrarlanmaz; T6 sorun listesi (`desloppify status` açık sorunlar, ~70) de bulgu kaynağıdır.

### G5: Tam paket kanıtı

- [ ] main `56111e4e` için "AI-DND bounded verification" sonucu (gh run). Kırmızıysa önce kanıt indirilir, köken izlenir, durulur.

### G6: Bulgu eşleme (triage)

Girdi: G1–G4 raporları. Kural:
- Her bulgu kümesi (araç + kural + modül) üç kovadan birine: **(a) mevcut satır** (satır kimliği + ek not), **(b) yeni satır**, **(c) yanlış alarm** (neden, rapora).
- Öncelik: bandit yüksek/orta, pip-audit/pnpm audit yüksek/kritik açık, gitleaks yeni bulgu → [YÜKSEK]; davranış hatası olabilecek (pyright `reportOptionalMemberAccess`, `reportAttributeAccessIssue` gerçek yolda, ruff B/BLE) → [ORTA]; stil/karmaşıklık/ölü kod → [DÜŞÜK].
- Gürültü kuralı: aynı kural+modül kümesi tek satır; satırda sayı, örnek 3 yer, rapor yolu.
- Mükerrer arama dosya+işlev adıyla yapılır (yalnız kurala göre değil).
- Her yeni satırda defterin istediği sahip ve tetik alanları dolu ("sahip: Kod-2, tetik: borç sıfırlama planı").
- Ledger kaynaklı satırlar burada eklenir: typeddict2 ledger'ındaki "saved None TypeError" satırı, `_make_room` Mapping notu, D-584'e narration B yeri eki.
- Doğrulama: rapordaki her küme bir kovaya düşmüş; sayım tablosu (kova başına) rapora.

### G7: Açık/kısmi satır durum tazeleme

- [ ] Açık + kısmi satırlar (≈287) 30'luk parçalara bölünür; parça başına bir Sonnet ajanı (≈10 ajan, Workflow ile paralel, yalnız okur).
- Ajan girdisi: satır metinleri + main `56111e4e` worktree'si (salt okunur). graphify kuralı brife konur.
- Ajan çıktısı JSON: `{id, verdict: open|closed|partial|stale_text, evidence: "<dosya:işlev> | <commit> | <test>", note}`.
- Kapatma kuralı defterin kendi kuralıdır: "closed" = düzelten commit sha'sı + doğrulayıcının onayı (ya da Kadir'in "wontfix"i). Sha'sız öneri "open" kalır.
- Her "closed" önerisi bir bağımsız doğrulayıcı ajanca reddedilmeye çalışılır (Sonnet; para/kayıt/Geri Al satırlarında Opus). Doğrulayıcı katılmazsa satır açık kalır. Doğrulayıcı sayısı = kapanma önerisi / 30, yukarı yuvarlanır.
- Doğrulama: her satır bir karar almış; kapanan her satırda kanıt var.

### G8: Belge PR'ı

- [ ] `docs/agents/kalite-taramasi-20261125/baseline.json`: araç başına sürüm, tam komut, cwd, çıkış kodu, kural×dosya sayıları, açık kimlikleri. Plan 2 sonunda aynı komutlarla tekrar koşulup bununla karşılaştırılır. Aynı klasörde pyrightconfig.json ve importlinter.ini.
- [ ] `docs/agents/kalite-taramasi-20261125.md`: araç/sürüm/lisans tablosu, her aracın komutu, çıkış kodu, bulgu sayısı, G6 kova tablosu, G7 karar tablosu, "başlangıç ölçümü" bölümü (ikinci planın sonunda tekrar koşulacak sayılar).
- [ ] `docs/agents/debt-register.md`: yeni satırlar (D-585…), ekler, durum değişiklikleri; satır silinmez (kapanan satır "kapandı: <kanıt>" olur).
- [ ] Bağımsız inceleme: Opus, rapor + defter diff'i; özellikle kapanan satırların kanıtı ve öncelikler.
- [ ] PR, CI yeşil, merge (belge PR'ı; oynayış kapısı oyun kodu içindir). Merge sonrası main CI kontrolü.
- [ ] Sabah özeti (≤5 satır) ve bellek güncellemesi.

## Tahmini bütçe

Sonnet: ≈10 tazeleme + ≈4 doğrulama ajanı. Opus: plan incelemesi 1, PR incelemesi 1. Araç koşuları denetleyicide (ajan yok). pyright/radon tam ağaç koşusu birkaç dakika.

## Durma koşulları

Yalnız CLAUDE.md'deki dört durum. Özellikle: gitleaks yeni gerçek sır bulursa değer yazdırılmadan durulur ve Kadir'e bildirilir (anahtar döndürme sahibin işi).
