# Oynanacak şey: insanlar kentini bilsin, ipler çekilsin (2026-10-31)

Durum: plan, kod yok. Okunan dal `task/c-series-merge` @ `b5435fe` (`AI-DND-c-merge/ai-dnd/`, satırlar o commit'e göre). Girdi: `OWNER_PLAY1`, `OYUN_TARIFI_KADIR`, `DEFTER_YASAYAN_DUNYA_PLAN`, Jarvis `02_WORLD_PLACES_HOOKS_TR` / `02_NPC_PUBLIC_TR` (yalnız "neden hoşa gidiyor" dersi alındı; içerik kopyalanmadı, `gm_only` okunmadı).

## 0. Tek cümle ve karar

Sahibin oyunu durdu çünkü **kimsenin kentine dair söyleyecek verisi yok**: prompt "bildiğin iş/yer varsa söyle" diyor (`game.py:8068-8072`) ama bağlama tek bir kamu bilgisi girmiyor; Python'un kendi cevapları da sabit ret ("belirli bir iş yok" `local_dialogue.py:582-586, 611-624`; "göze çarpan özel bir şey yok" `game.py:15603-15613`). Çözüm üç küçük parça: **(A) kent bilgisi** (her kişinin sınırlı, tohumlu kamu bilgi kümesi), **(B) dünya ipleri** (kampanyada tohumlanan, saatle yürüyen, gerçek şartlı 3–4 "birinin bir şeye ihtiyacı var" kaydı), **(C) işaret etmenin çalışması** (söylenen yer/kişi gerçek; "oraya gidiyorum" oraya gider). Model yalnız seslendirir; **ek model çağrısı sıfır**.

**Mod kararı: legacy'de kal.** Gerekçe: bu tasarımın modelden yapısal çıktı beklemesi yok (free_v1 işleri `job_proposals` JSON'una ve bozuk yönlendirmeye dayanıyor, `dialogue_runtime.py:116-130`, `game.py:17057-17065` erken dönüş). Legacy yolda konuşma notu (`_experimental_speech_note`) ve bağlam (`_experimental_npc_dialogue_context`) zaten var; veriyi oraya koymak yeter. free_v1'in "daha uzun, daha insan" sesi prompt üslubudur: `_SPEECH_ANSWER_RULES` (`game.py:8033`) ve `num_predict: 220` (`:7790`) üzerinden legacy'ye taşınır (T6). Mod geçişi bu dilimden sonra, ölçümle.

## 1. Koddan doğrulanan gerçekler

| Gerçek | Yer |
|---|---|
| Varsayılan rota legacy; speech yolu `AI_DND_NPC_SPEECH` olmadan da çoğu girdide modele gider (`experimental_dialogue_session`) | `api/session_manager.py:227`, `game.py:19465-19468, 19581-19614` |
| Konuşma notuna "iş arıyor" satırı giriyor ama bağlamda yer/kişi/iş verisi yok; `personal_context=False` ile profil de çıkarılıyor | `game.py:8068-8072, 8085-8094, 19598-19601` |
| Python'un iş/olay cevapları sabit ret | `local_dialogue.py:582-593, 611-624`; `game.py:15603-15613` |
| Kentteki kişiler tohumla üretiliyor (`scene_cast`, `_stable_name`), yerler `local_places.create_local_place` ile; kişi başına kalıcı `personal_profile`, `voice_trait`, `dialogue_persona` | `living_world.py:1472-1544, 1589-1659`; `local_places.py:233-282`; `game.py:3785-3835` |
| Yer türü bankası 10 tür, her birinde `issues` (yerel dert) + `role`; soylu hanesi türü **yok** | `local_places.py:22-145` |
| NPC'nin söylediği yer adı deftere giriyor; var olan yere bağlanıyor (`status: resolved`), son söylenen yer 6 tur hatırlanıyor | `npc_statements.py:378-429, 351-367` |
| "Evet Veyra Hanı" hatası: cümle başı yalnız `(da\|de)` eki soyuluyor; "Evet/Peki/Tamam" soyulmuyor | `npc_statements.py:78, 312-313` |
| Yere gitme yalnız tür kökünden (`stems`), ad eşleşmesi yok; aynı türden iki yer varsa ilkine gider; "oraya" çözülmüyor | `local_places.py:172-183`; `game.py:16770-16815` |
| Saat tek kapıdan ilerler; `close_due` sonrası boş kanca noktası | `campaign_time.py:118-149` |
| Teslimat mekaniği gerçek ve modelsiz: `DELIVERY` şablonu, paket envanterde, "paketi alıyorum/teslim ediyorum" Python'da çözülür — ama yalnız free_v1 çağırıyor | `adventure/dialogue_jobs.py:56-75, 92-142`; `dialogue_runtime.py:236-238` |
| Kabul/ret sözleri hazır (`_AGREE`, `_REFUSAL`) | `npc_statements.py:83-87` |
| Yeni dünya anahtarı istemciye sızmaz (allowlist); kayıt doğrulaması "anahtar varsa" deseni | `api/serializers.py:795-847`; `game.py:2372-2378` |
| Incidents/emergence `AI_DND_EMERGENCE_LIVE=1` + Neverwinter paketi ister; model çağrısı harcar | `api/session_manager.py:228-230`; `incidents/hooks.py:54` |

