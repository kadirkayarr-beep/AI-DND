# Hikâye bağları: iplerin birbirine değmesi (plan, 2026-11-01)

Salt okunur inceleme. Okunan: `AI-DND-c-merge/ai-dnd` @ `01ac28d` (`world_threads.py`, `world_reactions.py`, `town_knowledge.py`, `bold_acts.py`, `thread_catalog.py`, `adventure/dialogue_jobs.py`, `content/world/town_threads.json`, `content/world/catalog/mapping.json`), JARVIS 310 kalıp paketi, Carius oyun testi 2 (`final2.md`), sahip tarifi, Fable görüşü. Kod yazılmadı, test koşulmadı.

> **Güncelleme 2026-11-01 (eleştiri sonrası):** §2–§3 bu haliyle koda geçmez. Eleştiri koda karşı tek tek kontrol edildi; tutan itirazlar §5'te, satır numarasıyla. §3'teki sıralı işler **geçersiz**, yerine §6'daki tek uygulayıcı listesi geçerli. §2'nin tutan kısımları: sıfır ek model çağrısı, yalnız mevcut kimliklere referans, Python'un olayı modelin sesi taşıması, mektuba gerçek içerik, `trouble`/`npc_statements` teşhisi, `linked`'in yalnız yer paylaşımı olduğu tespiti.

## 1. Sorun, tek cümle

Oyun iş döngüsünü veriyor (duy, git, pazarlık, yap, para) ama **her ip kendi içinde kapanıyor**: ipler birbirine değmiyor, tehdit saatte gerçekleşmiyor, mektup ve söylentinin arkasında olgu yok, "şimdi ne olacak?" dört kez doğup dört kez söndü (final2 §Sonuç, sorun 6 ve 15).

