---
status: accepted
date: 2026-11-22
---

# `game.py` bölündü: `game_parts/` ve merkez kuralı

Motor tek dosyaydı (`ai-dnd/game.py`, 25 050 satır, 521 üst düzey işlev; spec §1); `game.py` bölmesi (spec `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md`, Kadir 2026-11-17; Planlar 1-6) onu `ai-dnd/game_parts/` parçalarına taşıdı, testlerin `game` üzerindeki hiçbir yaması değişmeden. Terimler: `GLOSSARY.md`.

## Bağlam

- 430 `import game` yeri, 245 `game.X` adı ve yaklaşık 1 045 test yaması `game` modülüne bağlıydı; yamaları yeni modüllere toplu çevirmek anti-hedefti (spec §2).
- Bu yüzden dışarıya açık tek ad `game` kaldı ve taşınan kod `game` üzerinden çağrılır; böylece eski yamalar taşınan koda da ulaşır.
- `game.py` bölmeden sonra 1 397 satırdır (Plan 6 Görev 1-2: taşımadan kalan fazla boş satırlar silindi, bir yorum bloğu yerine gitti); spec hedefi 1 500'ün altı.

## Karar

- **Merkez kuralı:** bir parça motor adlarını yalnız işlev gövdesinde `game.X` diye çağırır; kardeş parçayı içe almaz, `from game import ...` yazmaz; yama yüzeyindeki bir adı çıplak kullanmaz. `game.py` her taşınan adı açık bir yeniden dışa vurum satırıyla (`from game_parts.<parça> import ...`) geri verir; `game.py` dışında kimse `game_parts.*` içe almaz. İşlev dışa vuran her parça `_PART_MODULES`'te yazılıdır, böylece `session=` sarmalayıcısı onu da sarar.
- **Hiç taşınmayan adlar (spec §5):** içe almalar ve yeniden dışa vurum satırları, `world_state`/`messages` tohumları, `RULE_ORDER`, `GameSession` (Geri Al anlık görüntüsü), `_session`, `_bind_session_engine` ve oturum sarmalayıcısı, `create_session`, modül sınıfı değişimi (`_GameModule`), import anındaki `initialize_game` çağrısı, `_speech_debug_trail`, `DEFAULT_SAVE_PATH`, `start_terminal_game`; ayrıca `_restore_in_place` ve `_dynamic_engine_transitions` (D-471: Geri Al anlık görüntüsü dokunulmadan kalır).
- **Bekletilen tek ad: `_narrate_resolved_turn`** (351 satır). Hiç taşınmayan adlardan değildir: Plan 5'te N3 kural 4 onu durdurdu (`ResolvedTurn` adı bir tür açıklamasında; parçalarda `from __future__ import annotations` yok) ve Plan 6'nın Ruling N'i onu `game.py`'de bıraktı. Tur bölme diliminde taşınır (aşağıda "Boyut anahtarı").
- **Boyut bütçesi ve mandal (karar 10):** `size_budget.json` her dosyaya satır sınırı koyar (`part_max` 2 500; `turn.py` ve `narration_safety.py` geldikleri boyutta dondurulur, yalnız küçülebilir; 151 satır ve üstü işlevler bugünkü uzunluklarıyla dondurulur, yeni giriş ve büyüme yok). Bir bütçe gerçek boyutun 50 satırdan fazla üstündeyse test kırmızıdır; düşürme onay istemez; herhangi bir sayıyı yükseltmek onay listesi satırı ve Kadir'in onayı ister. `test_game_py_is_within_the_spec_cap` `game.py`'nin bütçesini ve gerçek boyutunu 1 500'ün altında tutar.
- **CI'da kalan kalıcı ağ:** N1 (`test_engine_surface`), N2 (`test_engine_patch_census`), N3 (`test_engine_routing`), N6 (`test_engine_sources`), boyut testi (`test_engine_size_budget`) ve düzen testi (`test_engine_layout`: motor dosyalarında üst düzeyde en çok iki boş satır üst üste).
- **Emekli olanlar (spec §11):** N4 (`ledger_diff.py`), N5 (`move_check.py`, `move_block.py`), N7 (`coverage_by_function.py`) ve N8 (`sensitivity.py`) zorunlu kapı adımı olarak emeklidir. Betikleri ve testleri depoda ve CI'da değişmeden kalır. Emekli şu demektir: bundan sonra hiçbir görev N4, N5, N7 araçlarını koşmak zorunda değildir; ileride bir bölme dilimi onları yine koşabilir.
- **Kalan canlı görevler:**
  - N8: `test_engine_sensitivity.test_every_flagged_function_in_every_engine_file_is_in_the_lock_or_removed` canlı motoru CI'da tarar ve `sensitivity.py --write` `game_parts/` varken reddeder. Yani para ya da kayıt içeren yeni bir işlev, elle yazılmış bir `sensitive.json` satırı gelene kadar CI'ı kırmızıya çevirir; o satır güçlü incelemeyle ve onay listesi satırıyla yazılır.
  - N2 (`patch_census`) kalıcı ve canlıdır: yeni bir yama hedefi kilidini aynı yolla değiştirir (CI kırmızı, kilit `patch_census.py --write` ile yeniden üretilir, incelemeyle ve onay listesi satırıyla).

