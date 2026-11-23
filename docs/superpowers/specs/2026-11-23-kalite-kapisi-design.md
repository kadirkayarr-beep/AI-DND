# Kalite kapısı (quality gate) — kısa tasarım

Kadir'in isteği (2026-11-23): "yazılan kodun kalitesinden emin olmamız lazım"; "aşırı temkinli olup eleme yapma, işe yarayacaksa kullanalım".

## Amaç

- Yeni ölü kod, kullanılmayan import/değişken, sızan anahtar ve dev dosya/işlev `main`'e sessizce giremesin.
- Bugünkü çöp tek seferlik bir taramayla bulunur ve borç defterine girer (yol haritası satır 4c).

## Yaklaşım (seçilen)

- **Asıl kapı CI'dır.** Yerel pre-commit/lefthook hook'ları atlanabilir (`--no-verify`) ve bu makinede hook'lar zaman aşımı ve RAM sorunu çıkardı (2026-11-17). Yerelde en fazla hızlı, isteğe bağlı bir pre-push (ruff) olur.
- **Mandal (baseline) yöntemi:** bugünkü bulgular taban dosyasına yazılır; CI yalnız YENİ bulguyu kırmızı yapar. `size_budget.json` ile aynı ilke: sayı yalnız düşer.
- Testler hook'a konmaz (tam paket ~30 dk); CI'da zaten koşuyor.

## Araçlar (2026-11-23 araştırması; kurulmadı, depoları okundu)

| Araç | Ne için | Karar | Ayar |
|---|---|---|---|
| ruff (astral-sh/ruff, MIT) | Python import/değişken, lint | kullan | sürüm sabit; pip/uv ile kur; mevcut hatalar `per-file-ignores` / `--add-noqa` ile tabana |
| vulture (jendrikseipp/vulture, MIT) | Python ölü kod (kapı) | kullan | `--make-whitelist` ile taban; `game.X` ve `sys.modules` yamaları beyaz listede; `--min-confidence 80` |
| skylos (duriantaco/skylos, Apache-2.0) | Python ölü kod (ikinci görüş; `--trace` dinamik çağrıları görür) | ayarla kullan | sürüm sabit; `[llm]` eki yok; her zaman `--no-upload`; `cloud`/`--upload` asla; Chainguard çatalı değil |
| knip (webpro-nl/knip, ISC) | TS/React kullanılmayan dosya/export/bağımlılık (kapı) | kullan | sürüm sabit; taban: ignore ayarı + CI farkı |
| fallow (fallow-rs/fallow, MIT) | TS/React ölü kod (ek; gerçek baseline'ı var) | ayarla kullan | sürüm sabit; `DO_NOT_TRACK=1`; benzer kod ve kapsam özellikleri kapalı; benzer adlı `jsgoldman/fallow` resmi değil |
| gitleaks (gitleaks/gitleaks, MIT) | Sızan anahtar | kullan | sürüm ve checksum sabit; `--baseline-path`; yalnız güvenlik yaması alıyor (yazar Betterleaks'e geçiyor), ileride değerlendirilir |

Doğrulanmadı: knip ve fallow'un postinstall davranışı, vulture ve skylos'un Python 3.13 desteği, gitleaks'in telemetrisi. Ayrıca bu repoda iki Python aracının dinamik kodu nasıl ele aldığı denenmedi; ilk iş bir dalda deneme koşusudur.

## Kapsam

- Python: `ai-dnd/` (motor, `api/`, betikler). TS/React: `ai-dnd/artifacts/` altındaki arayüz.
- Boyut sınırı (`size_budget.json`: dosya ≤ 2 500, işlev < 151 dondurma) motorun dışındaki Python ve arayüz koduna da yayılır; bugünkü büyükler bugünkü boyutlarıyla dondurulur.

## Sıra

1. Tur bölme biter, Kadir oynar.
2. Satır 4b: CI işi, deneme dalında araçların bu repodaki gürültüsü ölçülür, beyaz listeler ve tabanlar yazılır, CI'a eklenir. Yalnız CI/test: oynayış beklemez (S9).
3. Satır 4c: bir kerelik salt-okunur tarama (ucuz modeller alan alan, Opus doğrular), bulgular borç defterine; silme yok. Temizlik küçük PR'larla, kırmızı testle; para/kayıt/Geri Al temizliği Opus incelemesiyle.

## Riskler

- Dinamik çağrılar (`game.X`, `sys.modules`) yüzünden çok yanlış alarm: beyaz liste ve `--min-confidence` ile; skylos `--trace` ikinci görüş.
- Bu tür araçlar "ölü" dediği şeyi silmeye iter: ölü kod silme yalnız borç satırıyla, testle ve git commit'iyle yapılır (dosya silme kuralı geçerli).
