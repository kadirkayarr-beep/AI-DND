# Defter + yaşayan dünya: uygulama planı (2026-10-31)

Durum: plan. Kod yazılmadı, test ve model koşulmadı. Okunan dal `task/c-series-merge` @ `32035e3`, yollar `ai-dnd/` altında, satırlar o commit'e göredir (dal canlı düzenleniyor, kaymış olabilir). Girdi: `OYUN_TARIFI_KADIR`, `DEFTER_TASARIM`, `LIVING_WORLD_MAP`, Jarvis `02_YASAYAN_DUNYA_TASARIM_TR`. Örnekler burada da örnektir; sabit içerik olmaz.

## 0. Tek cümle

İki iş tek omurgada birleşir: **turda en fazla bir "boş yuva" çağrısı** (`incidents/arbiter.decide`), **tolere edilen faz** (başarısızlık turu geri almaz), **oyuncunun gördüğü veriden üretilen salt okunur paket**. A defteri ve özeti bu omurgayla anlatıcıya taşır; B ajandayı aynı omurgayla saatle yürütür ve sonucunu yine defter üzerinden gösterir.

## 1. Koddan doğrulanan gerçekler

| Gerçek | Yer |
|---|---|
| Anlatım belleğe `[presentation omitted]` olarak girer; özet yok | `api/narrative_memory.py:378-402` |
| Paket 4800 bayta sığdırılır; atılma sırası fingerprint, style, story_summary, location, npc_interactions, threads, recent_turns | `:789-812` |
| Sığdırma yalnız continuity'ye uygulanır; canonical context kırpılmadan gider | `api/narrative_director.py:131-136` |
| `recent_dm_narrations` casefold edilmiş 8 anlatım; prompta 240 karakterle, "olgusal dayanak değil" etiketiyle | `game.py:12903-12970`, `:13903-13905` |
| NPC sözleri zaten tutuluyor: `npc.memory` (16), `npc_statements` (40/NPC), `npc_speech_log` | `game.py:6614-6668`, `dialogue_runtime.py:197` |
| Çağrı tavanı 2, üçüncüsü `RuntimeError` | `api/ollama_adapter.py:26,205-208` |
| `resolved_narration` dışı her model hatası 503 + geri alma | `api/main.py:1437-1448`, `api/model_phase.py` |
| Saat ilerlemesi tek kapıdan: `campaign_time.advance` → `process_events` → `close_due` | `campaign_time.py:118-149` |
| free_v1 konuşma turu `_dispatch_player_turn`'de erken döner, `interaction_adventure.resolve`'a ulaşmaz | `game.py:17057-17065` |
| free_v1 işleri gerçek: teslimat/soruşturma, paket, ödül, `DISCOVERED` → günlükten kabul | `adventure/dialogue_jobs.py:33-75`, `dialogue_commitments.py:59-61` |
| Teklif süresi: `deadlines.arm` 3600 sn, `close_due` → `FAILED(missed)` | `adventure/deadlines.py`, `adventure/play.py:98-108` |
| `refuse`/`abandon` açık sözleri "broken" yapar; `offered` için de | `interaction_adventure.py:1269-1274` |
| `record_witness` üretimde çağrılmıyor; `PerspectiveEntry.kind` rumor/belief/lie yazıcısız | `interaction_adventure.py:609-627` |
| `relationships.note` aynı gerekçeyle idempotent; 24 kayıt tamponu | `relationships.py:50-64` |
| Günlük `record.journal` üzerinde, dünyada değil; anlatıcı onu görmüyor | `api/main.py:1588-1598` |
| `serialize_session_state` çıktısı allowlist; yeni dünya anahtarı istemciye sızmaz | `api/serializers.py:795-847` |
| Kayıt doğrulaması anahtar varsa çalışır (ör. `relationships`) | `game.py:2362-2380` |
| Anlatıcı sızıntılarının üçü kapanmış: profil allowlist (`current_activity`,`mood`), bilinmeyen rolde `personality/tags/shop_id` atılır, kilit yalnız biliniyorsa | `game.py:6979-6985`, `:7029-7032`, `:7132` |
| Konuşma modeli bağlamı (free_v1) perspektif ve ilişki içermiyor | `dialogue_runtime.py:76-112` |
| Varsayılan kampanya `legacy`: `AI_DND_DIALOGUE_MODE` yoksa free_v1 kapalı, rutinler kapalı | `api/session_manager.py:227`, `dialogue_runtime.py:34-38` |