Koddan doğrulanan eksikler:
- `world_threads.py`: bir ipin tek tarafı var (`owner_name`, isteğe bağlı `recipient_name`). Başka bir ipin sahibi için **sonuç üreten alan yok**. `trouble` türü açılıyor ama hiçbir geçiş onu "oldu/olmadı"ya götürmüyor; `job_lines` içinde `trouble` boş.
- `_open_thread` satır 263: iplerin yarısı aynı yere bağlanıyor (`linked`) ama bu yalnız **yer paylaşımı**, anlam paylaşımı değil.
- `npc_statements.commit`: NPC'nin "kapıya dayanırlar" gibi sözü `open` kalıyor; **saat onu kapatmıyor**, dünya onu yerine getirmiyor.
- `town_rumors.json` (80 kayıt) **hiçbir Python dosyasından okunmuyor**; `thread_templates`, `ambient_events`, `npc_roles`, `opening_lines` okunuyor. Söylentiler bağsız.
- `dialogue_jobs.letter_text`: mektup metni artık var (`job_lines.errand.letters`, final2'den sonra eklendi) ama `{target}` dışında kampanya olgusuna bağlı değil; okununca hiçbir kayıt değişmiyor.
- `mapping.json`: `muhafiz_karakolu → barracks`, `soylu_konagi → estate` eşlenmiş; `owner_mood` yalnız `wary %20` ve ilişki puanıyla karar veriyor. Karakol ve konak **bir tanıtım olmadan da** aynı sokak tezgâhı gibi açılıyor, ya da tesadüfen hiç açılmıyor.

## 2. Tasarım: "Bağ" (en küçük genel sistem)

Yeni bir olay tipi yok, yeni çağrı yok. Tek yeni kayıt türü: **bağ**. Bir bağ, iki mevcut kaydı (ip, kişi, yer, deed) bir **kural** ve bir **saat** ile ilişkilendirir. Python bağı açar, saat kapatır, model yalnız seslendirir.

```
world["world_links_v1"] = {
  "version": 1, "last_tick": 0, "next_number": 1,
  "links": [ { "link_id": "link_001", "kind": "karsi|donus|vade|kanit",
               "a": "thread_003", "b": "thread_005" | "npc_x" | "deed:12",
               "fires_at": <saniye> | null, "status": "open|fired|spent",
               "known_to_player": false, "public_line": "...(≤90 bayt)" } ],
  "rumours": [ { "rumour_id": "RUM017", "thread_id": "thread_003", "truth": "dogru|yanlis|yari",
                 "text": "...(≤90 bayt)", "speaker_place_kind": "market", "heard": false } ]
}
```

Dört bağ türü, hepsi mevcut kayıtlardan türetilir (ne olacağı tohumla, hangi ipin hangi iple bağlanacağı yer ve tür çakışmasıyla):

| Tür | Anlamı | Nereden türer | Saat gelince (Python) |
|---|---|---|---|
| `karsi` | A'nın işi B'nin derdi | A `errand/hiring` hedef yeri == B `trouble` yeri, ya da aynı yer farklı sahip | A `done` olursa B sahibinin ilişkisi −1, B'nin `public_line` değişir ("o yük geldi, …"); A `filled_by_other` olursa B rahatlar |
| `donus` | İpucu sonra başka anlam kazanır | Mektup/not taşıyan A ile aynı yerde açılan B | B açıldığında A'nın mektup metni B'nin `owner_line`'ını taşır; okuyan oyuncu B'yi "duymuş" sayılır (`mark_heard`) |
| `vade` | Tehdit saatte gerçekleşir | `trouble` ipi açılırken `fires_at = opened_at + h` (tohumdan 6–36 saat); NPC'nin `warn` önerisi | `bold_acts.deeds`'e `kind="happening"` deed yazılır (ziyaret/kapanma/kayıp: 3 genel sonuç), `world_reactions.NEWS` ile yürür; oyuncu oradaysa `reaction_lines` ile görür, değilse sonradan duyar |
| `kanit` | Açıklama hak edilir | Söylentinin `truth_condition_private`'ı bir kayıtla karşılanabilir: mektup okundu, iş bitti, deed görüldü | Koşul tutunca `rumours[i].truth` oyuncuya "doğrulandı/yalan çıktı" olarak söylenebilir; tutmadan NPC yalnız söylentiyi söyler |

Kurallar:
- Bağ **yalnız mevcut kayıtları** kullanır: `thread_id`, `npc.id`, `place_id`, deed indeksi. Ad uydurulmaz (bkz. `_taker` ilkesi).
- Her ipin en fazla 2 bağı, kampanyada en fazla 8 açık bağ (ip tavanı `MAX_ACTIVE=8` ile aynı mantık).
- Bağın `public_line`'ı ipin `public_line`'ı gibi bağlandıktan sonra ölçülür; sığmazsa bağ açılmaz.
- Oyuncu yokken de işler: `tick` içinde `_close_due` gibi `fire_due`. Oyuncu bir gün sonra döndüğünde `arrival_line` benzeri tek satır: "o dert olmuş/olmamış".
- Sahip örneklerinden hiçbiri kopyalanmaz: kalıp JSON'daki metinler "kim-nerede-ne" slotlu; hangi slotun hangi kayda bağlanacağı tohumla değişir, bu yüzden aynı kalıp iki kampanyada iki farklı hikâye verir.

### 2.1 "Şimdi ne olacak?" her an canlı

Değişmez: **her an oyuncunun duyduğu en az bir şeyin 24 oyun saati içinde bir saati olur.** `tick` sonunda Python bakar: `heard` ipler ve `known_to_player` bağlar arasında `min(expires_at, fires_at) − now ≤ 24h` yoksa, `_replenish` bir `vade` bağı olan `trouble` ipini önce açar. Oyuncu bir NPC'yle konuşurken Python o NPC'nin **kendi** bekleyenini tek satır verir: " Seni bekleyen: {public_line}; {kalan} saat." Bu, `town_knowledge.speech_note` içine 1 madde olarak girer, 5 madde / 600 bayt tavanı değişmez.

### 2.2 Söylenti ve mektuba gerçek içerik

- `town_rumors.json` okunur, kalıp `{yer}`/`{kişi}` slotları **yalnız o kampanyada var olan** yer ve `resident_name`'e bağlanır; `truth_status` Python'da kalır, modele gitmez (paket kuralı 5).
- Her söylenti bir ipe veya bağa bağlıdır: `dogru` → ipin `turn`'ünü söyler; `yanlis` → aynı yerde başka gerçek kişiyi suçlar; `yari_dogru` → doğru yer, yanlış kişi. Böylece **söylenti dinlemek de bir seçim**: hangisine inandığın, kime gittiğini değiştirir.
- Mektup: `letter_text` satırı `donus` bağı varsa B ipinin `owner_line`'ını `{target}` yerine taşır. Mektubu açan oyuncu bir şey **öğrenir** (B `heard`), teslim ederse alıcı tepkisi zaten var (`delivered_opened`).
- NPC'nin tehdit cümlesi (`warn` önerisi, listeden `thread_id` ile) Python'da `vade` bağına dönüşür; model saat söyleyemez, Python söyler ("gün batımına kadar").

### 2.3 Karakol ve konak: zincirsiz erişim

Tek karaktere yazılmış zincir yok; **tanıtım kuralı**: `mapping.json`'a `vouch_from` tablosu: `estate: [temple, market, harbor]`, `barracks: [harbor, workshop, market, temple]`. `owner_mood` için ek şart: yer türü `estate/barracks` ise `yes` ancak (a) o türlerden birinin sakiniyle `relationships.score ≥ 1` (bitmiş iş zaten +1 veriyor) **veya** (b) oyuncunun o yerde bir `kanit` bağı tutması (mektubu getirdi, deed'i gördü) **veya** (c) katalog `background_hooks` koşulu oyuncu tarafından gösterildiğinde. Her kampanyada tohum bu listeden 2 tür seçer; Carius limandan da tapınaktan da konağa varabilir, başka karakter başka yoldan. Konak/karakol ipleri `street_talk`'a girmez, yalnız tanıtımdan sonra `public_knowledge`'a düşer: duyulur ama "oraya git" demek yetmez.

