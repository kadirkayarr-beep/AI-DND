# Bounded production Monster Combat integration

## Death System + Save Management ownership

The selected policy is **2024 default monster death (Policy A)**. New resolved
lethal damage reaches `game.apply_npc_damage` from Weapon & Attack and Inner
Radiance. Zero HP means dead, not a monster death save or generic Stable recovery.
Damage math, verified survival reductions, initiative and combat closure remain
with their existing owners. No unsupported Monster Manual survival ability is
inferred. Historical zero-HP unconscious NPCs are preserved on load; their
incapacitated slots cannot act and no longer stall the scheduler.

Player transitions remain in the existing game Death owner. Real healing clears
zero-HP counters and pending recovery without resurrection. The bounded NPC
Medicine Help helper uses the existing skill resolver/action resource owner and
requires canonical supported healer data: **SUPPORTED MECHANIC / CURRENTLY
UNREACHABLE WITHOUT A LEGITIMATE EXTERNAL ACTOR.** Death owns the mechanic, not
creation of allied-NPC control, companion actions or autonomous rescue behavior.
Production reachability is not a Death completion blocker when no legitimate
conscious actor/action entry point exists. A future legitimate party/allied-NPC
action owner may invoke this primitive through existing receipts; no such route
or receipt-replay certification is fabricated here.

Stable recovery rolls one session-RNG d4 and persists an elapsed-time deadline.
`advance_campaign_time` consumes it through the existing clock/event pipeline,
including interruptions. Noncombat unconscious progression uses the same death-save
resolver, with episode-qualified six-second boundaries; no new scheduler exists.
Load/replay never rolls or advances time. Passive waiting is an explicit player
decision, not a conscious character action. Unconscious time consumption cannot
observe unknown events.

Normal uses the existing pre-initiative checkpoint; gameplay rollback preserves
consumed RNG/receipts while restoring captured world/time/inventory/campaign
metadata. Missing checkpoint retains the existing dead fallback. Permadeath ends
the character (`terminal=False`); Ironman sets campaign `terminal=True`. None
deletes saves. API persistence failure restores the request snapshot including RNG.

Explicit campaign deletion belongs to CampaignStore's existing SQLite transaction
and FK cascades. SessionManager serializes it with the active turn, revokes the
campaign session only after successful deletion, and checks persisted existence.
DELETE by stable campaign ID is idempotent, with absent IDs returning `deleted:
false`. Stale sessions cannot recreate a row. The campaign library requires
destructive confirmation and removes its card only after authoritative success.
Deletion and Death mechanics do not depend on a model.

The older dated evidence below remains evidence of its original execution, not a
retroactive certification of these changes. New focused runs are retained by the
existing regression evidence runner.

## Sonuç — 2026-10-04

**COMPLETE — yalnızca tek opt-in avlu senaryosu için.** Genel dünya
perception/pathfinding kaynaklarının tamamlandığı veya uygulamanın
yayınlandığı iddia edilmez.

Başlangıç checkout: `main`, `cde1da397a47c62d644747892790393b682363d8`;
tracked çalışma ağacı temizdi, kullanıcı eki untracked idi. Agent
commit/push/merge/publish/reset/rebase/force-push komutu çalıştırmadı.
Devam sırasında HEAD `6d695680114d840df50214c6dc613814c0fc54b5`
olarak gözlendi; bu bir agent commit komutunun sonucu değildir.

## Üretim sahibi ve oyuncu seçimi

`bounded_encounter.py` bir olasılık tanımlar; mevcut campaign'lere otomatik
NPC veya combat eklemez. Normal başlangıç kataloğundan canonical konum
seçilmiş bir campaign'de:

1. **Avlu karşılaşmasına gir**: mevcut NPC factory ile yeni, ID-bound NPC
   oluşturur. Combat başlamaz.
2. **Avlu çatışmasını başlat**: oyuncu tercihiyle mevcut initiative ve combat
   scheduler çalışır.
3. Normal structured `end_turn` isteği: #07, mevcut algı/rota ve kaynak
   sahiplerinden legal hareket/saldırı seçer.

Tek binding, mevcut world state içinde scenario/version/location/NPC/statblock
kimliklerini tutar. Mutable konumlar mevcut `npc.position` ve scene player
position sahibindedir. Ayrı persistence, receipt veya RNG sistemi yoktur.
Tekrar entry NPC'yi iyileştirmez, respawn etmez veya kaynakları yenilemez.
İsim/role benzerliğinden eski NPC'ye statblok bağlanmaz.