## 2. Mevcut taslaklara itiraz

1. **"DM unutuyor" teşhisi eksik.** Unutulan şey *anlatım* ayrıntısıdır (yara izi, kapı rengi). NPC'nin söyledikleri zaten üç yerde tutuluyor. Özet işi yalnız anlatım sahnesini hedeflemeli; NPC sözleri için yeni kayıt açılmaz.
2. **Defter continuity'ye değil canonical'a eklenirse bütçeyi bozar.** Canonical kırpılmıyor (`narrative_director.py:131`). Defter ve özet `relevant_continuity` içine, atılma listesinin **sonuna** girer (en son kırpılan). Taslağın "anlatı bloklarından önce gelir" cümlesi bu anlamda doğru, "canonical'ın yanına" anlamında yanlış.
3. **Özet için model çağrısı ikinci bir "boş yuva" müşterisidir.** Taslak A bunu bağımsız düşünmüş; B'nin review çağrısıyla aynı yuvayı paylaşır. Tek politika gerekir (§3). Aksi hâlde üçüncü çağrı veya 503.
4. **Özet, API katmanında (`update_narrative_memory` sonrası) çağrılamaz.** O noktada `capture_model_calls`/`capture_model_failures` kapanmış olur (`api/main.py:1344-1380`): çağrı sayılmaz, hata faz etiketi almaz, istisna 500'e düşer. Çağrı `game._run_player_turn` kancasında, çerçeve (`NarrativeTurnContext`) üzerinden taşınır.
5. **`offer_decision` enum'u modele durum kararı verdirir.** Haritanın free_v1 önerisi "narration never decides state" kuralını deler. Kabul/ret oyuncunun **kendi metninden** Python'la bağlanır (`npc_statements._AGREE/_REFUSAL` var, `:83-87`), modele yalnız `player_decision` bağlamı verilir ki NPC sesiyle onaylasın. Belirsiz metin → teklif açık kalır, soru sorulmaz.
6. **`Thread.status`'a `refused` eklemek kayıt riskidir** (`extra="forbid"`, eski derleme yükleyemez). Ret durumu `npc_agenda_v1`'de tutulur; `interaction_adventure`'da tek değişiklik: `offered` iplikte ret söz bozmaz.
7. **Harita §4'ün üç "High" maddesi kapanmış** (tablo). Kalan: `interaction_perspective` `kind` filtresi (bu dilim `rumor` yazmaya başlıyor), `id`/`reality_layer` sözcükleri. "Anlatıcı düzeltmesi önce" görevi küçülür.
8. **Jarvis §6 arka plan katmanları ve §3'ün 11 kaydı** bu dilime girmez. Tek yerleşim, tek NPC planı, kaynak/rezervasyon yok. Belge bunu zaten erteliyor; burada açıkça kesiliyor.
9. **Mod kararı verilmemiş.** Dilim free_v1 işlerini hedefler (gerçek şartlar, ödül, paket). Legacy teklifleri beş sabit başlık ve ödülsüz (`interaction_adventure.py:1361-1367`); orada plan "boş teklif" olur. Öneri: oyun testi `AI_DND_DIALOGUE_MODE=free_v1` ile; legacy bağlama "kesilecekler"de.

## 3. Ortak omurga (iki işin paylaştığı parça)

