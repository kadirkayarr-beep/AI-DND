# game.py'yi güvenle bölme — tasarım

Tarih: 2026-11-17 (revizyon 2, aynı gün). Taban: `origin/main` 088011b3, `ai-dnd/game.py` 25 050 satır.
Durum: tasarım ONAYLANDI (Kadir, 2026-11-17: "Hepsini onaylıyorum" — 14. bölümdeki 11 kararın hepsi öneri yönünde). Kod değişmedi, test koşulmadı.
İşaretler: **[D]** = kodda satırına bakılarak ya da betikle doğrulandı. **[Y]** = doğrulanmadı.

**Revizyon 2 özeti.** Bağımsız eleştirinin 11 bulgusu kodda tek tek sınandı; **11'i de doğru çıktı ve uygulandı**. Üç sayı benim ölçümümle biraz farklı (regex farkı): işlev içi içe alma 338 / 127 işlev (eleştiri: 347 / 128); para sözcüğü içeren 34 işlevin 26'sının adında para yok (eleştiri: 25); `legacy_debug` altında `game.py`'yi `exec` eden 25 betik (eleştiri: ~20). Kesin sayıları T0 betikleri üretir. Aşama adları değişti: eski taslaktaki A0-A7 → **T0-T7**, M0-M5 → **TM0-TM5** (yeniden tasarım planının A1/A2.2 adlarıyla karışmasın diye).

## 1. Amaç ve neden

Kadir'in isteği: BM'den sonra kodun genel yapısına dair kaygıyı gidermek; hataya, ölü koda ve spagettiye yol açan yapıyı düzeltmek; daha planlı ve güvenli ilerlemek.

Bugünkü durum: oyun motorunun büyük kısmı tek dosyada. `game.py` 25 050 satır, 521 üst düzey işlev **[D]**; tek bir işlev (`_run_player_turn_internal`) 2 743 satır. Bu dosyaya dokunan her iş birbirine çarpıyor, inceleme pahalı, hata bulmak zor.

Bu plan dosyayı konu başlıklarına göre ayrı dosyalara **taşır**. Oyunun davranışı değişmez. Asıl tehlike taşımanın kendisi değil, testlerin sessizce boşa düşmesidir: test yeşil kalır ama artık hiçbir şeyi sınamaz. Planın büyük kısmı bunu makineyle kanıtlamaya ayrılmıştır.

## 2. Hedefler, hedef olmayanlar, anti-hedefler

**Hedefler**
- `game.py` 1 500 satırın altına iner; kalan kod konu modüllerine dağılır.
- 430 `import game` yeri, 245 `game.X` adı ve ~1 045 test yaması **hiç değişmeden** çalışır.
- Her taşımanın "mantık değişmedi", "yorum kaybolmadı" ve "hiçbir yama boşa düşmedi" kanıtı makine çıktısı olarak deftere girer.
- Dosyanın yeniden şişmesini engelleyen kalıcı testler kalır.

**Hedef olmayanlar (bu planda yok)**
- Dev işlevleri parçalamak (`_run_player_turn_internal`, `_narration_safety_decision`). Bu mantık değişikliğidir; **bir sonraki dilimdir** (bkz. 12).
- Ölü kod silmek. Yalnız kanıt raporu hazırlanır; silme Kadir'in kararıdır.
- Yeniden adlandırma, biçim düzeltme, "geçerken şunu da" işleri.
- Eski kayıt uyumu (sahibin kuralı: eski kayıtlar önemli değil).

**Anti-hedefler (yapılırsa plan başarısız sayılır)**
- Test yeşil ama boş: taşınan kod bir yamadan kaçar.
- Test yamalarını yeni modüllere toplu çevirmek (~1 045 satır test yeniden yazımı).
- Taşıma görevine mantık değişikliği karıştırmak.
- Taşıma sırasında tek bir yorum satırının kaybolması ya da kısalması.
- Para, kayıt ya da Geri Al'a dokunan kodun "normal" incelemeyle taşınması.
- İşaretsiz test gevşetme, atlama, silme.

## 3. Kısıtlar (repo kuralları)

- Kendi worktree'si, tek yazıcı; push/merge yalnız Kadir'in taze onayıyla; force push ve dal silme yok.
- Testler yalnız `slot.sh` / `par` ile; aynı anda iki tam paket koşmaz (16 GB bellek).
- Her görevde: hedefli testler + sabit komşu seti (`test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`). Tam paket yalnız kilometre taşlarında.
- Önce kırmızı test, sonra düzeltme. Eski davranışı sabitleyen test ancak eşit sıkılıkla yeniden yazılır ve `docs/agents/onay-listesi-20261115.md` dosyasına girer.
- Yeni kampanya ya da oturum kuran **her yeni test** tohumu sabitler (`api/tests/town_seed.py` → `fixed_town`; yolculukta `campaign_seed`).
- Para, kayıt, Geri Al: bağımsız inceleme, en güçlü model (Opus; "fable yok" kuralı). Dilim sonu bütün dal incelemesi. Kadir 10 dakika oynamadan dilim bitmez.
- Doğrulanmamış skill, hook, npx kurulmaz. Anahtar dosyaları okunmaz.
- Hız kuralları askıda (2026-11-13): önce kalite, çift kontrol tam.

## 4. Yaklaşımlar

Üç tasarım hazırlandı, iki bağımsız hakem puanladı.

| Tasarım | Özü | Güçlü yanı | Zayıf yanı |
|---|---|---|---|
| **Risk** | Düz taşıma + "merkez kuralı"; önce tek kopya, sonra yapraklar, en son tur çekirdeği | Sıra en güvenli; ikinci kopya sorunu zorunlu aşama | `open`/`uuid4` yamalarını atlıyordu; 35 görev iyimser |
| **Test** | Aynı taşıma; yedi ayrı kanıt (N1-N7) ve ağın kendi sınavı | Test bütünlüğü en güçlü | İkinci kopya sorununu isteğe bağlı bırakıyordu |
| **Değer** | Tur çekirdeğini erken taşı ve hemen parçala | Sahibin asıl derdine en çabuk gider | Geri Al yolunu yöntem kanıtlanmadan yeniden yazıyor; `__main__` çözümü test sürecini kirletiyor |

Hakemler bölündü: biri Risk'i, biri Test'i seçti; ikisi de Değer'i güvenlik açısından geri çevirdi. Risk ve Test aynı ailedendir, bu yüzden **birleştirildi**: sıra ve dinamik mekanizma kararları Risk'ten, kanıt ağı Test'ten, pilot ve "sonraki dilim" fikri Değer'den alındı.

**Seçilen yöntem — merkez kuralı.** Taşınan kod kendi içinde başka bir motor adını çıplak çağırmaz; her zaman `game.X` diye çağırır. Böylece bir test `game.roll_d20` adını yamaladığında, hangi dosyada olursa olsun bütün çağıranlar yamayı görür. Bu, repoda zaten 24 modülün kullandığı alışkanlıktır **[D]**.