## 2. Tasarım

### A. `town_knowledge.py` (yeni, ~120 satır, salt okunur)

`public_knowledge(world, npc) -> list[dict]`: bu kişinin **kamuya açık** bildikleri, ≤ 5 madde, ≤ 600 bayt, deterministik.

Kaynaklar (hepsi kalıcı kampanya verisi): (1) yerleşimdeki yerler (`locations` parent==settlement, gizli/keşfedilmemiş hariç) ad + tür + `local_issue`; (2) oradaki kişiler kamu adıyla (`public_npc_name`, rol biliniyorsa rol); (3) `world_threads_v1` açık iplerin **kamu yüzü** (`public_line`: "X konağında adam arıyorlarmış"); (4) `npc_statements.place_references` (başkasının söylediği, `rumor`).

Kapsama: `sha256(seed|npc_id|item_id)[0] % 100 < kapsama(rol)`; kapsama: barmen/tüccar 70, muhafız 50, sakin 35, yolcu 10; ipin sahibi ve aynı yerin sakini her zaman. Böylece aynı kişi aynı şeyi hep bilir, bilmediğini hep bilmez; **herkes yardım etmez** (`voice_trait` "ters/şüpheci" olanlar için prompt zaten var). Çıktı satırı: `{"kind": "place|person|thread|rumor", "text": ≤90, "location_id", "npc_id|null"}`.

### B. `world_threads.py` (yeni, ~220 satır) — anahtar `world_threads_v1`

```
State   version=1, settlement_id, threads[] ≤ 8, next_number, last_tick
Thread  thread_id, kind(hiring|errand|trouble), status(open|heard|offered|accepted|done|filled_by_other|expired),
        place_id, owner_name, owner_npc_id|null, target_place_id|null, target_npc_name|null,
        terms{pay:int, duration_days:int|null, condition:str|null}, requires{vouch_from_kind:str}|null,
        public_line ≤120, private_line ≤160 (yalnız sahibi söyler), opened_at, due_at, heard_turn|null, quest_id|null, log[] ≤ 8
```