**Boş yuva politikası** — yeni `spare_slot.py` (motor, ~80 satır):
- Çağrı noktası: `game.py:16934` (`observe_turn` sonrası, `_run_player_turn` içinde). Anlatım bitmiş, işlem içinde, replay'de yeniden çalışmaz.
- `arbiter.decide(calls_used=arbiter.calls_used(), narration_needed=False) == PROPOSE` değilse hiçbir şey yapılmaz. 2 çağrı kullanılmışsa DEFER; adaptör zaten üçüncüyü reddeder (`:207`), yine de `RuntimeError` yakalanır.
- Öncelik sabit: (1) ajanda review (`needs_review` ve son tarih henüz geçmemiş), (2) compact özet (vadesi gelmiş). Turda en fazla **bir**.
- Her iş: girdi kopya, çıktı doğrulanmış sözlük; geçersizse "hiçbir şey" döner. Dünyaya/belleğe yazma yalnız doğrulamadan sonra, tek atama.

**Tolere edilen fazlar** — `api/model_phase.py`: `resolved_narration_scope(enabled)` yerine `tolerated_scope(phase)`; `only_resolved_narration_failures` → `only_tolerated_failures`, kabul kümesi `{"resolved_narration","agenda_review","compact_summary"}`. `api/main.py:1437` tek satır çağrı adı değişir. Ollama hatası bu fazda loglanır, tur **durur ve commit olur**. Aynı yoldan `incidents/attempts.py:189`'daki gizli hata da düzelir (bonus, ayrı test).

**Bütçe (8192, ölçüm değil tahmin; kodun kendi ölçüsü bayt/2 = token):**

| Parça | Bayt tavanı | ~token | Ne zaman |
|---|---|---|---|
| Defter (`ledger`) | 900 | 450 | her anlatım turu |
| Compact özet seçkisi | 600 | 300 | her anlatım turu |
| `known_news` | 400 | 200 | haber turu |
| Prompt kural cümleleri | 240 | 120 | her tur |
| **Toplam ek** | **2140** | **~1070** | |

Mevcut ~5300 + 1070 + 700 çıktı ≈ 7070, rezerv ~1100. Ama paket 4800 baytta sabittir: defter/özet girdiğinde `story_summary`, `location_continuity` daha erken düşer; bu istenen takastır (defter onların yerine geçer). Yan çağrılar ayrı istem: review ≤ 1200 token girdi / 120 çıktı; özet ≤ 1500 girdi / 300 çıktı. İlk gerçek ölçüm T2 sonunda `narrative_context_bytes` logundan alınır; 7500'ü geçerse defter tavanı 600'e iner.

## 4. A — Motor defteri ve compact özet

### 4.1 Dosyalar ve alanlar

**`api/narrative_memory.py` şema 2** (`NARRATIVE_MEMORY_SCHEMA_VERSION = 2`):
- `pending_narrations: list` ≤ 6 × `{text ≤1200, player ≤280, turn_index, location_id, authority:"presentation"}` — özetlenmeyi bekleyen, oyuncuya gösterilmiş metin. `update_narrative_memory` her turda ekler (zaten `narration` alıyor, `:366`). Pakete **asla** ham girmez.
- `compact_summaries: list` ≤ 24 × `{text ≤160, about: npc_id|location_id|null, location_id, turn_from, turn_to, authority:"summary"}`.
- `compact_cursor: {turn_index, location_id}` — son özet anı.
- `migrate_narrative_memory(value)`: `schema_version 1` → 2, üç alan boş/null; `validate` yalnız 2 kabul eder. Çağrı yerleri: `api/session_manager.py:294, 467, 526` (yükleme) ve `update_narrative_memory` girişi. Geri alma noktası `undo_checkpoint` v1 anlık görüntü taşıyabilir → `undo_last_turn` (`main.py:1830`) de migrate eder.
- Paket: `relevant_continuity["compact_summaries"]` (seçki) ve `relevant_continuity["ledger"]`; `_fit_context_packet` reductions sonuna `("compact_summaries", [])`, `("ledger", {})` eklenir (en son düşer). `authority_boundary`'ye iki satır: `"ledger": "motor kaydı; çelişkide kazanır"`, `"summary": "DM'nin kendi önceki anlatımının özeti; sahne ayrıntısını tutarlı kullan; mekanik kanıt değil; kayıtla çelişirse kayıt geçerli"`.

