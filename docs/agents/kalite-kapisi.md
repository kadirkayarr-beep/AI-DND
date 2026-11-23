# Kalite kapısı (CI)

Yeni ölü kod, kullanılmayan import, sızan anahtar ve ayar dışı büyüme bir PR'da kırmızı olur. Eski bulgular "baseline" dosyalarında kayıtlıdır; yalnız yeni bulgu kırar. Kapı CI'da çalışır (`.github/workflows/ai-dnd-quality.yml`), yerel hook yoktur. Araç sürümleri tek yerde: `ai-dnd/scripts/quality_gate/tools.json`.

## Hangi iş neyi korur

| İş | Ne yapar | Engeller mi |
|---|---|---|
| `python-gate` | ruff (F, E9) baseline'a karşı; vulture beyaz listeyle; üç "yalnız küçülür" kontrolü (ruff baseline, vulture listesi, `size_lock.json`) | Evet |
| `secrets-gate` | gitleaks tüm geçmişte, baseline dışı bulgu kırar, baseline yalnız küçülür; çıktıda sır değeri yok (`--redact`) | Evet |
| `ui-gate` | knip baseline'a karşı + baseline yalnız küçülür | Evet |
| `ui-gate` içinde fallow ve skylos | yalnız rapor (`continue-on-error`) | Hayır |

Boyut kilidi (satır sayısı) testle korunur (`size_lock.json` yalnız `part_max` (2500) üstündeki dosyaları ve uzun işlevleri bugünkü boyutlarıyla dondurur; öteki dosyaların girişi yoktur, `part_max` ile sınırlıdır): `test_quality_size_budget` ve `test_engine_size_budget`.

## Kırmızı işi okumak

1. Kırmızı adımın adına bak; `NEW:` ile başlayan satır yeni bulgudur (dosya, kural, ad; satır numarası yok).
2. `GREW:` satırı: bir baseline ya da kilit yukarı gitmiş; geri al.
3. `TOOL OUTPUT ERROR` ya da `crashed`: araç çökmüş ya da boş çıktı vermiş. "Sıfır bulgu" sayılmaz; aracı onar.
4. Bir dosya kilidi aştıysa dosyayı küçült ya da işi böl; bütçeyi yükseltme.

## Baseline nasıl düşürülür

Bir bulguyu gerçekten düzelttiysen: aracın raporunu al, `python -m scripts.quality_gate.ratchet update <ruff|knip|fallow> <rapor.json>` çalıştır (`ai-dnd/` içinde). `update` büyümeyi reddeder; yalnız küçültür. Vulture listesi için satırı silmek yeter. `size_lock.json` için: `part_max` üstündeki bir dosya `part_max`'a inince girişi silinir; `part_max` altı bütçesi olan bir girişi silmek büyüme sayılır (`GREW`), çünkü o dosyanın tek sınırı o girişti. Düşürmek onay istemez.

## Yükseltmek

Baseline ya da bütçe sayısını yükseltmek (yeni satır eklemek dahil) onay listesinde satır ve Kadir'in onayı ister. CI bunu `GREW` ile kırmızı yapar; onay verilirse yükseltme PR'ı Kadir'in tek seferlik yönetici birleştirmesiyle (admin merge) iner; PR gövdesine onay satırının kimliği (ör. `D-xxx`) yazılır. Zorunlu kontroller açıkken bunun başka yolu yoktur, bu yüzden yükseltme PR'ı yalnız baseline/kilit dosyasını değiştirir.

## Gerçek ölü kod

Kapı ölü kodu silmez. Gerçek ölü kod yalnız borç satırı (`docs/agents/debt-register.md`), test ve ayrı commit ile silinir. Bir bulgu yanlış alarmsa nedenini borç satırına yaz.

## Zorunlu kontrol (Kadir'in işi)

Üç işi (`python-gate`, `secrets-gate`, `ui-gate`) GitHub'da "required status check" yap (depo ayarı). Bu yapılana kadar kapı uyarır ama merge'i durduramaz.

Ölçüm sayıları: `docs/agents/kalite-kapisi-olcum.md`.