Reddedilenler: (a) çıplak çağrıyla düz yeniden dışa vurum: sessiz kaçış, yasak; (b) yamaları yeni modüllere çevirmek: ~1 045 test satırı, her biri onay listesi; (c) yamayı parçalara aynalayan gizli mekanizma: ikinci bir sihir katmanı.

Kabul edilen bedel: taşınan gövdelerde `game.` öneki görünür. Bağlaşım kaybolmaz, görünür olur. Öneki kaldırmak ayrı, isteğe bağlı bir iştir.

**Önek nasıl eklenir (bağlayıcı).** Önek, kaynak metin **yerinde** düzenlenerek eklenir: betik `tokenize` ile ad belirtecinin konumunu bulur ve o satıra yalnız `game.` karakterlerini ekler. Kaynağı yeniden üreten hiçbir araç kullanılmaz: `ast.unparse`, biçimleyici, yeniden düzenleme aracı, ruff `--fix` **yasak**. Neden: `game.py`'de 1 056 yorum var, 119'u Kadir'i, bir sahip kararını ya da bir borç numarasını (D-xxx) anıyor **[D, tokenize sayımı]**; yeniden üretim bunları sessizce siler.

## 5. Hedef yapı

Yeni paket: `ai-dnd/game_parts/` (`__init__.py` ile). Satır sayıları kabadır; kesin sınırlar T0'daki çağrı grafiği raporuyla çizilir **[Y]**.

| Modül | İçerik | ~Satır | Yama hassasiyeti |
|---|---|---|---|
| `tables.py` | RACES, CLASSES, SKILLS vb. veri tabloları | 500 | `CLASSES`, `RACES` testte yamalanıyor |
| `schemas.py` | INTENT/NPC/LOCATION/WORLD_UPDATE/DM şemaları, `system_prompt` | 350 | `system_prompt` `live_integration_test.py:42`'de yeniden bağlanıyor **[D]** |
| `text_rules_a.py`, `text_rules_b.py` | 151 kapalı saf yardımcı (3 169 satır) ve regex sabitleri | 3 500 | - |
| `character_rules.py` | karakter, beceri, tür, zar (`roll_d20`, `roll_attack`...) | 1 500 | en çok yamalanan adlar |
| `places.py` | yerel mekan, taverna, kapı, yolculuk, envanter, görev | 2 400 | - |
| `intent.py` | niyet ayrıştırma, normalleştirme, doğrulama | 1 400 | canlı duman betiklerinde yamalanıyor |
| `dialogue.py`, `lore.py` | NPC konuşması, adlar, lore soruları | 3 200 | - |
| `narration.py`, `narration_safety.py` | anlatım, `finalize_narration`, güvenlik kararı | 3 100 | üretimde yeniden bağlanan adlar |
| `new_game.py` | `initialize_game` gövdesi, başlangıç yardımcıları | 500 | - |
| `living_world_turn.py` | cepheler, zaman, olaylar | 2 300 | - |
| `combat_flow.py` | saldırı, hasar, iyileşme, ölüm | 1 800 | ölüm = Geri Al komşusu |
| `coin.py` | para, dükkan, takas | 1 000 | para |
| `savefile.py` | kayıt yükü, doğrulama, yükleme, göç | 1 100 | kayıt |
| `turn.py` | `_dispatch_player_turn`, anahtarlı tur, `_run_player_turn_internal` (bütün hâlde) | 3 900 | Geri Al |
| `terminal.py` | yalnız `__main__` altındaki terminal döngüsü | 200 | - |
| **`game.py` (kalır)** | içe almalar, açık yeniden dışa vurum satırları, `world_state`/`messages` tohumları, `RULE_ORDER`, `GameSession`, `_session`, sarmalayıcı, `create_session`, modül sınıfı değişimi, import anındaki `initialize_game` çağrısı, `_speech_debug_trail`, **`DEFAULT_SAVE_PATH`, `start_terminal_game`** | **≤ 1 500** | Geri Al anlık görüntüsü dokunulmadan kalır |

- Dışarıya açık tek ad `game` kalır. `game.py` dışında kimse `game_parts.*` içe almaz.
- `GameSession` (439 satır, snapshot/restore = Geri Al) ve oturum çekirdeği **taşınmaz**.
- `_speech_debug_trail` taşınmaz: içindeki `open(` testte `patch.object(game,'open',create=True)` ile yamalanıyor ve `game.open` diye bir ad yok **[D]**.
- **`DEFAULT_SAVE_PATH` ve `start_terminal_game` taşınmaz.** `DEFAULT_SAVE_PATH = Path(__file__).resolve().parent / "saves" / "adventure.json"` (24230) **[D]**; bir parçaya giderse terminal kaydı sessizce `ai-dnd/game_parts/saves/` altına düşer ve `test_regression.py` yolu `engine.DEFAULT_SAVE_PATH`'ten okuduğu için kırmızıya dönmez **[D]**. `start_terminal_game` bu yolu ve yerleşik `input`/`print`'i varsayılan argüman olarak yakalar (24233) **[D]**.

**İnceleme seviyesi içerikten belirlenir, modül adından değil (bağlayıcı).** Bir işlevin hangi dosyaya gittiği, para/kayıt/Geri Al'a dokunup dokunmadığını söylemez. Ölçüm **[D, betik]**:
- Anlık görüntü alan/geri yükleyen üst düzey işlevler: `perform_skill_check` (hedefi `character_rules`), `execute_intent` (hedefi `intent`), `_thread_gate`, `_run_player_turn_owned`, `_run_player_turn_keyed`, `_person_answers_stock`.
- Para sözcüğü (`currency|coin|gold|money_owner|pay(`) geçen 34 işlev; 26'sının adında para yok: `_front_step` (23 isabet), `_front_economic_offer` (16), `_the_rest_of_the_line` (15), `_experimental_speech_note` (10), `_thread_gate`, `parse_player_intent`, `_clear_turn_transients`, `_purchase_refused` (6'şar), `_carry_out_thread_turn` (5), `finalize_narration` (2) ve diğerleri.

Kural: T0.7 her işlevi **içeriğine** göre sınıflar ve "hassas liste"yi üretir (bkz. 6, N8). Listede olan bir işlev, hedef modülü ne olursa olsun **yalnız T5/T6'daki "Güçlü, evet" görevlerde** taşınır. "Normal" bir görevin taşıdığı adlar ile hassas liste kesişirse `move_check` görevi reddeder. Listeden ad çıkarmak (yanlış alarm) yalnız yazılı gerekçeyle ve güçlü inceleyenin onayıyla olur; implementer çıkaramaz.

## 6. Yama ve test bütünlüğü güvencesi