## MM kaynağı

Yüklenmiş MM 2024-rules Commoner sayfası görsel olarak doğrulandı:
basılı **77**, PDF **80**. `mm2024.commoner` açık ID ile bağlanır.

- AC 10; HP 4 (1d8); Speed 30 ft; initiative +0.
- Altı ability 10, modifier 0; passive Perception 10; Common.
- Club: melee +2, reach 5 ft, 1d4 bludgeoning.
- Multiattack, limited-use/recharge, resistance/immunity yok.
- Training için History seçildi; trait kayıtlıdır. Bu senaryoda beceri
  kontrolü yürütülmez; Training'in skill-check mekanikleri için native
  execution iddiası yapılmaz.

NPC instansı Medium seçilir. Club'ın doğrulanmış toplam +2 attack bonusu
mevcut attack owner'a verilir; ikinci bir proficiency bonusu eklenmez.

## Algı ve rota

Üç authored anchor: entry, far, near. Başlangıç mesafesi 60 ft, yakın
anchor 5 ft; far→near yürüyüşü 55 ft. Bunlar **senaryo tasarım verileridir**,
MM'den alınan coğrafya veya anlatımdan çıkarılmış canonical lore değildir.

Yönlü çiftler ayrı kayıtlarla tanımlanır. Blinded/invisible/hidden mevcut
condition sahiplerinden okunur; özel sense üretilmez. #07 snapshot öncesi,
rota çözümü sonrası ve normal turn girişinde scoped refresh yapılır.
Konum veya node bilinmiyorsa eski pair/perception/route ve legacy feet
fallback'i kaldırılır. Başlangıç anchor'ına otomatik geri dönüş yoktur.
Budget-only hareket, onaylı endpoint olmadığı için bounded node'u geçersiz
kılar. Eksik hostile route evidence için mevcut #04 rejection korunur.

## Gerçek HTTP kanıtı

Kanıt: [evidence/bounded-encounter-http.json](evidence/bounded-encounter-http.json).
Tekrar çalıştırılabilir kontrol: `scripts/verify_bounded_encounter_http.py`.
Girdi yalnız normal campaign start, oyuncu komutları ve combat context içerir;
request'ten statblock, perception, route, zar veya sonuç verilmez.

Canlı development proxy → mevcut 8008 servisi → normal production factory:
creation → entry → start → native Dash → native Club attack → save.
Mevcut **ayrı 8000 süreci**, aynı persistence sahibinden resume ve replay yaptı.
Bu yayınlanmış production deployment testi değildir.

Gözlenen sonuç:

- `npc_001` → `mm2024.commoner`, source printed p.77/PDF p.80.
- #07 Dash: 55 ft hareket, 60→5 ft; action spent; dash_count 1;
  movement_used 55, available 60.
- Sonraki enemy turn: hedef player; Club +2; gerçek d20 **20**, total **22**;
  critical 2d4 **[1,1]**, 2 bludgeoning; player HP **12→10**.
- Save/resume public state eşit; replay response, state ve history değişmedi.
- Restart/resume testleri ayrıca tam serialized canonical state ve
  `rng.getstate()` eşitliğini doğruladı. Replay ikinci RNG/resource/turn
  tüketmedi; stale combat context'ten önce receipt döndü.
- Canlı workflow'daki üç yeni gameplay turn logunun her biri
  `model_calls=0` bildirdi.

Disposable campaign inceleme için bırakıldı:
`12109bb2-97d1-4de8-96a1-a96739b32908`. Mevcut kullanıcı campaign'leri
seçilmedi, değiştirilmedi veya silinmedi.

## Testler — exact counts

| Kategori | Sonuç |
|---|---|
| Önceki unique backend baseline | 480/480 PASS |
| Yeni production-owner integration | 8/8 PASS |
| Yeni mechanical uncertainty/negative owner | 4/4 PASS |
| Yeni normal HTTP attack/resource acceptance | 1/1 PASS |
| Yeni save/resume + canonical state/RNG | 1/1 PASS |
| Yeni restart sonrası receipt replay | 1/1 PASS |
| Yeni action-ID conflict + unrelated model-service guards | 2/2 PASS |
| Ek API/campaign contract regresyonu | 56/56 PASS |

Ana unique suite **497/497**, failures/errors/skips **0/0/0**.
Ek contract suite **56/56**, toplam **553/553**.
Baseline içindeki **26/26 hardening** PASS; toplamda tekrar sayılmadı.
Limited resources across combat IDs, Multiattack component legality,
hostile route evidence ve Frightened modifier davranışları korundu.