- **Tür kataloğu hikâye değil, kalıp:** `hiring` = "bir yerde el gerekiyor" (iş + ücret + süre, isteğe bağlı `requires.vouch`); `errand` = "bir paket başka yere gidecek" (mekanik: `DELIVERY`); `trouble` = o yerin `local_issue`'su (konuşma rengi + başka ipe yol). Metinler yer türü bankasından ve 3–4 kalıp cümleden tohumla birleşir; sabit örnek yok.
- **Tohumlama** (`ensure(world, settlement)`): yerleşim sahnesi ilk kurulduğunda 3 ip: 1 `hiring`, 1 `errand`, 1 `trouble`. Yerler **o anda** `local_places.create_local_place(world, settlement, kind)` ile yaratılır (sadece world, oturum gerekmez), sakin adı `stable_local_name` ile kayda yazılır (`record["resident_name"]`); kişi, oyuncu geldiğinde mevcut `furnish` ile doğar ve `bind_owner` ile ipe bağlanır. Böylece söylenen her ad gerçektir.
- **Hedef kampanyadan gelir, kodlanmaz:** `hiring` ipinin işveren türü karakterin kayıtlı geçmişine eğilir (`character.background`: Soldier → `estate`/`barracks`, Merchant/Guild → `market`/`workshop`, Acolyte → `temple`, yoksa tohum). Yeni yer türü **`estate`** (`local_places.PLACE_KINDS`: stems `konak|malikane|kosk`, suffix "Konağı", role "Kâhya", issues 2 adet). `estate` türlü `hiring` ipi `requires.vouch_from_kind` taşır (`smithy|market|tavern` tohumla): kâhya adam arıyor ama "bir esnafın kefaleti" istiyor. Kefalet, o türden yerin sahibine ait bir `errand/trouble` ipi `done` olunca düşer. Görev verilmez; yol zamanla açılır.
- **Tik** (`tick(world, now)`, `campaign_time.py:143` `close_due` sonrası): `due_at` geçen `open/heard` → `filled_by_other` (tohumlu %; `incidents/rng.py` deseni), `offered` → `expired`; açık ip sayısı < 2 ise yeni ip (aynı tür art arda gelmez). `accepted` ipin `quest_id`'si `COMPLETED/FAILED` olduysa `done/expired`. Modelsiz, kopyada hesapla, sonda ata.
- **Kabul/ret** (0 çağrı): speech yolunda model cevabından **önce** Python bakar: muhatabın `offered` ipi varsa ve oyuncu metni `_AGREE` → `accept(session, thread)`: `errand` için `templates.instantiate("DELIVERY", bindings=prepared_bindings(source_npc_id=owner, target_npc_id=hedef, location_ids=[target_place]))` + paket envantere + `director.discover` (`dialogue_jobs.prepare:65-74` gövdesi, `creation_evidence="thread-job:<id>"`); `hiring` için `accepted` + `due_at` = işe başlama saati, gün sonu `done` (ücret `equipment_economy` ile; yoksa yalnız günlük satırı). `_REFUSAL` → `open` kalır, sahibi başkasına verir (tik). Belirsiz → `offered` kalır, soru sorulmaz. Karar `speech_note`'a "oyuncu kabul etti/etmedi" diye girer; model onaylar.
- **İp "duyuldu":** `game.py:7861` `npc_statements.record` sonrası `note_mention(world, npc_id, npc_text)`: gösterilen cevapta ipin yer adı veya sahibi geçiyorsa `heard`. Sahibiyle konuşmada ip `offered` olur (sahibi `private_line`'ı bağlamda görür, şartları kendi söyler).

### C. İşaret etmenin çalışması

- `local_places.is_local_place_visit` + `game._local_place_turn`: önce **ad eşleşmesi** (yerleşimdeki yerlerin `name`/`aliases`'ı metinde geçiyorsa o kayıt), sonra tür kökü; "oraya/ oraya gidiyorum / bahsettiğin yere" → `npc_statements.last_said_place` (6 tur); varsa ona git. Aynı türden iki yer + ad yok → kısa Python sorusu değil, en son söylenen.
- `_named_places_in_sentence`: `_SENTENCE_OPENER` yerine söylem sözcükleri seti (`evet, hayir, peki, tamam, elbette, tabii, hmm, yani`) cümle başından soyulur; test: "Evet, Veyra Hanı var" → "Veyra Hanı".
- Oyuncu kişiyi adıyla arıyorsa (`unresolved_named_address`) ve ad bir ipin `owner_name`'i ise: "X şu an burada değil; <yer>de bulursun" (Python, 0 çağrı).

### D. Prompt ve Python cevapları

- `_experimental_speech_note` (`game.py:8046`): "**Kentte bildiklerin:** <A listesi; ≤5 satır>. Bunların dışında kimseyi, yeri, işi bilmiyorsun; uydurma. Birini başka yere yönlendirebilirsin." Sahibi için ek satır: "Şu işin sende: <private_line>; şartlar: <terms>. İstersen teklif et, mecbur değilsin." Kabul/ret satırı.
- `_experimental_npc_dialogue_context` (`:8076`): `"known_about_town": [...]` (aynı veri, JSON).
- `local_dialogue.personal_answer/unaddressed_work_answer` ve `game.py:15603-15613`: bilgi listesi boşsa eski sabit satır; doluysa `None` döner (modele bırakır) ya da ilk `thread` satırını Python söyler ("Duyduğuma göre X konağında adam arıyorlarmış" — 0 çağrı, model yoksa da oyun ilerler).
- `num_predict` 220 → 300 (T6, ölçümle).

### E. Bütçe, kayıt, hata

| Parça | Bayt tavanı | ~token |
|---|---|---|
| Kent bilgisi (not + JSON) | 600 + 600 | ~600 |
| İp sahibi satırları | 320 | ~160 |
| Kural cümleleri | 200 | ~100 |

Mevcut speech promptu küçük (hedefe bağlı bağlam); 8192 içinde kalır; ilk gerçek ölçüm T2 oyun kontrolünde `AI_DND_SPEECH_DEBUG` iziyle. **Model çağrısı: 0 ek.** Kayıt: `world_threads_v1` ek üst anahtar; eski kayıt yüklenir, `ensure` ilk speech turunda tohumlar (sahibin mevcut kampanyası da ipleri alır); doğrulama `game.py:2372` deseni; serializer allowlist'i sızdırmaz. Hata: A/B/C kancaları `try/except` → log + eski davranış; tik hatası turu düşürmez (kopyada çöz). `_fit_context_packet` dokunulmaz (speech paketi ayrı).

## 3. İş sırası (her satır bir ajan)

| # | Görev | Dosyalar | Kanıt testi | Oyuncu hissi kontrolü (gerçek motor, legacy, Türkçe) |
|---|---|---|---|---|
| T0 | `estate` yer türü + `resident_name` desteği (`furnish` adı kayıttan okur) | `local_places.py:22-145, 321-357` | tür yaratılır, ad kayıttan, idempotent | "konağa gidiyorum" → konak doğar, kâhya orada |
| T1 | `world_threads.py` durum + tohum + tik + doğrulama; kanca `game.py:7509` sonrası `ensure`, `campaign_time.py:143` `tick`, `game.py:2372` validate | yeni dosya, `campaign_time.py`, `game.py` | 3 ip, yerler gerçek; aynı tohum → aynı ipler; reload eşit; `due_at` geçince `filled_by_other`; açık < 2 → yeni; eski kayıt yüklenir ve tohumlanır | 10 tur oyna, kaydet/yükle: `world_threads_v1` aynı |
| T2 | `town_knowledge.py` + prompt notu + JSON anahtarı + sabit ret satırlarının bilgiye bağlanması | yeni dosya, `game.py:8046-8163, 15603-15613`, `local_dialogue.py:582-624` | kapsama deterministik; sahibi hep bilir; yolcu az bilir; ≤600 bayt; gizli alan (private_line sahibi dışına, ilişki puanı) girmez | Carius hana girer, "burada iş var mı?" → barmen en az bir **gerçek** yere/kişiye yönlendirir veya karakterine uygun reddeder; 3 kişiye sor: en az biri ip verir |
| T3 | İşaret: ad eşleşmesi, "oraya", söylem sözcüğü soyma, "X nerede?" | `local_places.py:172-183`, `game.py:16770-16815, 6333`, `npc_statements.py:312-313` | "Evet, Veyra Hanı var" → ad "Veyra Hanı"; aynı türden iki yer → adla doğru olan; "oraya gidiyorum" → son söylenen | NPC konağı söyler → "oraya gidiyorum" → konağa varır, kâhya adıyla orada |
| T4 | Sahibi konuşunca `offered` + `note_mention` (`heard`) + kabul/ret bağlama (`_AGREE/_REFUSAL`) + `speech_note` karar satırı | `world_threads.py`, `game.py:7846-7861, 19581-19614` | ret → `open` kalır, sonra `filled_by_other`; "olur" → `accepted`; belirsiz → `offered`; teklif tekrar sunulmaz | Kâhyaya "iş var mı?" → şartları söyler, kefalet ister; "olur" de → günlükte kayıt; başka kampanyada reddet, 1 gün bekle, dön: iş gitmiş |
| T5 | `errand` → `DELIVERY` görevi + paket + legacy'de `dialogue_jobs.resolve` çağrısı (`thread-job:` öneki kabul) + tamamlanınca `done` + kefalet düşer | `world_threads.py`, `adventure/dialogue_jobs.py:80, 114`, `game.py:17111` | kabul → paket sahibinde, "paketi alıyorum" → oyuncuda, teslim → `COMPLETED` → ip `done` → `estate` ipinin `requires` boş | Demirciden paketi al, teslim et; kâhyaya dön: artık kefalet istemiyor, işe alıyor |
| T6 | Ses: `_SPEECH_ANSWER_RULES` free_v1 üslubu (uzunluk, insani dokunuş), `num_predict` 300, aynı stok satırların tekrarını kır (`"Dinlenmeye uğradım sadece"` vb. `_CLAIM_DENIAL_LINES` tohumlu seçim) | `game.py:7790, 8033-8043, 6902` | prompt ≤ 8192 ölçülü; cevap kesilmiyor | 20 tur: kelimesi kelimesine tekrar ≤ 1 |
| T7 | Kayıt: `run_tests.py TESTS`, `test_runner_inventory`, HANDOFF; 30 tur sahip oyunu tekrar | | suite yeşil | "ilerleyemiyorum" yok: ilk 30 dakikada ≥ 2 gerçek ip, ≥ 1 yere varış |

T0→T1→T2 sıralı; T3 bağımsız (T0 sonrası); T4 T2'ye, T5 T4'e bağlı; T6 bağımsız. Her görev tek ajan, kendi testiyle.

## 4. Zaman daralırsa kesilecekler (sırayla)

1. T5 mekanik teslimat ve kefalet zinciri — `hiring` yine `accepted` olur, kefalet şartı tohumdan düşer (`requires=None`); kapı zamanla değil hemen açılır.
2. T6 ses ayarı.
3. T4 ret/doldurma — ipler duyulur ve işaret edilir ama sahibi teklif etmez; yine de dünyada gidilecek yer ve konuşulacak kişi olur.
4. A'nın 4. kaynağı (`rumor` söylentileri) ve B'nin `trouble` türü.
5. Hiç kesilmeyecek: T1 tohum + T2 bilgi + T3 işaret. Bu üçü tek başına "kent beni duyuyor, gidebileceğim yer var" hissini verir.

## 5. İlk üç risk

1. **Model bilgiyi görmezden gelip yine "bilmiyorum" der.** Koruma: `thread` satırı ilk sırada, not metni "bunu söyleyebilirsin" diye açık; Python yedek cevabı (D) model başarısız olsa da yönlendirir. T2 oyun kontrolünde 3 kişiden en az 1 yönlendirme ölçülür.
2. **Yer yaratımı tavanı** (`MAX_LOCAL_PLACES_PER_SETTLEMENT=8`, 60 NPC, yer başına 6 NPC): tohum 3 yer kullanır; tik yeni ip açarken önce mevcut yerleri yeniden kullanır, tavan dolunca ip açmaz (sessiz).
3. **Kabul bağlamada yanlış pozitif** ("olur" başka bir şeye evet). Koruma: yalnız sahibiyle konuşurken, ip `offered` iken ve aynı turda; `has_multiple_dialogue_clauses` ile tek cümle; aksi hâlde `offered` kalır.

## 6. Sahibin kararı gereken noktalar

- Legacy'de kalma (öneri) ve free_v1 üslubunun prompt olarak taşınması.
- İş vadesi (`due_at` varsayılan 1 gün), kapsama yüzdeleri, kefalet şartının her `estate` ipinde olup olmayacağı. Hepsi tek sabit, oynayarak ayarlanır.
- Önceki defter planıyla (`DEFTER_YASAYAN_DUNYA_PLAN`) ilişki: `world_threads_v1` o planın `npc_agenda_v1` teklif/doldurma işini legacy'de karşılar; iki anahtar birlikte yaşamaz, ileride biri diğerine katlanır. Bu dilim önce.