**"Yama yüzeyi" tanımı.** Yalnız motor işlevleri değil; `game` üzerinde yamalanan ya da yeniden bağlanan **her** ad yüzeye girer:
- 66 işlev adı (en çok `roll_d20`, `roll_attack`, `roll_damage`, `heal_player`).
- Veri adları: `CLASSES`, `RACES`, `RULE_ORDER`, `system_prompt` **[D]**.
- İçe alınmış adlar: `ollama`, yerleşik `open` (`test_dialogue_live_context.py:119` ve `:126`), `uuid4` (`test_sessions.py:3065`). `uuid4` `game.py`'de **6 işlevde 6 yerde** çağrılır **[D]**: `_apply_player_damage`, `_resolve_player_death_turn`, `_start_combat_with_initiative`, `_down_outside_combat_turn` (dövüş/ölüm), `_migrate_legacy_combat_state` (kayıt göçü → `savefile`), `advance_campaign_time` (yaşayan dünya). Yani `uuid4` çağıranları T4 ve T5'e yayılır; hepsi `game.uuid4()` yazar.
- **Üretim kodunun yeniden bağladığı adlar:** `api/narrative_director.py` `install_narrative_context_adapter` (`ask_dungeon_master`, `build_world_context`, `finalize_narration`) **[D]**; `trace_ai_pipeline.py:77-93` altı ad **[D]**; `api/ollama_adapter.py` `install_for_engine` **[Y]**.
- **`test_*.py` adını taşımayan yeniden bağlayıcılar [D]:** `live_integration_test.py:42` (`game.system_prompt = ...`), `acceptance_test.py:85/589` (`game.roll_d20 = lambda...`), `live_narration_smoke.py:117-121` (`parse_player_intent`, `normalize_intent`, `validate_intent`, `finalize_narration`, `ollama.chat`), `live_phase_c_narrative_smoke.py:278-280` (`ask_dungeon_master`), `offline_test_support.py:27` (`patch.object(engine, "ollama")`), `scripts/gameplay_audit.py` **[Y: satırı okunmadı]**.

Kural: parçalarda bu adların hiçbiri çıplak kullanılmaz; `game.uuid4()`, `game.ollama.chat(...)`, `game.CLASSES`, `game.system_prompt` yazılır.

**Kanıt ağı**

| No | Kontrol | Tür | Kanıtladığı |
|---|---|---|---|
| N1 | **Altın yüzey**: `vars(game)` içindeki her ad, türü, imzası, `__module__` değeri ve `_session_bound` adların tam kümesi dondurulur. **Fark kuralı:** bir taşıma görevinde altın dosyada yalnız o görevin taşıdığı adların `__module__` satırı değişebilir; başka her fark betikle reddedilir | test, CI + fark betiği | ad, sarmalayıcı ya da imza kaybolmadı; altın dosya gürültüyle yenilenmiyor |
| N2 | **Yama sayımı**: `ai-dnd` altındaki **bütün `.py` dosyaları** (`game.py` ve `game_parts/` hariç): testler, `live_*`, `acceptance_test.py`, `offline_test_support.py`, `scripts/`, `trace_ai_pipeline.py`, `api/`. Sayılanlar: `patch("game.X")`, `patch.object`, `setattr`, **modül düzeyi dahil** düz `game.X = ...` ataması. Takma ad (`engine`, parametre) çözülemezse tutucu davranılır: ikinci argümanı bir `game` adı olan her `patch.object`/`setattr` sayılır. Liste elle tutulmaz, taramadan türetilir | test, CI | yama yüzeyi biliniyor, yeni yama gizlenemiyor |
| N3 | **Yönlendirme denetimi** (`ast` + `symtable`); kurallar aşağıda | test, CI | statik kanıt: yamadan kaçış yapısal olarak imkânsız |
| N4 | **Yama isabet defteri**: her (test, yama hedefi) için sahte nesne çağrıldı mı; taşımadan önceki tabanla fark. Taban TM0'da **iki kez** ölçülür; iki koşu arasında değişen satırlar "gürültü kümesi" olarak kaydedilir ve farktan düşülür | betik, kilometre taşı | dinamik kanıt: eskiden ateşleyen hiçbir yama susmadı |
| N5 | **Taşıma eşdeğerliği** (`move_check`); kurallar aşağıda | betik, her görev (implementer ve inceleyen ayrı koşar) | taşıma mantığı ve yorumları değiştirmedi |
| N6 | **Kaynak okuyan testler**: tek yardımcı `engine_source_files()` = `game.py` + bütün parçalar; metin/AST tarayan testler bunu kullanır | test + onay listesi | "şu metin kodda yok" türü denetimler körleşmedi |
| N7 | **Kapsam eşitliği**: işlev başına koşulan satır sayısı, bölmeden önce ve sonra aynı. Taban TM0'da iki kez ölçülür; koşudan koşuya değişen işlevler gürültü kümesine girer, yalnız onlar eşitlikten muaftır | betik, TM4 ve son | testler aynı kodu hâlâ çalıştırıyor |
| N8 | **Hassasiyet taraması**: her üst düzey işlev için AST + regex: anlık görüntü/geri yükleme, kayıt/yükleme/serileştirme çağrısı, dosya yazma, para alanı okuma-yazma. Çıktı: "hassas liste" dosyası | betik (T0.7), `move_check` her görevde okur | para/kayıt/Geri Al'a dokunan hiçbir kod normal incelemeyle taşınmadı |