Ek contract suite ilk çalıştırmada 55/56 geçti. Başlangıç checkout'unun
ilgili üretim modülleri /tmp altında salt okunur Git içeriğinden kurularak
aynı `distance_unknown` hatası doğrulandı. Eski serializer fixture'ına
yalnız `distance_ft: 5` eklendi; üretim range validation gevşetilmedi.
Bu fake attack sonucu/mesafe **fixture evidence**'dır; native kanıt değildir.

Python compilation ve `git diff --check` PASS. İki mevcut FastAPI workflow
bir kez restart edildi, temiz startup ve gerçek HTTP 200 yanıtları görüldü.
Campaign Browser screenshot'ı düzgün açıldı; browser console error yoktu.
Ekran görüntüsü combat etkileşim testi olarak sayılmadı.

## Fixture evidence sınırı

480 eski test ve ek 56 contract testi mekanik/HTTP sözleşmelerini kanıtlar;
test executor, statblock, geometry veya RNG fixture'ları native üretim
kapsamı olarak sayılmaz. Yeni dört uncertainty testi mevcut canonical
state'i kasıtlı geçersizleştirir; replacement geometry sağlamaz.
Native kanıt, yalnız production-owner testleri ve gerçek HTTP zinciridir.

## Scope ve açıklanmış ek kararlar

Promptun boş bıraktığı başlangıç konumu canonical katalogdan normal API
ile seçildi; unresolved campaign'e konum uydurulmaz.
Native, tamamen Python-owned komutlar Qwen health preflight'ına bağlı
olmaktan çıkarıldı. Konfigüre adapter varsa mevcut call/failure capture
korunur; serbest metin eski model gereksinimini sürdürür. Model kurulmadı.
Combat start sonucu mevcut Action Economy result biçiminde serialize edilir;
yeni schema/codegen sistemi yoktur.

Full MM ingestion, full perception/tactical geometry/pathfinding, quest,
#08, Death redesign, broad UI redesign, yeni dependency/persistence/RNG/
receipt architecture yapılmadı. Tek NPC, tek authored rota ve tek bounded
senaryo tamamlandı. Serbest hareket için endpoint veya desteklenmeyen
Training skill check üretilmez.

## Dar hareket düzeltmesi — 2026-10-04

Son salt-okunur inceleme, Ready hareketi ve Cloud Jaunt sonrasında eski
bounded anchor'ın korunabildiğini buldu. Kullanıcının dar kapsam onayıyla,
bu iki başarılı hareket sahibi mevcut bounded konum geçersizleştirmesine
bağlandı. Endpoint, mesafe, görünürlük veya rota uydurulmaz; başarısız
işlemler konumu geçersizleştirmez. Action/Reaction/Bonus Action ve yetenek
kullanımı kuralları değiştirilmedi.

Tarihsel raporda unique regresyon koşusu **563/563 PASS**, failures/errors/skips
**0/0/0** olarak belirtilmişti: yukarıdaki 553 test ve 10 yeni hareket
regresyonu. Yalnız `/tmp/bounded-movement-fix-regression.log` referansı ve
tekilleştirme beyanı korunmuş; onaylı kalıcı artifact'lerden bu koşu bağımsız
doğrulanamıyor. Bu nedenle sonuç **HISTORICAL RUN UNVERIFIED** olarak kalır.
Yeni koşular bu eksik tarihsel koşuyu sertifikalandıramaz. Gelecek koşuların
kalıcı kanıt sözleşmesi: [regression-evidence.md](regression-evidence.md).
Yeni kontroller normal HTTP Ready/react, structured Cloud Jaunt ve combat
dışı species endpoint'ini; fresh manager/app ile save/resume, canonical
state/RNG ve receipt replay'i kapsar. Negatif kontroller yalnız başarısızlık
ve rollback koşullarını sınar; replacement geometry sağlamaz. Bounded
binding bulunmayan campaign'de Cloud Jaunt world/RNG'yi değiştirmez.
Bu koşu yeni bir canlı ağ veya ayrı-process kabul çalışması değildir.

## Gerekli follow-up

İki hareket/geometri bulgusu düzeltildi ve regresyonları geçti. Ancak önceki
incelemenin commit oluşturma mekanizmasına ilişkin **PROVENANCE UNRESOLVED**
sonucu bu kod düzeltmesiyle çözülmüş değildir. Bu belge tek başına manuel
push için GO vermez. Genel MM veya navigation/perception kapsamı ve #08
bu değişikliklere dahil değildir.