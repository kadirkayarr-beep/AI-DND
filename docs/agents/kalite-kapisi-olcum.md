# Kalite kapisi: olcum sonuclari (Task 4)

Olcum 2026-11-24, commit 7d9f6dff uzerinde, **yerelde** yapildi (CI'a push yok; isci push edemez). CI'daki ilk kosu ayrica denetlenmeli.
Yerel ortam: WSL Ubuntu 24.04, **Python 3.12.3** (CI 3.13 kullanir; 3.13 uyumu bu olcumde dogrulanmadi). Node tarafi: pnpm 12, Windows.
Kurulum: pip/pnpm yalniz `tools.json` pinleriyle; skylos `[llm]` olmadan ve her zaman `--no-upload`; fallow `DO_NOT_TRACK=1`; pnpm `--ignore-scripts` ve `npm_config_ignore_scripts=true`.

False-alarm sayimi: elle okuma degil, metin aramasidir (`game.X`, `"game.X"` ya da `"X"` baska dosyada geciyor mu). Kaba ve eksiktir; asagida her sayinin nasil bulundugu yazili.

| Arac | Bulgu | Sure | Karar |
|---|---|---|---|
| ruff (F,E9) | 1066 | 0,15 sn | gate (baseline), game.py F401 ayri ele alinacak (Task 5) |
| vulture (>=80) | 13 | 12,7 sn | gate (baseline) |
| skylos | 177 + 3 dongu | 4 dk 34 sn | report-only |
| gitleaks | 9 | 29 sn (2430 commit) | gate (baseline), Task 6 |
| knip | 370 | 5-8 sn | report-only, Task 7'de `components/ui/**` karari |
| fallow dead-code | 302 | 3,7 sn | report-only |

## ruff
- 1066 bulgu: F401 862, F811 78, F841 63, F821 49, F541 14. 688'i `ai-dnd/game.py` (hepsi F401), 196'si testlerde.
- `game.py` F401'lerinin 620'si baska dosyada `game.X` ya da `"X"` olarak geciyor (game.py bilerek yeniden disa aciyor; testler `game.X` yamaliyor). Yani `game.py` icin yanlis alarm orani en az %90, toplamda en az %58 (620/1066).
- Rastgele 20 bulgu (tohum 4): 20'sinde de ismin baska yerde gecisi bulundu; bunun bir kismi `game`, `Any`, `person` gibi yaygin isimler yuzunden sayimi sisirir, bu 20/20'ye guvenilmez.
- Karar: %50 kurali nedeniyle `game.py` F401 oldugu gibi gate olamaz; Task 5 ya per-file-ignore ya da baseline ile ele alir. F821 (tanimsiz isim, 49) gercek hata sinifidir, gate'e uygun.

## vulture (--min-confidence 80)
- 13 bulgu: 6 kullanilmayan degisken (testlerde, `acceptance_test.py`'de ve bir rapor betiginde), 6 import (5'i `game.py`, 1'i `character_creation.py`), 1 `barbarian.py` "unreachable code after try".
- `game.py`'deki 5 import'tan 4'unun adi `game_parts/` icinde tanimli (yeniden disa acma deseni): yaklasik %31 yanlis alarm (4/13). Metin aramasiyla bulundu, tek tek okumadim.
- Karar: sayi kucuk, baseline ile gate.

## skylos (--no-upload, --trace YOK)
- `--trace` testleri calistirir (hedef kodu yurutur, uzun); calistirmadim, is akisina da koymadim.
- 177 bulgu (36 fonksiyon, 100 import, 41 degisken) + 3 dairesel bagimlilik. Hepsi test disi kaynak; 77'si `game.py`.
- Ham JSON 169 MB, 2,8 GB RAM, 4 dk 34 sn. Is akisi yalniz bulgu listelerini (yaklasik 3 MB) artifact'a koyar.
- `game.py`'deki 77'den en az 9'u `game.X` ile baska yerde kullaniliyor (alt sinir). `game.py` disindan 12 bulgu elle okundu: 3 yanlis alarm (ziyaretci metodu `w_AnnAssign`, iki yeniden disa acilan import), 9 gercek kullanilmayan kod.
- Karar: report-only (sure, boyut, yanlis alarm).

## gitleaks (8.30.1, sha256 dogrulandi)
- 9 bulgu, hepsi `generic-api-key`, hepsi `ai-dnd/` altinda (agirlikla testler ve buyu kodu dosyalari). `--redact` calisti: raporda `Secret` alani `REDACTED`, ekran ciktisi 317 bayt, deger basilmadi. Degerleri ben okumadim; dosya adlari test sabiti gibi gorunuyor (dogrulanmadi).
- **Yanlis yesil riski:** git deposu okunamayinca (worktree yolu WSL'den acilamadi) gitleaks `0 commits scanned` ve `no leaks found` yazip cikis 0 verdi. Task 6 kapisi taranan commit sayisinin sifirdan buyuk oldugunu denetlemeli.
- Karar: baseline ile gate (Task 6).

## knip (6.48.0)
- 370 bulgu: 151 dosya, 114 devDependency, 82 export, 13 tip, 6 dependency, 2 unlisted, 2 katalog.
- `PORT`, `BASE_PATH`, `DATABASE_URL` olmayinca `vite.config.ts` ve `drizzle.config.ts` yuklenemiyor (ERROR); is akisi sahte degerler veriyor.
- Bulgularin cogu vendored shadcn/ui bilesenleri (`components/ui/*`: kullanilmayan bilesen ve alt export'lar). Gercek ama gurultu; `game.X` tipi yanlis alarm degil. Rastgele 20 export icin yaptigim ad aramasi guvenilir degil (ayni kit icindeki baska dosyalarda gecen adlar), orani olcemedim.
- Karar: report-only; Task 7 `components/ui/**` icin config karari verince gate.

## fallow (3.45.0, `dead-code` yalniz)
- Ilk pin 3.47.0 pnpm `minimumReleaseAge` kuralina takildi (1 gunluk surum, `ERR_PNPM_NO_MATURE_MATCHING_VERSION`). `tools.json` 3.45.0'a cekildi (resmi fallow-rs/fallow v3.45.0, 2026-11-20).
- 302 sorun: 162 kullanilmayan dosya, 97 export, 7 tip, 5 dependency, 16 devDependency, 10 override, 1 sinif uyesi, 1 prop, 1 unlisted, 2 cozulemeyen import. Cikis kodu 1 (bulgu var).
- Olcum kopyamda `content/` yoktu: 2 cozulemeyen import muhtemelen kopya artefakti.
- Duplication, similar-code ve coverage ozellikleri kullanilmadi.
- Karar: report-only (yeni arac, knip ile ortusuyor).

## Postinstall ve telemetri
- `pnpm install --ignore-scripts` ve `npm_config_ignore_scripts=true` ile hicbir betik calistirilmadi. Ag trafigini izlemedim: telemetri kapali oldugu yalniz `DO_NOT_TRACK=1` ayarina dayaniyor.