## Sonuçlar

- Testler ve yamalar `game` üzerinden değişmeden çalışır; bedeli her `game.X` erişiminin `_GameModule` üzerinden geçmesidir (hız kilometre taşlarında TM0 tabanına karşı ölçülür, sınır 1.10).
- `game.py`'ye yeni işlev eklenmez; yeni kod ilgili `game_parts` modülüne ya da kendi modülüne girer (CLAUDE.md, karar 8; `implementer-preamble.md` maddesi (i)).
- Dev işlevleri parçalamak bu kararın dışındadır; sonraki dilimdir (tur bölme dilimi, spec §12).

## Sonraki dilimler için kurallar

Kadir'in 2026-11-22 kararlarıyla eklendi.

- **Boyut anahtarı (Q4):** taşınan bir işlev yeni yerinde, yeni anahtarı altında (`long_functions`'ta `<dosya>::<ad>` ve dosyanın `files` girdisi) eşit ya da daha düşük bir bütçe sayısı taşır. Eşit ya da daha düşük sayılı bir anahtar yükseltme sayılmaz; daha yüksek bir sayı hiç yazılmaz. `_narrate_resolved_turn` için özel olarak: tur bölme diliminde, 351 ya da daha az sayıyla, yeni bir parçaya taşınır (`turn.py` dondurulmuş; `turn_front.py` 2 500'ü geçer). Ancak tür açıklaması düzeltmesi (P5T4-1) ve kayıt yazıcısı sabitlemesi (P5T5-8) iki bayrakta da yeşil olduktan sonra, bir parti dosyası kararıyla, güçlü Opus incelemesiyle taşınır; onay satırı "gevşetme olabilir" diye işaretlenir.
- **Önce taşı, sonra düzelt (Q1, karar j):** dondurulmuş uzun bir işlevi uzatacak bir düzeltme, önce bloğu değiştirmeden yeni bir modüle taşır (kilit düşer), sonra ikinci bir commit'te düzeltir. Kimlik kesiminin içinde davranış değişikliği olmaz; bütçe yükseltilmez. Mümkünse düzeltme dondurulmamış çağrılan işlevde yapılır.
- **`game.py` payı (Q3):** bütçe `min(gerçek boyut + 50, 1499)`'dur. Bu payın her kullanımı bir `Ruling` ve bir onay listesi satırıdır.
- **Parti dosyaları (rapor I6):** `scripts/engine_split/batches/*.txt` içinde adı geçen bir adı sonradan taşıyan, yeniden adlandıran ya da silen iş, aynı commit'te o parti dosyasını da düzenler ve "gevşetme olabilir" işaretli bir onay satırı yazar; böylece `test_engine_surface`'ın `*_batches_are_movable` sabitlemeleri doğru kalır.
- **Tarif (rapor I10):** yeni ya da değişen herkese açık bir ad `surface.json`'u yeniden üretir (N1 fark kuralı); yeni bir parça `_PART_MODULES`'e yazılır ve `game.py`'de içe alınır; para ya da kayıt içeriği kazanan eski bir işlev elle yazılmış bir `sensitive.json` satırı alır; `implementer-preamble.md` maddesi (i)'deki koruma testi listesi her motor göreviyle koşar.