### 2.4 Bütçe, çağrı, kayıt

- Model çağrısı: **sıfır ek**. Bağ açma/kapama `campaign_time` → `world_threads.tick` ve `bold_acts.on_time` hattında; okuma `note_mention` id eşlemesiyle; tek yeni öneri türü `warn` mevcut `read_proposal` alanına eklenir.
- Token: prompt'a en fazla 3 kısa satır (bekleyen, söylenti, kendi bağı), her biri ≤ 90 bayt. Fable ölçümü en büyük istem 4.608 token; +~120 token, 8192 içinde. Bağ `public_line` sığmazsa bağ açılmaz, kesilmez.
- Kayıt: `world_links_v1` `world_threads_v1` gibi **tembel tohumlanır** (`ensure` deseni); eski kayıt ilk `tick`'te kazanır. İplere eklenen alanlar (`fires_at`, `turn`) `_OPTIONAL_INTS/_OPTIONAL_TEXTS`'e girer, `validate` yokluğu kabul eder. `thread_id`/`npc.id` dışına referans yok; silinen ip → bağ `spent`.
- Geri alma/replay: bağ sonucu deed olarak `flags.deeds`'e yazılır, mevcut serializer allowlist'i ve `MAX_DEEDS=24` korunur.

### 2.5 Test: aynı tohum, farklı seçim, farklı hikâye

`api/tests/test_story_links.py`, sahte model (0 çağrı), tek tohum:
1. **Determinizm**: aynı 12 komut iki kez → `world_links_v1`, `history`, `deeds` eşit.
2. **Ayrışma**: koşu A `thread_A` kabul+teslim; koşu B aynı ipi reddedip bir gün bekler. Beklenen: A'da `karsi` bağı `fired`, B sahibinin ilişkisi −1, söylenti "doğrulandı"; B'de ip `filled_by_other`, `vade` deed'i oluşmuş, oyuncu dönüşte tek satırla duymuş. `history` statüleri ve `deeds.kind` kümeleri **farklı**, kampanya tohumu aynı.
3. **Canlı kanca**: 40 tur rastgele yürüyüş boyunca her turda "24 saat içinde saati olan duyulmuş şey ≥ 1".
4. **Erişim**: tanıtımsız konak `wary/no`, liman işi bitince `yes`; başka tohumda başka yoldan.
5. **Eski kayıt**: `world_links_v1` olmayan kayıt yüklenir, tick sonrası bağ var, hata yok.

## 3. Sıralı işler