**N3 kuralları (yeniden yazıldı).** Eski metin "parçada yalnız `import game`" diyordu; bu, parçalara gidecek içerikle çelişiyordu: 170 üst düzey atamanın 68'i `re.compile(` içerir, 127 işlevde 338 işlev içi içe alma vardır (`grounded_action`, `bold_acts`...) **[D]**.
1. Bir parça, üstte ve işlev içinde **stdlib** ve **motor dışı proje modüllerini** (`game.py`'nin bugün içe aldıkları) içe alabilir. İşlev içi içe almalar olduğu gibi taşınır.
2. Bir parça kardeş parçayı içe almaz; `from game import ...` yazmaz; `import game` serbesttir.
3. Yama yüzeyindeki ad (N2 listesi: `ollama`, `uuid4`, `open`, yamalanan veri ve işlevler) parçada **hiçbir yolla** doğrudan bağlanmaz ve çıplak kullanılmaz.
4. `game.` erişimi yalnız işlev gövdesinde olur; modül düzeyinde, varsayılan argümanda, dekoratörde olmaz.
5. Bir modül düzeyi sabit başka bir sabite dayanıyorsa **ikisi aynı parçada** durur (T0.1 sabit bağımlılık kümelerini çıkarır). Başka parçadaki kod o sabiti `game.SABIT` diye okur.
6. **Kimlik adları yasak:** parçada `__file__`, `__name__`, `globals()`, `locals()`, `vars()`, `sys.modules` geçemez; istisna yalnız görev başına incelenen izin listesindeki (dosya, işlev, ad, gerekçe) satırlardır. Neden: bu adlar her zaman tanımlıdır, "tanımsız ad" denetimi ve N5 onları göremez, ama parçada anlamları değişir.
7. Parçada tanımsız ad olmaz; `game.<karakter özniteliği>` okunmaz.

**N5 kuralları (genişletildi).** Taşınan her blok için üçü birden tutmalı:
- (a) AST, eklenen `game.` öneki geri alınınca eskisiyle aynı.
- (b) **Belirteç akışı** (`tokenize`; `COMMENT` ve belge dizgileri dahil, tür + metin) eskisiyle aynı; yalnız eklenen `game` ve `.` belirteçleri düşülür.
- (c) Blok, işlevin üstündeki yorum satırlarını da kapsar; `game.py` + bütün parçalardaki toplam yorum sayısı tabandaki sayıya (bugün 1 056) eşit kalır.
- Ayrıca: `game.py` farkı yalnız silme + içe alma satırıdır; taşınan ad hassas listede ise görev "Güçlü, evet" olmalıdır; elle düzenlenen her satır "mekanik değil" diye işaretlenir.

**Kural:** N5 "değişen" sayısı sıfırdan büyükse ileriye doğru yamanmaz; taşıma baştan yapılır.

**Bilinen kör nokta, açıkça:** N4 "çağrılmadı" diye doğrulayan yamaları göremez (`assert_not_called`). Örnek: `test_dialogue_live_context.py:119-121` **[D]**. Bu testlerin tek koruması N3'tür; T0.2'de adları listelenir.

**Ağın kendi sınavı (zorunlu, hacimli taşımadan önce).** Pilot taşımadan sonra geçici bir dalda beş hata ekilir: yamalanan ada çıplak çağrı, eksik yeniden dışa vurum, parçaya yasaklı metin, silinmiş bir yorum, parçada `__file__`. N3, N1, N6, N5, N3 sırayla kırmızıya dönmelidir. Hiç kırmızı görülmemiş ağa güvenilmez.

**Oturum bağlama testi.** Dışarıda 39 ad üzerinde 190 `game.X(..., session=...)` çağrısı var **[hakem AST sayımı]**. Taşınmış bir işlev için kırmızı test: `game.<işlev>(session=s)` hâlâ `s` oturumunu bağlıyor mu. Bu ve iki içe alma sırası testi oturum kurar; `fixed_town` kullanır.

## 7. Dinamik mekanizmalar

| Mekanizma | Bugün | Karar | Kontrol |
|---|---|---|---|
| `globals()` sarmalayıcısı | `_ENGINE_FUNCTIONS` yalnız `value.__module__ == __name__` olanları alır (24262) **[D]**; taşınıp geri içe alınan işlev **sarılmaz**, `session=` çalışmaz | `game.py`'de kalır. Tek satır genişletme: `... or value.__module__ in _PART_MODULES` (açık liste). Yeniden dışa vurumlar açık `from game_parts.x import a, b` satırlarıdır; yıldızlı içe alma yok | N1; güçlü inceleme |
| `fn.__module__ == "game"` bağımlılığı | tek kullanım sarmalayıcı süzgecinin kendisi; `scripts/run_regression_evidence.py:129` yalnız test işlevlerine bakar (hakem doğrulaması) | çözüldü | N1 `__module__` kaydeder |
| `__class__` değişimi (`_GameModule`) | `game.max_hp` gibi adları varsayılan oturuma yansıtır; yalnız `__name__ != "__main__"` iken kurulur (24846-24862) **[D]** | Dokunulmaz | N3 |
| Hız | Her `game.X` erişimi Python düzeyindeki `_GameModule.__getattribute__`'tan geçer **[D]**. Sıcak yollar (konuşma, anlatım, tur çekirdeği) T4-T6'da taşınır | **TM2, TM3, TM4, TM5'in her birinde** iki ölçüm, TM0 tabanına karşı: (1) tam paket süresi; (2) **sabit tur ölçütü**: sabit tohum, `fixed_town`, sahte model, aynı N komutluk senaryo, 5 koşunun ortancası. Taban TM0'da iki kez ölçülür (oynaklık bilinsin). **Herhangi biri %10'dan fazla yavaşlarsa dur ve bildir** | süre ölçümü defterde |
| Import anı | `_bind_session_engine()` ve `initialize_game(creation_choice="2", ...)` içe almada çalışır | Çağrılar aynı yerde ve sırada kalır; gövde en son `new_game.py`'ye taşınır. Parçalar içe alınırken `game.`'e dokunmaz | N3; "taze yorumlayıcıda iki içe alma sırası" testi |
| Döngüsel içe alma | Parça `import game` yapar, `game.py` parçaları alır; parçanın üstte aldığı motor dışı modüllerin bir kısmı da `import game` yapar (bugün de böyle) | `game_parts/__init__.py` içinde `import game`; erişim yalnız çağrı anında | alt süreç testi |
| **İkinci kopya** | `test_regression.py:812-821` `builtins.input`'u yamalar, sonra `runpy.run_path(game.py, run_name="__main__")` ile dosyayı **yeniden çalıştırır** **[D]**; `test_sessions.py:4193-4205` `exec(kaynak, düz sözlük)` ile kopya kurar **[D]**; `legacy_debug/` altında 25 betik de `game.py`'yi `exec` eder **[D sayım; hangi testin koştuğu Y]** | **Zorunlu aşama T1.** Ayrıntı aşağıda. `sys.modules['game']` takma adı çözümü **reddedildi** | karar 1 |
| Kimlik adları | `sys.modules[__name__]`: `_local_place_turn` (18618), `_run_player_turn_internal` (23920). `logging.getLogger(__name__)`: `_repair_dilim1_fields` (2886), `_repair_dilim2_fields` (2949); hiçbir test günlükçü adını doğrulamıyor (`test_dilim2_save_repair.py:151` yalnız `level=`) **[D]**. `locals().get("preparsed_scene_intent")` yalnız tur işlevinde (22553) **[D]** | Elle düzenleme: `sys.modules[__name__]` → `game`; `getLogger(__name__)` → `getLogger("game")`, **önce** günlükçü adını `"game"` diye sabitleyen test. `locals()` olduğu gibi kalır, N3 izin listesine ve borç defterine girer. Hepsi en son, güçlü incelemeli görevlerde | N3 kural 6; N5 "mekanik değil" |
| Terminal kayıt yolu | `DEFAULT_SAVE_PATH` `__file__`'a bağlı (24230); `__main__` döngüsü onu `/save`, `/load` için kullanır (24897) **[D]** | `game.py`'de kalır; `terminal.py` onu `game.DEFAULT_SAVE_PATH` diye okur. T1'de sabitleme testi: yol, test dosyasının konumundan hesaplanan `ai-dnd/saves/adventure.json`'a eşit (`engine.__file__`'tan değil). Bugün yeşildir; ekilen ihlalle (yol bir parçaya taşınmış gibi) kırmızı gösterilir | test, CI |
| Oturum içi `session=` çağrısı | `game.py:20114` `gear.don_shield(..., session=session)`, başka modüle çağrı. Motor işlevinden motor işlevine `session=` geçen çağrı **sıfır** | - | - |
| Kaynak okuyan testler | ~9 metin/AST tarayıcı ve yazar sayımı testleri (`test_talk_mode_writers`, `test_narration_source_record`, `test_combat_v2_authoritative`) **[Y: her birinin biçimi]**; `test_exits.py:211` özyinelemesiz `root.glob("*.py")` kullanır **[D]**. **Düzeltme:** `test_coin_writers.py` WRITERS tablosunda hiç `game.py` satırı **yok** ve tarama zaten `ROOT.rglob("*.py")` ile özyinelemelidir (satır 27-39, 44) **[D]**; önceki taslaktaki "para sayımı `game.py:<işlev>` yolları" cümlesi yanlıştı. Bu test değiştirilmez; parçaları kendiliğinden görür | Diğerleri T0.3'te, paket boşken N6 yardımcısına bağlanır. Her yeniden yazılan test için **ekilen ihlal kanıtı** | onay listesi |
| `engine_hash` | `campaign_store.py` 583-587 `game.py` baytlarının sha256'sı; yazılır, **hiçbir yerde karşılaştırılmaz** **[önceki tur D; bu turda yeniden bakılmadı]** | `game.py` + sıralı `game_parts/*.py` üzerinden hesaplanır. Önce kırmızı test: "parça değişince hash değişir" | güçlü inceleme (kayıt) |
| Yol korumaları | `scripts/development_archive.py:25`, `development_checks.py:153`, `security_gate.py`, `test_development_tooling.py` | `ai-dnd/game_parts/` eklenir | kendi testleri |
| CI dışı testler | `ai-dnd/scripts/full_python_suite.py` yalnız `api/tests/test_*.py` toplar **[D]**; 36 kök `ai-dnd/test_*.py` CI'da koşmaz | Her kilometre taşı **yerel `par`** koşusunu kullanır. CI yeşili tek başına yetmez | defter |

**T1 ayrıntısı (ikinci kopya) — bu bir saf taşıma değildir.**
- Bugün terminal testi şöyle çalışır: `builtins.input` yamalanır, `runpy` `game.py`'yi baştan çalıştırır, `def start_terminal_game(input_fn=input, ...)` **yama altında** yeniden tanımlanır ve yamalı `input`'u yakalar. T1'den sonra `__main__` koruması zaten içe alınmış asıl `game`'e devreder; o modül `input`'u ilk içe almada yakalamıştır, yama ona ulaşmaz ve test **gerçek stdin'i okur**.
- Bu yüzden T1.1 bir **kod değişikliğidir**: terminal girişi `input_fn` ve `print_fn`'i **çağrı anında** verir (`start_terminal_game(input_fn=input, print_fn=print)` çağrıda yazılır, tanımda yakalanmaz). Önce kırmızı test, kendi güçlü incelemesi (döngü `save_game`/`load_game` çağırır).
- `exec` sözleşmesi **emekli olur**. `game.py:24859-24860` yorumu "düz exec sözlükleri `create_session()` kullanmalı" der ve `test_sessions.py:4193` bunu sınar. Bölmeden sonra `exec` kopyası yarı kopya, yarı asıl modül olur; bu sözleşme tutulamaz. Test "eşit sıkılıkla yeniden yazılmaz": aynı sınırı (çıplak adlar durum girdisi değildir) asıl modül üzerinde sınayan yeni testle değiştirilir ve onay listesine **"sözleşme kaldırıldı, gevşetme"** diye açıkça yazılır. Yorum satırı Kadir'in onayıyla güncellenir.
- `legacy_debug/` altındaki 25 `exec` betiği borç defterine "bölmeden sonra güvenilmez" diye yazılır; düzeltilmez.
- Plan yazarına not **[Y]**: `python game.py` dosyayı iki kez çalıştırır (`__main__` olarak ve `game` olarak). `__main__` korumasını dosyanın en üstüne almak bunu önler; T1.1'de ölçülüp karar verilir.

## 8. Aşamalar ve görevler

Her görev: bir implementer + bir bağımsız inceleyen; N1 (fark kuralıyla) + N2 + N3 testleri; taşıma görevinde N5 çıktısı deftere; hedefli testler = taşınan ada dokunan test modülleri + sabit komşu seti. "Güçlü" = en güçlü modelde bağımsız inceleme. Kilometre taşı (TM) = tam paket bayrak kapalı, sonra açık (asla birlikte), N4 farkı, PR, CI yeşil, Kadir'in merge onayı.

| Görev | Kapsam | Doğrulama | İnceleme | Para/Kayıt/Geri Al |
|---|---|---|---|---|
| **T0 Güvenlik ağı** (motor değişmez; **BM'den önce `main`'e girmez**, bkz. 12) | | | | |
| T0.1 | Envanter betikleri; çağrı grafiği ve sabit bağımlılık raporu (kesin modül sınırları); bu belgedeki **her [D] iddiasının betikle yeniden sınanması**; N1 altın yüzey + fark betiği | N1 değişmemiş `game.py`'de yeşil; ekilen eksik ad kırmızı | normal | hayır |
| T0.2 | N2 yama sayımı (geniş kapsam, modül düzeyi atama, "çağrılmadı" testleri listesi) | ekilen bilinmeyen hedef kırmızı; `live_integration_test.py`'deki `system_prompt` listede görünüyor | normal | hayır |
| T0.3 | N6 yardımcı; kaynak okuyan testler; `test_exits.py:211`. `test_coin_writers.py` **değişmez** | test başına ekilen ihlal kanıtı; onay listesi | **Güçlü** (sınır yeniden tanımlanıyor) | teste göre; para testi yok |
| T0.4 | N5 `move_check` (AST + belirteç + yorum sayımı + hassas liste denetimi) ve kendi sınavı | bilerek bozulmuş taşıma, silinmiş yorum ve `ast.unparse` çıktısı "değişti" der | normal | hayır |
| T0.5 | N4 defter aracı, N7 kapsam, sabit tur ölçütü; tabanlar iki bayrakta, **ikişer kez** | gürültü kümesi deftere yazıldı; çıktı `.local/` altında | normal | hayır |
| T0.6 | Boyut mandalı: `game.py` büyüyemez | ekilen fazla satır kırmızı | normal | hayır |
| T0.7 | N8 hassasiyet taraması; hassas liste; görev tablosunun listeye göre düzeltilmesi | elle seçilmiş 6 bilinen ad (`perform_skill_check`, `execute_intent`, `_front_step`...) listede çıkıyor | **Güçlü** (inceleme seviyelerini bu belirler) | evet |
| **TM0** | BM merge'inden sonra: N1/N2/boyut dosyaları taze `main`'de yeniden üretilir; tam paket ×2, ikişer ölçüm (N4/N7/süre tabanı); CI; PR | | | |
| **T1 Tek kopya** | | | | |
| T1.1 | Terminal girişi `input_fn`/`print_fn`'i çağrı anında verir (kod değişikliği); `__main__` döngüsü `terminal.py`'ye; kayıt yolu sabitleme testi | önce kırmızı test; `test_regression` hedefli | **Güçlü** | evet (terminal kaydet/yükle) |
| T1.2 | `runpy` testi tek modüle karşı yeniden yazılır; `exec` sözleşmesi emekli, yerine yeni test | onay listesi, "sözleşme kaldırıldı, gevşetme" | **Güçlü** | evet (durum/kayıt girdisi) |
| **T2 Sarmalayıcı, hash, pilot** | | | | |
| T2.1 | `_PART_MODULES` ile süzgeç genişletme (liste boş) | N1 kümesi birebir aynı | **Güçlü** | evet (oturum) |
| T2.2 | `engine_hash` dosya kümesi üzerinden | önce kırmızı test | **Güçlü** | evet (kayıt) |
| T2.3 | Yol korumaları | kendi testleri | normal | hayır |
| T2.4 | **Pilot, iki parça:** (a) `roll_d20`; (b) bir `re.compile` sabiti + onu kullanan bir saf yardımcı (N3 kural 1 ve 5'in kanıtı). N3 kurulur; ağın kendi sınavı (5 ekilen hata); `session=` kırmızı testi; iki içe alma sırası testi | beş ağ kırmızı görüldü, sonra yeşil | **Güçlü** | hayır |
| **TM1 = devam/dur kapısı** | tam paket ×2; N4: **sıfır düşüş** (gürültü kümesi dışında). Düşüş varsa plan durur, Kadir'e bildirilir | | | |
| **T3 Yapraklar** | | | | |
| T3.1-2 | `tables.py`, `schemas.py`; kimlik doğrulanır (`game.RACES is tables.RACES`); okuyanlar `game.CLASSES`, `game.system_prompt` yazar | veri yaması testleri adıyla koşar | normal | hayır |
| T3.3-6 | 151 saf yardımcı → `text_rules_a/b.py`, görev başına ~800 satır; **hassas listedekiler hariç** | N5 | normal | hayır |
| **TM2** | tam paket ×2, N4, **süre + tur ölçütü**, PR | | | |
| **T4 Düşük etkili alanlar** (hassas listedekiler hariç) | | | | |
| T4.1-5 | `character_rules`, `places`, `intent`, `dialogue`, `lore` | o modüldeki adları yamalayan testler (N2 listesi) | normal | hayır |
| T4.6-9 | `narration`, `narration_safety`, `living_world_turn`, `new_game` | üretim yeniden bağlama adları için ayrı test: bağdaştırıcı kuruluyken taşınan çağıran onu görüyor | normal | hayır |
| **TM3** | tam paket ×2, N4, süre + tur ölçütü, PR + **Kadir 10 dk oynar** | | | |
| **T5 Para, kayıt, dövüş, hassas artıklar** | | | | |
| T5.1 | `combat_flow.py` | ölüm/Geri Al testleri | **Güçlü** | evet |
| T5.2 | `coin.py` | `test_coin_writers` (değişmeden yeşil), K2 testleri | **Güçlü** | evet (para) |
| T5.3 | `savefile.py`; `_repair_dilim1/2_fields` günlükçü düzenlemesi (önce sabitleme testi) | kayıt-yükleme gidiş dönüş testleri | **Güçlü** | evet (kayıt) |
| T5.4-5 | **Hassas artıklar:** T3/T4 modüllerine ait olup hassas listede olan işlevler (`perform_skill_check`, `execute_intent`, `parse_player_intent`, `finalize_narration`, `_experimental_speech_note`...), hedef modüle göre gruplanır | N5; o adlara dokunan testler; sıfır tolerans yolculukları | **Güçlü** | evet |
| **TM4** | tam paket ×2, N4, **N7 kapsam eşitliği**, süre + tur ölçütü, PR | | | |
| **T6 Tur çekirdeği** | | | | |
| T6.1 | `_dispatch_player_turn`, anahtarlı tur, `_execute_intent_internal`, cephe/konu işlevleri (`_front_*`, `_thread_gate`...) | sıfır tolerans yolculukları | **Güçlü** | evet (Geri Al, para) |
| T6.2 | `_run_player_turn_internal` bütün hâlde + elle düzenlenen `sys.modules[__name__]` yerleri | sıfır tolerans yolculukları; elle düzenlemeler brifte adıyla | **Güçlü** | evet (Geri Al) |
| **TM5** | tam paket ×2, N4, süre + tur ölçütü, PR | | | |
| **T7 Kapanış** | | | | |
| T7.1 | Boyut bütçeleri son değerlere; içe alma kuralı testi kalıcı | ekilen aşım kırmızı | normal | hayır |
| T7.2 | Ölü kod kanıt raporu (silme yok) | bkz. 10 | normal | hayır |
| T7.3 | CLAUDE.md satırı, `implementer-preamble.md` maddesi, GLOSSARY/ADR, `docs/design/INDEX.md`, borç defteri satırları, `graphify update .` | - | normal | hayır |
| T7.4 | `move_check` taze `main`'e karşı yeniden; N4+N7 son; bütün dal incelemesi; sabah özeti | tam paket ×2, CI | **Güçlü** | evet |
| **Kapı** | Kadir 10 dk oynar | | | |

Toplam (tahmin): ~40 görev, 7 kilometre taşı (TM0-TM5 + kapanış), 7 PR, ~17 güçlü inceleme. Hassas listenin kesin boyu T0.7'de çıkar; T5.4-5 buna göre bölünür **[Y]**. Her aşama taze `main`'den kendi kısa dalıdır.

## 9. Araçlar

| Araç | Karar | Ne zaman | Sınır |
|---|---|---|---|
| stdlib `ast` / `symtable` / `tokenize` (N1-N3, N5, N8, boyut) | **Evet, CI'da** (N1-N3, boyut). Yeni bağımlılık yok; asıl kilit bunlar | T0'dan itibaren | - |
| **coverage.py** | **Evet**, yalnız geliştirme, sabit sürüm, CI'da değil | TM0 taban (iki kez), TM4, son | Yavaşlatma **[Y]**; yalnız rapor |
| **ruff** | **Evet**, yalnız geliştirme, dar: F821, F401, F811; kapsam `game.py` + `game_parts/` | T2'den itibaren yerelde; CI adımı ancak plan bittikten sonra | `--fix` ve `format` **asla**. N3'e ikinci göz, kilit değil |
| **vulture** | **Evet**, bir kez, yalnız rapor | T7.2 | Tek başına hiçbir şey kanıtlamaz |
| Kaynak yeniden üreten araçlar (`ast.unparse`, rope, libcst kod üretimi, biçimleyiciler) | **Hayır** | - | Yorumları siler ya da biçimi değiştirir; N5 (b) kırmızı verir |
| import-linter | **Hayır** | - | Gereken kurallar N3'te |
| **desloppify** | **Hayır** | - | Kod ve hook kurar; "doğrulanmamış skill/hook yok" kuralıyla çelişir |
| graphify | Var; gezinme için | T7.3'te güncelleme | Yama ve dinamik yolları göremez |
| N4 yama defteri | Kendi betiğimiz | kilometre taşları | `unittest.mock` iç API'sine yaslanır; `slot.sh` içinde koşup koşmadığı **[Y]**. Kurulamazsa deftere yazılır, N3 + N7 + tam paket kalır ve Kadir'e bildirilir |

## 10. Ölü kod kanıtı ve sahibin kararı

Bir işlev ancak **dört koşul birden** tutarsa "ölü" diye Kadir'e sunulur:
1. Bütün repoda (ai-dnd, artifacts, lib, scripts, tools, JSON, belgeler) tanımı dışında adı geçmiyor.
2. Tam pakette, bayrak kapalı **ve** açıkken, tek satırı bile koşmamış (coverage).
3. Dinamik yoldan erişilemiyor: `getattr(game, ...)` ya da `session.<ad>` kalıbında yok.
4. vulture da aynı şeyi söylüyor.

Bugünkü adaylar (yalnız ad taramasıyla, 5 işlev, 44 satır): `_filter_unsupported_lore_paragraphs`, `_existing_local_tavern`, `analyze_player_action`, `update_world_state_from_player`, `is_dialogue_or_emotion`. Dört koşul henüz **sınanmadı**.

Çıktı: tek tablo (ad, satır, sade Türkçe "ne yapıyordu", kanıt, son dokunan commit, öneri). **Hiçbir şey Kadir'in "evet"i olmadan silinmez.** Silme, plan bittikten sonra kendi küçük PR'ıdır. Beklenti dürüstçe: kazanç küçük (onlarca satır); asıl "ölü ağırlık" dev işlevlerin içindedir ve bir sonraki dilimin konusudur.

## 11. Yeniden şişmeyi önleme

- `api/tests/test_engine_size_budget.py` + bütçe dosyası (CI):
  - `game.py` ≤ 1 500 satır; her parça ≤ 2 500; `turn.py` ve `narration_safety.py` geldikleri boyutta dondurulur, yalnız küçülebilir.
  - 150 satırı aşan işlevler bugünkü uzunluklarıyla dondurulmuş listede; yeni giriş ve büyüme yok.
  - **Mandal:** bir bütçe gerçek boyutun 50 satırdan fazla üstündeyse test kırmızı olur (bütçe boşluk biriktiremez). Bedeli: bir dosya 50 satırdan fazla küçülünce bütçe sayısını **düşürmek** için de bir satır değişir; düşürme onay istemez.
  - Herhangi bir sayıyı **yükseltmek** = onay listesi + Kadir. **Bu kalıcı bir kuraldır ve Kadir'e sorulur (karar 10); onaylanmadan yürürlüğe girmez.**
- `game.py` ad izin listesi (N1'den): `game.py`'ye yeni üst düzey işlev eklemek testi kırar.
- N1, N2, N3 kalıcıdır. N4, N5, N7, N8 plan bitince emekli olur.
- CLAUDE.md'ye tek satır (karar 8): "game.py'ye yeni işlev eklenmez; yeni kod ilgili `game_parts` modülüne ya da kendi modülüne girer. `game_parts` içinde motor adları `game.X` diye çağrılır. Boyut bütçesi yalnız Kadir'in onayıyla yükseltilir." Aynı madde `docs/agents/implementer-preamble.md`'ye.

## 12. Sıralama ve takvim

- **Başlangıç koşulu:** BM `main`'e birleşmiş ve Kadir'in BM oynayış kapısı geçilmiş olmalı. BM bugün `origin/main` 088011b3'te **değil**.
- **T0 ve BM (düzeltildi).** Önceki taslak "T0 BM beklerken başlasın" diyordu ama bedelini yazmıyordu. BM dalı `game.py`'de +130/-58 satır (net +72) ve 3 yeni üst düzey işlev getirir **[D: `git diff --shortstat origin/main...origin/task/bm-once-model-20261117`]**; 29 test dosyası da değişir **[eleştiri ölçümü, bu turda yeniden sayılmadı]**. Boyut mandalı, N1 ad listesi ve N2 sayımı BM'den önce `main`'e girerse BM'nin merge'i CI'da kırmızı olur ve her BM düzeltmesi Kadir'den bütçe onayı ister. Bu yüzden:
  1. BM'den önce T0 **yalnız birleştirilmemiş bir dalda** yazılır; betikler rapor verir, hiçbir kilit `main`'e girmez.
  2. BM `main`'e girdikten sonra N1 altın dosyası, N2 sayımı, boyut bütçesi ve hassas liste **o `main` üzerinde yeniden üretilir**.
  3. T0'ın PR'ı ve TM0 bundan sonra gelir.
- **Dondurma:** bir aşama dalı açıkken başka hiçbir dal `game.py` ve `game_parts/`'a dokunmaz; acil düzeltmeler aşamalar arasında girer. Taşınmış blok ile düzenlenmiş blok makineyle güvenle birleştirilemez. UI işi (yeniden tasarım planının A2.2 B adımı, v0) paralel yürür; `game.py`'ye dokunmaz.
- **Oynayış:** TM3'te ve kapanışta, en az 10'ar dakika.
- **Süre (tahmin, ölçüm değil):** 11-14 oturum; 14 tam paket koşusu + TM0'daki ikinci taban koşuları (~30 dk'şar, hiçbiri eşzamanlı değil) + N4/N7/tur ölçütü koşuları.
- **Sonraki dilim (ayrı tasarım, bu planın hemen ardından):** tur çekirdeğini parçalamak. Yöntem taslağı: üst düzey her blok için girdi/çıktı dökümü; yalnız 5 ya da daha az çıktısı olan bloklar kesilir; önce `locals().get('preparsed_scene_intent')` kendi kırmızı testiyle değiştirilir; her çıkarma güçlü inceleme alır.

## 13. Riskler

| Risk | Önlem |
|---|---|
| Taşınan kod yamadan kaçar; test yeşil ama boş | N3 statik + N4 dinamik + ağın kendi sınavı; TM1 devam/dur kapısı |
| `test_*.py` olmayan dosyadaki yeniden bağlama gözden kaçar | N2 kapsamı: `ai-dnd` altındaki bütün `.py`; modül düzeyi atama sayılır |
| Para/kayıt/Geri Al kodu normal incelemeyle taşınır | N8 hassas liste; `move_check` kesişimi reddeder; hassaslar yalnız T5/T6'da |
| Taşıma yorumları siler | yerinde önek ekleme; N5 belirteç ve yorum sayımı; yeniden üreten araç yasak |
| `__file__`/`__name__` parçada sessizce anlam değiştirir (kayıt yolu, günlükçü adı) | N3 kural 6 + izin listesi; `DEFAULT_SAVE_PATH` ve `start_terminal_game` kalır; yol ve günlükçü sabitleme testleri |
| N3 kuralı içerikle çelişir, plan ortasında bükülür | kural yeniden yazıldı; pilotta regex sabitiyle kanıtlanır |
| T0 kilitleri BM'yi kırar | T0 BM'den önce `main`'e girmez; kilitler BM sonrası yeniden üretilir |
| "Çağrılmadı" testleri sessizce boşalır | N4 göremez; N3 tek koruma; testler T0.2'de adıyla listelenir |
| Taşınan işlev `session=` bağını yitirir | N1 kümesi; açık `_PART_MODULES`; 190 çağrı için kırmızı test |
| Üretim bağdaştırıcısı (`narrative_director`) atlanır | adlar yama yüzeyinde; T4.6-9'da ayrı test |
| İkinci kopya (runpy, exec) ayrışır; terminal testi gerçek stdin okur | T1 zorunlu, kod değişikliği olarak; `exec` sözleşmesi açıkça emekli; `legacy_debug` borç defterinde |
| Eksik `game.` öneki, yalnız nadir yolda NameError | N3 tanımsız ad denetimi + ruff F821 |
| Kaynak okuyan test körleşir | N6 + ekilen ihlal kanıtı; `test_exits.py:211` ayrıca |
| "Saf taşıma" içinde gizli davranış değişikliği | N5 (başarısızsa baştan), N7, sıfır tolerans yolculukları |
| Tur başına gecikme artar, paket süresi bunu göstermez | TM2-TM5'te paket süresi **ve** sabit tur ölçütü; +%10 üstü = dur ve bildir |
| N1/N4/N7 farkları gürültüye boğulur, gerçek sorun gözden kaçar | N1 fark kuralı; N4/N7 tabanı iki kez, gürültü kümesi kayıtlı; yeni testlerde `fixed_town` |
| Olağan dışı içe alma sırasında döngü | `game_parts/__init__` + alt süreç testi |
| Başka dalda değişmiş blok taşınırken kaybolur | aşama boyunca dondurma; N5 taze tabana karşı; merge öncesi yeniden |
| N4 kurulamaz | deftere yazılır; N3 + N7 + tam paket kalır; Kadir'e bildirilir |
| Plan uzar, `main`'den uzaklaşır | aşama başına kısa dal ve PR |
| Beklenti: "spagetti bitti" sanılır | Bu plan yalnız taşır; parçalama sonraki dilimdir (karar 4) |

## 14. Sahibin kararları (Kadir 2026-11-17: hepsi öneri yönünde onaylandı)

1. **Terminal oyunu ve ikinci kopyalar.** `python game.py` tek gerçek motoru kullansın; "motor dosyası düz `exec`/`runpy` ile ikinci kopya olarak çalıştırılabilir" sözleşmesi **kaldırılsın** mı? Sonuç: terminal giriş kodu küçük bir değişiklik alır, 1 test yeniden yazılır, 1 testin sözleşmesi kalkar (onay listesine "gevşetme" diye girer), `legacy_debug` altındaki 25 eski betik güvenilmez sayılır. **Öneri: evet.** Hayır denirse merkez kuralı güvenli değildir.
2. **Zamanlama.** Taşıma BM merge'i ve BM oynayışından sonra başlasın. T0 BM beklerken **yalnız birleştirilmemiş dalda** yazılsın; kilitler (boyut mandalı, ad listesi, yama sayımı) `main`'e ancak BM'den sonra ve yeniden üretilerek girsin mi? **Öneri: evet.** Tersi BM'yi CI'da kırar.
3. **Dondurma.** Bir aşama dalı açıkken `game.py`'ye başka iş girmesin mi? **Öneri: evet.**
4. **Kapsam.** Bu plan yalnız taşısın; dev işlevleri parçalamak hemen ardından ayrı dilim olsun mu? **Öneri: evet.**
5. **Araçlar.** ruff, coverage, vulture sabit sürümlü, yalnız geliştirme paketi olarak kurulsun (hook yok, otomatik düzeltme yok); desloppify kurulmasın mı? **Öneri: evet.**
6. **Merge ritmi.** Yedi küçük PR (yedi onay) mı, sonda tek büyük PR mı? **Öneri: yedi küçük.**
7. **Oynayış.** TM3'te ve kapanışta 10'ar dakika yeterli mi? **Öneri: evet.**
8. **CLAUDE.md satırı** (bölüm 11) eklensin mi? **Öneri: evet.**
9. **Ölü kod.** Kanıt tablosu gelince: silinsin mi, kalsın mı? **Öneri: tablo gelmeden karar verme.**
10. **Boyut bütçesi kuralı (yeni, kalıcı).** Bölmeden sonra her dosyanın bir satır sınırı olacak. Sınırı **yükseltmek** her seferinde senin onayını istesin mi? Ayrıca sınır gerçek boyutun en çok 50 satır üstünde durabilsin mi (dosya küçülünce sınır da düşürülür; düşürme onay istemez)? Bedeli: motor büyüdükçe ara sıra sana "şu dosyanın sınırını X'ten Y'ye çıkarayım mı" diye sorulur. **Öneri: evet;** hayır dersen sınırlar yalnız uyarı verir ve dosya yeniden şişebilir.
11. **Hassas kod incelemesi.** Para/kayıt/Geri Al'a dokunan her işlev, hangi dosyaya giderse gitsin en güçlü modelle incelensin mi? Bedeli: ~5 ek güçlü inceleme (token). **Öneri: evet;** bu zaten CLAUDE.md'nin dokunulmaz kuralıdır, burada yalnız maliyeti bildirilir.

## 15. Kurucuya kalanlar

Planı yazacak (writing-plans) ve yürütecek oturum için açık işler:

- **Doğrulanmadı:** kesin modül sınırları ve sabit bağımlılık kümeleri (T0.1); hassas listenin kesin boyu (T0.7; kaba ölçüm ~45 işlev, çoğu zaten T5/T6'da); sarılan adların tam sayısı (beklenen ~517); N4'ün `slot.sh` içinde koşması ve yükü; coverage yavaşlatması; `api/ollama_adapter.py` `install_for_engine` ve `scripts/gameplay_audit.py` satırları; yazar sayımı testlerinin (para dışındakiler) biçimi; `legacy_debug` betiklerinden hangilerinin bir testte koştuğu; BM dalındaki 29 test dosyası sayısı; `engine_hash` satırları (bu turda yeniden bakılmadı); `python game.py`'nin çift çalıştırma maliyeti.
- **Sabit olmayan varsayılan argümanlar [D]:** `_combat_record_for_actor`, `_has_unregistered_person_name`, `_combat_end_if_decided`, `initialize_game` (2), `_death_save_line`, `start_terminal_game` (3). Varsayılan bir motor adına bakıyorsa N3 kural 4'e takılır; taşıyan görevin brifinde adıyla geçer.
- **Sayım farkı:** `roll_d20` yama sayısı recon'da 283, Test tasarımında 378 (farklı regex). N2 tek doğru sayıyı üretir.
- **Brif kuralları:** her implementer istemine `docs/agents/implementer-preamble.md`, graphify kuralı, "taşıma görevinde başka hiçbir değişiklik yok" ve "önek yerinde eklenir, kaynak yeniden üretilmez" cümleleri girer; brifte satır numarası değil işlev/dosya adı verilir.
- **Onay listesine girecekler:** N6'ya bağlanan her kaynak okuyan test; `runpy` testi; kaldırılan `exec` sözleşmesi testi ve `game.py`'deki yorumu; `test_exits.py` taraması; N3 kimlik adı izin listesindeki her satır; hassas listeden çıkarılan her ad; boyut bütçesindeki her yükseltme.
- **Borç defterine girecekler (8 `|` kuralıyla):** 2 743 satırlık tur işlevi; `locals()` araması; `game.` önek stili ve kaldırma planı; kök testlerin CI dışında olması; `_speech_debug_trail`'in `open` yaması yüzünden `game.py`'de kalması; `legacy_debug` altındaki 25 `exec` betiği; `python game.py`'nin dosyayı iki kez çalıştırması (kalırsa).
- **Defter:** `.superpowers/sdd/<plan>/progress.md`; her kilometre taşında N1/N4/N5/N7 çıktısı, paket süresi ve tur ölçütü yazılır; oynayış yapılmadıysa "oynayış bekliyor".
- **Bu belge commit edilmedi.** Kadir onaylarsa `docs/design/INDEX.md`'ye eklenir.