**`campaign_ledger.py` (yeni, motor, ~150 satır)** — `project(world, journal) -> dict`, salt okunur, kopya tutmaz. Kaynaklar ve sıra (hepsi oyuncunun bildiği):
1. NPC'nin oyuncuya açık sözleri: `npc_statements.view(world)["commitments"]` status open/fulfilled/broken, `quote[:90]`.
2. İşler: `world["quests"]` yalnız `DISCOVERED/ACTIVE/COMPLETED/FAILED/ABANDONED` (`AVAILABLE` duyulmamış, girmez); başlık, durum, veren (public ad).
3. Ajanda: `npc_agenda.player_view(world)` — sunulmuş teklifler oyuncunun bildiği hâliyle, `known_news`.
4. Ölen/yenilen bilinen NPC'ler: journal `enemy_defeated`.
5. Bilinen kişiler: journal `known_npcs` (public ad, rol, son görüldüğü yer/tur), en yeni 8.
6. Gidilen yerler: journal `locations`, en yeni 6.
7. Oyuncu sözleri: `story_summary.player_history`.
8. Son bilinen olaylar: journal `events` (adventure_event, item_gained/lost), en yeni 6.
Tavan 900 bayt; satır ≤ 90 karakter; sıra sabit, deterministik. İlişki puanı **girmez** (NPC'nin içi); `interaction_adventure` gizli objective'ler girmez (`public()` zaten süzer).

**Günlük erişimi:** `NarrativeTurnContext`'e `journal` alanı; `narrative_turn_context(record.narrative_memory, msg, journal=record.journal)` (`api/main.py:1323`). `build_with_narrative_context` defteri burada üretir ve pakete koyar.

**Prompt metni** (`game.py:12923, 12970`): RECENT NARRATION etiketi "yalnızca tekrar etmeme için; olgusal dayanak değil" → "ifade tekrarı için değil; anlatılmış sahne ayrıntısını tutarlı kullan, mekanik kanıt sayma". Bir cümle eklenir: "KAYIT (ledger) ile özet çelişirse KAYIT geçerlidir." Yeni denetim yok (az engelleme).

### 4.2 Compact özet işi (`spare_slot` müşterisi 2)

- Vade: `turn_index - compact_cursor.turn_index >= 6` **veya** `location != compact_cursor.location_id`; ve `len(pending_narrations) >= 2`.
- Girdi: `pending_narrations` metinleri + oyuncu satırları; `known_ids` allowlist (paketteki NPC/yer id'leri); ≤ 3000 bayt. Ayrı mesaj listesi; `session.messages` ve bellek girmez.
- Çıktı şeması: `{"facts":[{"text":str≤160,"about":str|null}]}` ≤ 6, `format=` ile. `options={"num_predict":300,"temperature":0.2}`.
- Doğrulama: `about` allowlist dışında → null; `[[` içeren, boş, `_secret_free` kıran satır atılır; mevcutla aynı metin atılır; 24 tavanı en eskiden düşer. Sonuç çerçeveye (`frame.staged_summaries`) yazılır; `api/main.py:1528` `update_narrative_memory(..., staged_summaries=narrative_frame.staged_summaries)` ile birleştirir, `pending_narrations` boşaltır, cursor ilerler.
- Başarısızlık/geçersiz JSON: hiçbir alan değişmez, `pending_narrations` birikmeye devam eder (6 tavanı, en eski düşer), sonraki vadede yeniden denenir. Tur commit olur.
- Seçki (paket): `about ∈ seçili id'ler` veya `location_id == şimdiki`, en yeni önce, ≤ 8, ≤ 600 bayt.

### 4.3 Kayıt uyumu

Bellek `narrative_memory` olarak campaign_store payload'ında; şema 2 migrate ile yüklenir, eski kayıt bozulmaz. Dünyaya yeni anahtar yok. `test_narrative_memory.py:62, 381` tam anahtar kümesini sabitler → güncellenir. `:198` "narration saklanmaz" testi **bilinçli** değişir: "ham anlatım pakete girmez; yalnız `authority: summary` satırı girer".

## 5. B — `npc_agenda` dilimi

### 5.1 Dünya anahtarı `npc_agenda_v1` (yeni `npc_agenda.py`, pydantic strict, modül durumu yok, saat yazmaz)

```
State  version=1, resolved_through:int, plans[] ≤16, offers[] ≤16, news[] ≤32, log[] ≤64
Offer  offer_id, issuer_id, source_ref("quest:<id>"), public_terms{title,target_label,place,reward},
       presented_at, expires_at, state(presented|accepted|refused|expired|filled_by_other|breached|completed|failed),
       accepted_terms|null, player_outcome_seen:bool
Plan   plan_id, owner_id, offer_id, goal_kind="fill_offer", version, status(active|blocked|done|dropped),
       step{kind(await_answer|seek_other|do_self|drop), target_npc_id|null, earliest_at, deadline},
       tried_npc_ids[], needs_review:bool, last_resolved_at
News   message_id, sender_id, recipient_id, kind("breach_claim"|"offer_filled"), source_event_id,
       earliest_arrival, delivered_at|null, credibility("heard"|"witnessed")
Log    event_id, causal_parent_ids[], at, kind, actor_ids[], witness_ids[], player_known:bool
```
Harita §3b ile aynı; `recipient_id` sabit "player" olduğundan atıldı. Kaynak/rezervasyon, `truth_link`, güven düzeyi yok.

### 5.2 Akış (çağrı sayısı parantezde)

- **Teklif (0).** `dialogue_jobs.prepare` dönüşünde (`:71` `director.discover` sonrası) `npc_agenda.open_offer(world, quest)`: `expires_at` = görevin `deadlines.arm` penceresi (aynı saat), plan `await_answer`.
- **Kabul/ret (0).** `dialogue_runtime.resolve_turn` içinde `_generate_reply`'dan **önce** `npc_agenda.bind_player_decision(world, npc_id, player_text)`: muhatabın tek açık `presented` teklifi varsa ve metin `_AGREE` → `accepted` + `adventure.play.accept` (günlük yolu ile aynı geçiş, `accepted_terms` kopyası); `_REFUSAL` → `refused`, plan `seek_other @ now+3600`, görev `ABANDONED` değil **açık kalır** (NPC başkasına verebilir). Karar `build_context`'e `player_decision` olarak gider; model sadece seslendirir. Eşleşme yoksa teklif açık kalır, soru yok. Günlükten kabul (`play.accept`) de `accepted`'a bağlanır.
- **Doldurma (0).** `resolve_due` tikinde: sahip yaşıyor, serbest, savaşta değil; aday = yerleşimdeki yaşayan, `tried` dışı, oyuncu-dışı NPC'ler; sıra ve sonuç `sha256(campaign_id:plan_id:version:npc_id)` ile (bkz. `incidents/rng.py:16`), %50 eşiği; başarı → `filled_by_other`, görev `FAILED(outcome="filled_by_other")` (`adventure/transitions.transition`), paket verenin envanterinden silinir, `log` + `news(offer_filled)` yok (oyuncu öğrenince `_event(player_known=True)`). Başarısız → `tried` + `now+3600`, 3 denemeden sonra `needs_review`. Son tarih + 1 gün → `drop`.
- **İhanet v1 = ifşa (0).** Kabul edilmiş teklif varken oyuncu **başka** bir mevcut NPC'ye konuşurken metin görevin kamu etiketini (veren adı/sıfatı, "paket", "teslimat") + anlatma/ihbar fiili içerirse: `Offer.state=breached`, `_event(kind="witnessed_fact", privacy="public")` (dinleyiciler = `present_npcs`), `record_witness` (ilk üretim çağrısı). Kaydedilen şey "oyuncu şunu söyledi"dir; işin suç olup olmadığı yazılmaz. Paketin başkasına verilmesi mekanik yol gerektirir (`dialogue_jobs.resolve:120-122` ad eşleşmesi) → ertelendi.
- **Haber (0).** Veren dinleyiciyse hemen bilir. Değilse tanık (muhatap) → veren, `earliest_arrival = now+3600`, aynı yerleşim. Tanık yoksa haber yok. Teslimde: verenin perspektifine `PerspectiveEntry(kind="rumor", source_id=event)`, `relationships.note(issuer, -2, "breach:<offer_id>")` (teklif durumu üzerinden tek sefer koruması), planı `needs_review`.
- **Review (1, gerekince).** `spare_slot` müşterisi 1. Girdi: sahibin kamu profili, teklif şartları, denenen adaylar, haber özeti, aday listesi; ≤1200 token. Çıktı `{choice: wait|ask_npc|do_self|drop, target_npc_id|null, delay_seconds 0..14400}`. Geçersiz → değişiklik yok, bayrak kalır; son tarihte motor `drop`. Dünya modeli beklemez.

### 5.3 Kancalar

| Nokta | Yer | Not |
|---|---|---|
| Tik | `campaign_time.py:143` `close_due` sonrası: `known.extend(npc_agenda.resolve_due(world, old, resolution["stop_at"], source))` | gerçek durma noktası; kopyada çöz, sonda ata; 16/çağrı, `resolved_through` boşalınca |
| Teklif | `adventure/dialogue_jobs.py:71` | tek yaratım noktası (free_v1) |
| Karar | `dialogue_runtime.py:272` öncesi; `build_context`'e `player_decision`, `offer_state` | modelden önce Python |
| NPC sesi | `dialogue_runtime.build_context` → `known_to_me`: `interaction_adventure.perspective(world,npc)["entries"]` son 4 (kind ile), `relationship_tone` kova (soğuk/nötr/sıcak; sayı değil) | haber ancak böyle duyulur |
| Anlatıcı | `game.py:7036` yanına `known_news` ≤2×200 bayt, yalnız `player_known`; defter de aynı veriyi alır | |
| Günlük | `_event(player_known=True)` → `campaign_journal.py:764-774` otomatik | ek kod yok |
| Ret düzeltmesi | `interaction_adventure.py:1269`: iplik `offered` ise söz bozulmaz | tek koşul |
| Perspektif filtresi | `game.py:7143-7150`: `kind == "lie"` girişleri anlatıcıya gitmez | `rumor`/`belief` gider (NPC'nin inancıdır) |
| Kayıt doğrulama | `game.py:2372` yanına `if "npc_agenda_v1" in saved_world: npc_agenda.validate(...)` | yoksa dokunma |
| Reddedilen iş | `dialogue_jobs.py:60-61` kapalı iş → `DialogueResponseError` yerine sessiz "teklif yok" | planlar işi daha sık kapatır |

### 5.4 Kayıt uyumu, bütçe, çağrı

Ek üst anahtar; eski kayıt yüklenir, `view` yazmadan okur (`npc_statements.view` deseni). `SAVE_FORMAT_VERSION` 4 kalır, `State`/`scheduled_events` şemasına alan girmez. Anahtar motor kaydında → makbuzla commit, turla geri alınır, `undo` ile döner. Anlatıcıya giren tek şey `known_news` + defter satırı. Review çağrısı tolere fazda; sıfır çağrılı yollar her zaman yeter.

## 6. İş sırası (her satır bir ajan)

| # | Görev | Dosyalar | Kanıt testi | Oyuncu hissi kontrolü (gerçek motor, Türkçe) |
|---|---|---|---|---|
| T0 | **Ön koşul, bu plan dışı:** hedefsiz konuşmada en makul kişiyi seç (`OLCUM_20TUR` 1. madde) | `game.py` hedef çözümü | 20 tur yeniden: duvar ≤ 2 | Konuşma başlıyor mu |
| T1 | Şema 2 + migrate + `pending_narrations`/`compact_summaries` + paket yuvası (model yok) | `api/narrative_memory.py`, `session_manager.py`, `main.py:1830`, `test_narrative_memory.py` | v1→v2 round-trip; eski kayıt yüklenir; undo v1 anlık görüntü; ham anlatım pakette yok; reductions sırası | — |
| T2 | `campaign_ledger.py` + çerçeveye journal + prompt cümleleri + RECENT NARRATION etiketi | yeni dosya, `narrative_director.py`, `main.py:1323`, `game.py:12923,12970` | sentinel sır testi (AVAILABLE iş, gizli ad, ilişki puanı, ajanda planı pakete girmez); 900 bayt; aynı dünya → aynı defter; reload sonrası eşit | 10 tur oyna, kaydet, yeniden yükle; "Hancı bana ne söz vermişti?", "Kimi yendim?" — DM defterden doğru cevap |
| T3 | `spare_slot.py` + `model_phase` tolere fazları + `main.py:1437` + `game.py:16934` kancası (müşterisiz iskelet) | listelenen | tolere fazda hata → tur commit; 2 çağrıda DEFER, üçüncü deneme yok; aynı `action_id` replay'de çağrı yok; `incidents/attempts` hatası turu düşürmez | — |
| T4 | Compact özet işi | `spare_slot.py`, `narrative_memory.py`, `main.py:1528` | geçersiz JSON → değişiklik yok; allowlist dışı `about` → null; sır/`[[` süzülür; tavanlar; "özet kanonik olmaz" | 3. turda DM bir ayrıntı uydursun (ör. tezgâhtaki çizik); 12. turda sor — tutarlı. Çelişki senaryosu: envanterde yok dediğin şeyi özet var diyorsa defter kazanıyor mu |
| T5 | `npc_agenda.py` durum + tik + `open_offer` + kabul/ret bağlama + ret düzeltmesi + kayıt doğrulama | `npc_agenda.py`, `campaign_time.py`, `dialogue_jobs.py`, `dialogue_runtime.py`, `interaction_adventure.py`, `game.py:2372` | `test_npc_agenda_time` (okuma/yeniden yükleme/boş tur plan oynatmaz; bekleme oynatır; parçalı = toplu; ölü sahip; 16 tavanı; ufuk dışı); `test_npc_agenda_offer` (ret söz bozmaz; cevapsız açık kalır; kabul şart kopyalar; "olur/istemiyorum" bağlanır, belirsiz açık kalır) | Teklif al, "olur" de → günlükte ACTIVE; başka kampanyada "istemiyorum" de → iş açık, NPC işine döner |
| T6 | `seek_other` + `filled_by_other` + verenin bağlamı + `known_news` + `dialogue_jobs:60` yumuşatma | `npc_agenda.py`, `dialogue_runtime.build_context`, `game.py:7036`, `adventure/transitions` | görev `FAILED(filled_by_other)`; paket silinir; aynı teklif tekrar sunulmaz; oyuncu öğrenince journal olayı; `known_news` ≤400 bayt | Reddet, "iki saat bekliyorum", verene dön: iş gitmiş, veren kimin aldığını (etiketle) söylüyor; defterde satır var |
| T7 | İfşa ihaneti + tanık haberi + `rumor` perspektifi + ilişki notu | `npc_agenda.py`, `interaction_adventure.record_witness`, `dialogue_runtime.build_context`, `game.py:7143` | `test_npc_agenda_news` (varış öncesi tepki yok; sonrası var; tanıksız haber yok; iddia iddia kalır; ilişki bir kez; `lie` anlatıcıya gitmez) | Kabul et, başka NPC'ye işi anlat, hemen verene dön → değişiklik yok; 1 saat sonra dön → soğuk/soran ses |
| T8 | Review çağrısı (`spare_slot` müşterisi 1) | `spare_slot.py`, `npc_agenda.py` | `test_npc_agenda_model_budget` (0/1 çağrıda review; 2'de DEFER; hata turu düşürmez; geçersiz çıktı → değişiklik yok; son tarihte drop) | Adaylar tükenince NPC'nin bir sonraki adımı değişiyor mu (günlük/log) |
| T9 | Kayıt: `run_tests.py TESTS` + `test_runner_inventory` + `graphify update .` + HANDOFF | | suite yeşil | 20 tur ölçümü tekrar, `narrative_context_bytes` raporu |

T1–T4 ve T5–T8 birbirinden bağımsız; T3 ikisinin ortak zemini (T4 ve T8 ona bağlı). Her görev tek başına gönderilebilir.

## 7. Zaman daralırsa kesilecekler (sırayla)

1. T8 review çağrısı — plan `drop`'a düşer, dünya yine hareket eder.
2. T7 ihanet/haber — ret + doldurma tek başına "insanlar kendi işine bakıyor" hissini verir.
3. T4 özet çağrısı — defter + etiket düzeltmesi tek başına "DM ne olduğunu hatırlıyor"u verir; "ne söylediğini" eksik kalır.
4. Legacy mod desteği (zaten dışarıda) ve `offer_decision` (hiç girmedi).
5. Defter kaynaklarından 6–8 (yerler, oyuncu sözleri, olaylar) — 1–5 kalır.

## 8. İlk üç risk

1. **Konuşma başlamıyor (T0).** 8/20 tur açıklama duvarı. Dilimin tamamı konuşma üzerinden hissedilir; T0 olmadan test oyuncusu teklife ulaşamaz. Kabul/ret bağlama da çözülmüş muhataba dayanır.
2. **`api/main.py` hata politikası değişikliği.** Yanlış kapsamda tolerans, yarım uygulanmış durumu commit eder; dar kapsam ise iyi turu 503 yapar. Koruma: boş yuva işleri kopya üzerinde çalışır, tek atama; T3 testleri hem "hata turu düşürmez" hem "hata dışı faz hâlâ geri alır" ispatlar.
3. **Bütçe ve özet kalitesi.** Bayt/2 tahmini Gemma-Türkçe için ölçülmedi; 4800 paket zaten continuity'yi atıyor; 4B modelin özeti uydurabilir ve "defter kazanır" cümlesine uymayabilir. Koruma: T2 sonunda gerçek `narrative_context_bytes`; tavanlar tek sabitten; özet satırı `about` allowlist'li; çelişki senaryosu T4 oyun kontrolünde.

İkincil: ince teklif içeriği (plan hollow hissedilebilir, durum testi kanıtlayamaz), mod kararı, `relationships` 24-kayıt tamponu (teklif durumu üzerinden koruma var), uuid olay id'leri (eşdeğerlik testleri anlamla karşılaştırır).

## 9. Sahibin kararı gereken noktalar

- Oyun testi modu: `free_v1` (öneri) mi, legacy mi.
- "Ham anlatım saklanmaz" sözleşmesinin "özet saklanır, ham pakete girmez" olarak değişmesi.
- Özet vadesi 6 tur / mekân değişimi; doldurma gecikmesi 3600 sn; ilişki −2. Hepsi tek sabit, oynanarak ayarlanır.