1. `world_links.py`: durum, `ensure`, `validate`, `tick(fire_due)`, 4 tür için türetme (`derive_links` yalnız mevcut ip/yer/kişiden). Yarım gün.
2. `trouble` ipine `fires_at` ve 3 genel sonuç; sonuç `bold_acts` deed + `world_reactions.NEWS["happening"]`. `town_threads.json`'a `job_lines.trouble` ve `links` satırları. Yarım gün.
3. `rumour_catalog.py`: `town_rumors.json` okuma, slot bağlama, ipe/bağa eşleme, `public_knowledge`'a 1 madde. `truth` modele gitmez. Yarım gün.
4. Mektup `donus`: `letter_text` bağ varsa B `owner_line`; okuma → `mark_heard`. 2 saat.
5. `read_proposal`'a `warn`; `npc_statements` tehdit sözü → `vade`. 2 saat.
6. "Canlı kanca" değişmezi `tick` sonunda + `speech_note`'a bekleyen satırı. 2 saat.
7. `mapping.json` `vouch_from` + `owner_mood` ek şartı; `street_talk` dışlaması. 2 saat.
8. Testler (§2.5), eski kayıt yükleme. Yarım gün.
9. 40 tur ölçüm: Carius ile; sahip okur. "Şimdi ne olacak?" ölçütü: merak uyandıran her şeyin bir sonucu var mı (final2'deki 4 sönme = 0 hedef).

## 4. Kesilecekler

- `incidents/emergence` bu işe girmez; kapalı kalır.
- Yeni ip türü, yeni NPC rolü, yeni yer türü yok; 9 yerleşik + katalog kalıbı yeter.
- Bağ türü 4'ten fazla değil; "ittifak", "hainlik", "aşk" gibi türler modelin değil oyuncunun seçiminden doğsun.
- `ambient_events` bağlara bağlanmaz (süs kalır).
- Söylentide `yanlis/yari` için karşı-olgu yoksa kayıt kullanılmaz (paket kuralı); 80'in belki 30'u bağlanır, yeter.
- Mektup metnini model yazmaz, konak/karakol "boss" kapısı yok, tek karakterlik senaryo yok.

## 5. Koda karşı doğrulanan itirazlar (2026-11-01)

Her madde `AI-DND-c-merge/ai-dnd` @ `01ac28d` üzerinde yeniden okundu. Koddan doğrulanamayan maddeler listeye alınmadı (bkz. sonda "Düşen maddeler"). Simülasyon sayıları (300 tohum) yeniden koşulmadı; yalnız yapısal nedeni koddan doğrulanan yerlerde anılıyor.

### 5.1 `karsi` bağı çoğu kampanyada doğamaz
- `world_threads.py:125` `_can_be_done`: `target_place_kinds` taşıyan `hiring` şablonu **hiç açılmıyor**. `town_threads.json`'daki 3 `hiring` da, katalogdaki 19 `hiring` da hedefsiz. §2 tablosundaki "A `errand/hiring` hedef yeri == B `trouble` yeri" koşulunu yalnız `errand` (2 yerleşik + 20 katalog) sağlayabilir.
- `world_threads.py:203` `_reserve_resident`: bir yerin **tek** sakini var. "Aynı yer farklı sahip" alt koşulu ve §2.2'deki "aynı yerde başka gerçek kişiyi suçla" hiç gerçekleşemez.
- `_replenish` (`:1452`) `MIN_OPEN = 2` (`:40`) public ipe ulaşınca durur; açılışta `trouble` olmayan kampanya olağan.
- Sonuç: bağ türetme "yer çakışması"na dayanamaz; derive kuralı değişmeli (bkz. §6 iş 5).

### 5.2 `vade` oyuncudan bağımsız bir takvimdir
- `JOBS = ("hiring", "errand")` (`:1100`); `jobs_of` (`:1119`) ve `promise_note` (`town_knowledge.py:320`) yalnız `JOBS`'u listeler. `town_threads.json:640`: `"trouble": "Bu bir dert, iş değil: kimseye para ya da ücret teklif etme."` **Oyuncunun bir derdi üstlenme yolu yok.** Plan "oyuncu bunu nasıl durdurur" demiyor; §2.5 test 2'nin "A koşusunda `vade` ateşlenmez" varsayımının arkasında kural yok.
- Katalogdaki 19 `trouble`ın `offer_hours` penceresi sabit `[8,8]…[20,20]`; yerleşik 4'ü `[24,72]…[48,120]`. `fires_at = opened_at + 6…36h` bu 19'da çoğu kez ipin `expires_at`'inden sonra düşer: ip `expired`/`filled_by_other` ile kapanır, `gone_lines` "{place} işini {who} kapmış" der (`town_knowledge.py:110`), tehdit sessizce söner. T70 sönmesi yeniden üretilir.
- `owner_of` (`world_threads.py:411`) o yerin NPC'si doğana kadar `None`; `karsi` sonucunun "B sahibine −1" yazısı sessizce kaybolur. `trouble` ipi `offered_at` taşımaz; `arrival_line` (`:546`, `:607`) ve `recent_closed` (`:1116`) yalnız `offered_at` olanları gösterir.

### 5.3 `warn` çalışamaz, T70 vakası kapanmaz
- Model `trouble` kimliklerini görmüyor (`promise_note` → `jobs_of` → `JOBS`). `read_proposal`'a (`town_knowledge.py:425`, `_PROPOSAL_KINDS :422`) `warn` eklemek yetmez; önce `promise_note` `trouble`ı listelemeli.
- `npc_statements.commit` yalnız `give/escort/show/meet/help` dalında (`town_knowledge.py:490`). Tehdit cümlesi bu yoldan geçmiyor.
- T70'teki cümle ("mührü kırık mektubu kimin açtığını görürlerse…") koşullu ve "onlar" kayıtta yok; `warn` listeden `thread_id` alsa bile doğaçlama tehdit yine bağlanamaz. Her `trouble` açılışta `fires_at` alıyorsa `warn` zaten gereksiz.

### 5.4 `happening`i `deeds`'e yazmak mevcut oyunu bozar (en acil)
- `bold_acts.speech_note` (`bold_acts.py:251`): `witnesses` için "Karşındaki kişinin şunları yaptığını kendi gözünle gördün" (`:267`); `heard` için **yalnız son kayıt** (`:273`); silahlı NPC'ye "bunu söyleyen biri görürsen üstüne gidersin" (`:275`). Dükkân kapanması `deeds`'e girerse muhafız oyuncuya saldırır, yeni olay oyuncunun cinayet haberini bastırır.
- `MAX_DEEDS = 24` (`:16`, `:77`) ortak; sık olaylar oyuncunun suçlarını defterden kovar.
- Çözüm: olaylar ayrı defter (`world_threads_v1.happenings`), `speech_note`'a ayrı ve etiketli cümle.

### 5.5 Ayrı `world_links_v1` anahtarı gereksiz risk
- `tick` (`world_threads.py:1470`) yalnız `world_threads_v1`'i bütün tutuyor (deepcopy + hata halinde geri al). Ayrı anahtar yarım kalır, `fire_due` çift yazabilir.
- `dialogue_jobs._KEPT` (`adventure/dialogue_jobs.py:17`) ve `game.py:2451` doğrulaması yalnız `world_threads_v1`'i tanıyor.
- `fires_at` hem bağda hem ipte: tek kaynak ipte olmalı. Bağlar `world_threads_v1` içinde tutulursa üçü de bedavaya çözülür.

### 5.6 Saat sırası ve değişmez
- `campaign_time.py:147-150`: `world_threads.tick(world, old + actual)` **saat yazılmadan önce** çağrılıyor; `_open_thread` ise `now = _now(world)` (`world_threads.py:292`) ile eski saati okuyor. Uzun tek `tick`te yeni ipler geçmiş `opened_at`/`expires_at` ile doğar; `fires_at` doğarken geçmiş olabilir. §2.1 formülü `min(...) − now ≤ 24h` negatif değeri de "canlı" sayar.
- §2.1 değişmezi mantıken tutmuyor: yeni ip `open` doğar, `heard` değil; koşul düzelmez, her `tick` yeni ip ister; ilk turda duyulmuş şey yok, test 3 baştan düşer; `_replenish` 2 public ipte durur.

### 5.7 Model saat söyleyemez ama istem saat taşıyor
- §2.1 "{kalan} saat" istem içine giriyor; onarım yalnız para için var (`without_unbacked_money`). `final2` #14'te bulut modeli bile 39 bakırı 24 dedi. Kalan süre modele **sayı** olarak verilmemeli; Python kaba sözcük verir ("bu akşam", "yarın"), ya da satırı Python doğrudan oyuncuya basar.

### 5.8 "Duydu" kaydı ve söylenti
- `note_mention` (`town_knowledge.py:598`): `item in hits or item["location_id"] in spoken` (`:612`). Yer adı geçti mi o yerdeki **bütün** kalemler duyulmuş sayılır; söylenmemiş yanlış söylenti de "duyuldu" olur. "Hangisine inandığın" için kayıt yok.
- Suçlanan kişinin kendi söylentisini listede görmesini engelleyen kural yok (`public_knowledge :88`): model "ben yaptım" diye seslendirebilir.
- `public_knowledge` tavanı 5 madde / 600 bayt (`:32-33`), sıra ipler → haberler → yerler (`:116`); `speech_note` için ayrı tavan yok. Yeni kalemler öne girerse yer ipuçları düşer, arkaya girerse kendileri düşer. `fallback_line` (`:543`) söylenti türünü ayırmıyor.

### 5.9 Söylenti paketi plana uymuyor
- `town_rumors.json` repoda yok; yalnız `AI-DND-JARVIS-310-KALIP-20261031/`. 80 kayıt var, şema: `rumor_template {yer}/{kişi}`, `truth_status`, `truth_condition_private` (düz yazı, Python değerlendiremez), `location_types`, `speaker_role`. `turn` alanı yok. Örnek içerik `RUM001` "ekmeğe susam serpiyormuş": iplerle ilgisi yok. Paketin kendi `binding_rules`'u görev/hedef/ödül/zamanlayıcı başlatmayı yasaklıyor, kişi için "doğrulanmış kamu adı" istiyor; plan `resident_name` diyor.
- §3 iş 3 "yarım gün veri çevirisi" değil, yeni içerik yazımıdır. Söylenti ipin **kendi** kaydından türetilmeli.

### 5.10 Tekrar ve ölçüm
- İskelet tek: `trouble` açılır → 6–36 saat → 3 genel sonuçtan biri → bir satır. Bağ sonucu yeni ip ya da bağ açmıyor, sonuçlar birikmiyor. Sahibin ilk şikâyeti "tekrar".
- `job_lines.errand.letters` 6 kalıp; 7. mektup bire bir tekrar.
- "Her an 24 saat içinde bir saat" sabit tik tak üretir; sahip "ne boş bekleme ne her tur kriz" diyor.
- §2.5 yalnız aynı tohumda ayrışmayı ölçüyor; tohumlar arası iskelet karşılaştırması yok (`test_world_threads.py` `shape()` başlangıç olabilir).

### 5.11 Konak kapısı
- §4 "boss kapısı yok" derken §2.3 `owner_mood == "no"` ile kapı kuruyor. `owner_mood` (`world_threads.py:1012`) bugün `no`yu yalnız ilişki ≤ −1 ve son iş `failed/abandoned` için veriyor; `wary` `WARY_PERCENT = 20` tohumla. Açılma koşulu sessiz bir sayı olur, oyuncu nedenini göremez. (c) yolu model kararı ister. Çözüm: `wary` + sözlü tanıtım, `no` kullanılmaz.

### 5.12 Eski kampanya ve zaman
- Kabul edilmiş eski işe geriye dönük bağ bağlanırsa konuşulan şartlar sonradan değişir; bağlanmazsa test 5 boş geçer. Karar: **bağlanmaz**, yalnız yeni açılan iplere.
- Replay/geri alma büyük risk değil (`game.py:2195` tüm dünyayı kopyalıyor, `action_id` makbuzu var); ama §2.4'teki "serializer allowlist" `deeds` için yok, gerekçe düzeltildi.
- `final2` #12: yolculuk zaman harcamıyor (kod üzerinden doğrulanmadı, oyun kaydından). Ölçüm (§6 iş 11) önce buna bakmalı; "5 saat" sözü 30 tur boyunca 5 saat kalırsa `vade` anlamsız.

### Düşen maddeler
- Bütçe: +120 token 8192 içinde, `public_line`'lar 90 bayta sığıyor. İtiraz yok.
- Replay/geri alma: risk değil (yukarıda).
- "`background_labels` 'Not used yet'" ve "152 konaklı tohumun 6'sında tanıtımcı tür yok": kodda yeniden doğrulanmadı, §5.11 bunlara dayanmıyor.

## 6. Tek uygulayıcı için iş listesi (§3'ün yerine)

Sıra bağlayıcı; her iş kendi testiyle kapanır, sonrakine geçmeden `python -m pytest api/tests -q` yeşil. Yeni model çağrısı yok. Hiçbir sahip örneği metni kopyalanmaz.

1. **Saat sırasını düzelt.** `campaign_time.py:147-150`: `clock["elapsed_seconds"] = old + actual` satırını `world_threads.tick` ve `bold_acts.on_time` çağrılarının **önüne** al; `_open_thread` `now`'ı parametre olarak alsın (`_replenish(world, work, now)` zaten taşıyor). Test: tek 7 günlük `tick` sonrası her yeni ipte `opened_at == now` ve `expires_at > now`.
2. **Olay defteri.** `world_threads_v1`'e `"happenings": []` (tavan 16, `validate` kabul eder, `ensure` tembel ekler). Kayıt: `{thread_id, kind: "visit|closed|lost|averted", at, place_id, line ≤ 90 bayt, known_to_player: bool, next_thread_id: str|null}`. `deeds`'e **yazılmaz**. `bold_acts.speech_note`'a dokunulmaz; `town_knowledge.speech_note`'a ayrı, etiketli tek cümle ("Duyduğun: {line}"), yalnız NPC'nin yeri ya da komşu yer için. `_KEPT` ve `game.py:2451` değişmez (aynı anahtar).
3. **`trouble`a vade ve sonuç.** `_open_thread`: `type == "trouble"` ise `fires_at = opened_at + h`, `h` tohumdan, `expires_at`'i **`fires_at`'e hizala** (ip ateşlenmeden `expired` olmaz; katalogdaki sabit `[8,8]…[20,20]` pencereler `fires_at` aralığı olarak yeniden okunur). `_close_due` içinde `fire_due`: `now ≥ fires_at` ve ip kapanmamışsa `happenings`'e yaz, ipi `fired` statüsüyle `history`'ye taşı. `town_threads.json`'a `job_lines.trouble.fired_lines` (3 genel sonuç, slotlu) ve `gone_lines.fired`. `transition` tablosuna `fired`. `fires_at` `_OPTIONAL_INTS`'e. Test: `trouble` açılır, `tick(fires_at)` sonrası `happenings` 1, `deeds` değişmedi, `history[-1].status == "fired"`.
4. **Dert üstlenilebilir.** `JOBS`'a `trouble` ekle **ama** `pay=None` kalsın; `town_threads.json:640` satırı korunur (para teklifi yok). `jobs_of`/`promise_note` `trouble`ı listeler, `owner_mood` için ayrı dal yok. Oyuncu `accepted` yaparsa `fires_at` silinir (ip artık oyuncunun elinde), `done` olursa `happenings`'e `kind: "averted"` yazılır; `abandoned`/`expired` olursa `fires_at = now + 6h` ile ateş yeniden kurulur. Bu, §5.2'nin "oyuncu nasıl durdurur" cevabıdır. Test: aynı tohum, A kabul+bitir → `averted`; B hiç konuşmaz → `visit|closed|lost`. `history` statüleri farklı.
5. **Zincir (tek kural, bağ kaydı yok).** `fire_due` bir `trouble`ı ateşlerken aynı yerleşimde **yeni bir ip** açar: `happenings[-1].kind` → şablon seçimi (`closed` → o yerde `hiring` 2 gün yasak, `lost` → komşu yerde `errand` öncelikli, `visit` → aynı yerde `trouble` ama farklı şablon). `linked=True` ile aynı yer tercih edilir. Zincir `happenings[i].next_thread_id` ile izlenir; `karsi/donus/vade/kanit` türleri ve `world_links_v1` **yok**. Test: ateşlenme sonrası `state["threads"]`'te `opened_at == fires_at` olan yeni ip var, `template_id` öncekinden farklı.
6. **Mektup = olgu.** `dialogue_jobs.letter_text`: `errand` ipinin hedef yerinde açık bir `trouble` varsa `{target}` yerine o ipin `owner_line`'ı (≤ 90 bayt kontrolü, sığmazsa eski satır). Mektup okunduğunda `world_threads.mark_heard(trouble)`. 6 kalıp 12'ye çıkarılır (sahip metni değil, slotlu). Test: açık mektup → `trouble.heard_turn` dolu.
7. **Söylentiyi ipten türet.** `town_rumors.json` **kullanılmaz**. `public_knowledge`'a yeni kalem türü `"rumour"`: açık bir `trouble` için `truth ∈ {dogru, yanlis}` tohumla; `dogru` → `public_line`; `yanlis` → `catalog.rumour_lines` içinden yer doğru, **kişi yok** ("{place} tarafında bir şey dönüyormuş" tipi; kimse suçlanmaz, böylece tek sakin duvarına ve "ben yaptım" riskine çarpmaz). İp sahibinin kendi NPC'si `yanlis` söylentiyi görmez. `note_mention`: `rumour` kalemi yalnız `hits` ile `heard` olur, `spoken` yer adıyla **olmaz**. `fallback_line` `rumour`ı atlar. Tavan: `rumour` sıraya **haberlerden sonra, yerlerden önce** girer; 5/600 değişmez. Test: `yanlis` söylentide `resident_name` geçmez; yer adı tek başına `heard` yapmaz.
8. **`speech_note` bekleyen satırı, sayısız.** NPC'nin kendi yerinde `fires_at` taşıyan ip varsa tek cümle: " Seni bekleyen: {public_line}; {vakit}." `{vakit}` Python'dan **sözcük** (`bugün`, `bu gece`, `yarın`, `birkaç gün`), sayı değil. `warn` önerisi **eklenmez**; `read_proposal` değişmez.
9. **Konak/karakol `wary` ile tanıtım.** `mapping.json`'a `vouch_from`. `owner_mood`: yer türü `estate/barracks` ve `vouch_from` türlerinden hiçbirinde `relationships.score ≥ 1` yoksa **`wary`** döner, `no` değil; `shared.wary_stranger` yanına `shared.wary_vouch` satırı ("{yer}'den biri senin adına söylerse…", slotlu) `town_knowledge.py:244` dalına. `street_talk` dışlaması yok (duyulsun, kapı sözlü). Test: tanıtımsız `wary`, liman işi `done` sonrası `yes`; iki tohumda `vouch_from` seçimi farklı.
10. **Testler.** `api/tests/test_story_links.py`: (a) determinizm, (b) ayrışma (iş 4), (c) tohumlar arası iskelet: 20 tohum × 30 tur sahte model, `shape()` benzeri `(template_id dizisi, happenings.kind dizisi, next_thread_id zinciri)`; en az 15 farklı iskelet, (d) eski kayıt: `happenings` olmayan `world_threads_v1` yüklenir, `ensure` ekler, `validate` geçer, eski `accepted` ipe `fires_at` **eklenmez**, (e) `deeds` hiçbir testte `happening` içermez.
11. **Ölçüm (sahip okur).** 40 tur Carius. Önce `final2` #12: yolculuk/bekleme saati gerçekten akıyor mu; akmıyorsa `vade` ölçülmez, önce o düzeltilir (ayrı iş). Sonra: duyulan her `trouble` için 40 tur içinde `fired|averted` ≥ 1, `deeds`'e sızan olay = 0, modelin söylediği saat sayısı = 0.

Kesilenler (§4'e ek): `world_links_v1` anahtarı, `karsi/donus/vade/kanit` dört tür, `warn` önerisi, `town_rumors.json`, `kanit` koşul değerlendirmesi, §2.1 "her an 24 saat" değişmezi (yerine: duyulan her `trouble`ın bir sonucu var).
