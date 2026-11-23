# Unwritten

Karanlık fantezi metin RPG'si (motor `ai-dnd/game.py` ve `ai-dnd/game_parts/`). Bu sözlük şimdilik `game.py` bölmesinin terimlerini tutar; kararın kendisi `docs/adr/0001-game-parts-merkez-kurali.md`'dedir.

## Language

### Motor yapısı

**game_parts**:
`game.py`'den taşınan motor kodunun konu modülleri (her biri bir "parça"); dışarıya açık tek ad `game` kalır ve `game.py` dışında kimse `game_parts.*` içe almaz.
_Avoid_: alt motor, motor paketi

**Merkez kuralı (`game.X`)**:
Bir parça motor adlarını çıplak değil, yalnız işlev gövdesinde `game.X` diye çağırır; böylece `game` üzerine yapılan her yama taşınan koda da ulaşır.
_Avoid_: yönlendirme kuralı, çıplak çağrı yasağı

**Yeniden dışa vurum**:
`game.py`'deki açık `from game_parts.<parça> import a, b` satırı; taşınan her ad `game.<ad>` olarak erişilebilir kalır (yıldızlı içe alma yok) ve bu satırlar herkese açık yüzeydir, silinmez.
_Avoid_: re-export listesi, takma ad

**Yama yüzeyi**:
`game` üzerinde yamalanan ya da yeniden bağlanan her ad: işlevler, `CLASSES`/`RACES`/`RULE_ORDER`/`system_prompt` gibi veriler ve `ollama`, `open`, `uuid4` gibi içe alınmış adlar.
_Avoid_: yama listesi

### Kilitler

**Boyut bütçesi**:
`api/tests/engine_split_locks/size_budget.json` ve `test_engine_size_budget`: dosya başına satır sınırı (`files`), her parça için en çok `part_max` 2 500 satır ve 151 satır ile üstü işlevlerin dondurulmuş uzunlukları (`long_functions`); bir sayıyı yükseltmek yalnız Kadir'in onayıyla olur (karar 10), düşürmek onay istemez.
_Avoid_: satır limiti, kota

**Mandal**:
Bir bütçe gerçek boyutun `slack` 50 satırından fazla üstündeyse test kırmızı olur, yani bütçe boşluk biriktiremez; `game.py` bütçesi `min(gerçek boyut + 50, 1499)`'dur ve bu payın her kullanımı bir `Ruling` ve onay listesi satırı ister.

**Dondurulmuş dosya**:
Bütçesi geldiği boyutta kilitlenen ve yalnız küçülebilen parça: `turn.py` (3 667) ve `narration_safety.py` (1 505).

**Hassas liste**:
`api/tests/engine_split_locks/sensitive.json`: para, kayıt, Geri Al anlık görüntüsü ya da dosya yazma içeren işlevler; listedeki bir işlev yalnız güçlü incelemeyle taşınır, satırı elle yazılır (`sensitivity.py --write` `game_parts/` varken reddeder).
_Avoid_: kırmızı liste

### Kanıt ağı (N1-N8)

**N1 (altın yüzey)**:
`surface.json` ve `test_engine_surface`: `game` modülündeki her adın türü, imzası ve `__module__` değeri; kalıcı, CI'da; yeni ya da değişen herkese açık ad `surface.json`'u yeniden üretir (fark kuralı).

**N2 (yama sayımı)**:
`patch_census.py`, `patch_census.json` ve `test_engine_patch_census`: motor dışındaki her `.py` dosyasında `game` üzerine yapılan yamalar; kalıcı ve canlı: yeni bir yama hedefi CI'ı kırmızıya çevirir, kilit `patch_census.py --write` ile yeniden üretilir, incelemeyle ve onay listesi satırıyla.

**N3 (yönlendirme denetimi)**:
`routing_audit.py` ve `test_engine_routing`: parçalarda çıplak yüzey adı, kardeş parça içe alması, modül düzeyinde `game.` ve kimlik adı olmadığının statik kanıtı; kalıcı, CI'da.

**N4 (yama isabet defteri)**:
`ledger_diff.py`: her (test, yama hedefi) için sahte nesnenin taşımadan önce ve sonra çağrılıp çağrılmadığı; zorunlu kapı adımı olarak emekli (spec §11), betik ve testleri depoda ve CI'da kalır.

**N5 (taşıma eşdeğerliği)**:
`move_check.py` ve `move_block.py`: taşınan bloğun AST'si, belirteç akışı ve yorum sayısı eskisiyle aynı; zorunlu kapı adımı olarak emekli, betikler ve testleri depoda ve CI'da kalır.

**N6 (kaynak okuyan testler)**:
`engine_source_files()` (`game.py` + bütün parçalar) ve `test_engine_sources`: metin ya da AST tarayan testler bu tek yardımcıyı kullanır; CI'da kalır.

**N7 (kapsam eşitliği)**:
`coverage_by_function.py`: işlev başına koşan satır sayısı bölmeden önce ve sonra aynı; zorunlu kapı adımı olarak emekli, betik ve testleri depoda ve CI'da kalır.

**N8 (hassasiyet taraması)**:
`sensitivity.py` ve `test_engine_sensitivity`: zorunlu kapı adımı olarak emekli ama görevi canlı: `test_every_flagged_function_in_every_engine_file_is_in_the_lock_or_removed` motoru CI'da tarar, yani para ya da kayıt içeren yeni bir işlev elle yazılmış `sensitive.json` satırı gelene kadar CI'ı kırmızıya çevirir (güçlü inceleme ve onay listesi satırıyla).
