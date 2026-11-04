# Test İncelemesi: cba0408..a59bbea (2026-10-31)

Bağımsız, salt okunur inceleme. Yalnız `git diff` ve `git show` ile yapıldı. Hiçbir test çalıştırılmadı; aşağıdakiler kod okumasıdır, çalışma kanıtı değildir. Sayım değişiklik grubu üzerindendir. Satır numaraları a59bbea içindir.

## Sonuç

| Sınıf | Adet |
|---|---|
| JUSTIFIED | 34 |
| WEAKENED | 7 |
| SUSPICIOUS | 1 |

**Karar: GO WITH NOTES.** Gerçek bir hata kanıtlanmadı, ama W1, W2, W3 ve W5 boşlukları sessiz kalabilecek hatalara yol açar. Bunlar güçlendirilmeden yeşil suite bu dört alanda güvence sayılmamalı. S1 Kadir'in kararını bekliyor.

## WEAKENED

### W1. `scene_state` artık hiç karşılaştırılmıyor
- **Yer:** `api/tests/test_interaction_adventure.py:449`
- **Önce:** Plan turunda `adventure` ve `flags` dışındaki tüm anahtarlar aynı kalmalıydı.
- **Sonra:** `scene_state` de dışarıda; tek gerekçe "anlatıcı sahne kaydı açabilir" yorumu.
- **Kaçabilecek hata:** Yalnız plan kurulan turda `player_position`, `entry_target_reference`, `active_referent_id`, `proposal_references` veya ambient olay geçmişi değişebilir.
- **En küçük güçlendirme:** `scene_state` içinden yalnız `scenes[<mevcut konum>]` çıkarılsın, geri kalanı eşitlikle karşılaştırılsın.

### W2. Saldırı açıklama turunda "durum değişmedi" kanıtı kalktı
- **Yer:** `test_combat_v2.py:350,361`, `test_combat.py:272`
- **Önce:** `serialize_game_state()` ve tüm `world_state` tam eşitti.
- **Sonra:** v2'de yalnız `status`, `combat.active` ve RNG; `test_combat`'ta `npcs` ve `combat.active`. `before` değişkeni v2'de hâlâ alınıyor ama kullanılmıyor.
- **Kaçabilecek hata:** Açıklama dönüşünden sonra `observe_turn`, `record_entry_target_reference` ve `interaction_adventure.consume` çalışıyor. Hedefsiz bir saldırı bayrakları, saati veya macera durumunu değiştirebilir, tur harcayabilir.
- **Not:** 400 yerine doğal soru kabul edilmiş bir değişiklik, ama eşitliği kaldırmak için sahip onayı yok. `test_regression.py` aynı yolda eşitliği koruyor; farkın nedeni belirlenemedi.
- **En küçük güçlendirme:** v2'deki iki eşitlik geri gelsin, ayrıca `state_changes == []` ve boş olmayan anlatım istensin. Bir alan gerçekten değişiyorsa yalnız o alan gerekçeyle dışlansın.

### W3. `fixed_street`: açılış çeşitliliği akış testlerinin dışında
- **Yer:** `api/tests/fixed_street.py:19`, `test_varied_openings.py:138-151`
- **Önce:** Üretim ve testler aynı sokağı kullanıyordu.
- **Sonra:** Üretimde 1-3 kişilik 9 rolden seçim, 5 saat, 4 hancı var. `CampaignApiTests`, `ClockApiTests` ve `StageADiagnosticTests` kurulumunu kullanan en az 70 test dosyası eski sokakta, sabit saatte kalıyor. Hitap ve kapı testleri de buna dahil.
- **Kaçabilecek hata:** `campaign_seed` yeni kampanyaya yazılmazsa her oyun yine aynı "Kent sakini + Muhafız" ile başlar. Sahibin ilk şikâyeti olan bu hata suite'ten geçer: ilk bakış testi rolleri `scene_cast`'in kendisiyle karşılaştırıyor. Tek kişilik sahnede hitap ve kapı akışı da hiç çalışmıyor.
- **En küçük güçlendirme:** `NewCampaignTests` içinde 12 kampanyada `campaign_seed` dolu olsun ve en az iki farklı rol kümesi çıksın. `seeded_street = True` ile bir de tek kişilik hitap ve kapı akışı eklensin.

### W4. Test cümlesi yeni yola girmesin diye değiştirilmiş
- **Yer:** `api/tests/test_campaign_api.py:3146`, `test_playable_living_world.py:2066`
- **Önce:** "...içebileceğim bir yer var mı?" ile `local_search` bulunuyordu.
- **Sonra:** Cümle "...bir yer arıyorum." oldu. Yanında kişi varken soru artık kişiye gidiyor (72f4ace); bu sahip kuralına uygun.
- **Kaçabilecek hata:** "han" kelimesi geçmeyen bu doğal soru kişiye gider ama han bulunmaz. Kapsanan örnekler "Bu çevrede bir han var mı?" gibi cümleler.
- **En küçük güçlendirme:** `test_natural_addressing`'e eski cümle kişi varken eklensin; tek han yaratılsın ve adı anlatımda geçsin (`test_playable_living_world.py:716` gibi).

### W5. `not_applied` iddiasız dalının testi kalmadı
- **Yer:** `api/tests/test_roadmap_r02_backend.py:280`
- **Önce:** `assertNotIn("not_applied", ...)`, yani iddia yok.
- **Sonra:** `assertIs(..., True)` ve açık niyet yok. Bu değişikliğin kendisi JUSTIFIED ve daha sıkı. Ama `release_action_intent` hata verirse çalışan "iddia etme" dalını artık hiçbir test sınamıyor.
- **Kaçabilecek hata:** Serbest bırakma başarısızken tarayıcıya `not_applied` gider. Kayıt kapanır, sunucuda niyet açık kalır ve sonraki hamleler 409 alır. Bu, önlenmek istenen kilidin ta kendisidir.
- **En küçük güçlendirme:** `release_action_intent` patch ile hata versin; 503, `not_applied` yok, niyet açık beklensin.
- **Ayrıca:** `not_applied` sonrası aynı id hâlâ uygulanabiliyor. Araya başka hamle girdikten sonra geç gelen eski id'nin davranışı test edilmemiş; beklenen davranış bir testle yazılmalı.

### W6. Söylenti cevabının içeriği artık sınanmıyor
- **Yer:** `api/tests/test_default_npc_targeting.py:1245`
- **Önce:** `assertIn("söylenti", rumor_reply)`
- **Sonra:** Yalnız iki `assertNotIn`. Sözcüğün gitmesi doğru, olumlu kontrolün gitmesi değil.
- **Kaçabilecek hata:** Boş veya alakasız cevap geçer.
- **En küçük güçlendirme:** `assertEqual(rumor_reply, "Orayı pek bilmem.")`

### W7. Eşitlik yerine olumsuz kontrol
- **Yer:** `test_wave3_conversation_ux.py:102`
- **Önce:** `status == "clarification"` ve `success` false.
- **Sonra:** `assertNotEqual(status, "clarification")` ve `active_npc_id`.
- **Kaçabilecek hata:** Başka bir başarısız durum veya boş cevap geçer. Aylin listede de ilk olduğu için "son hitap edilen" ile "ilk kişi" ayrışmıyor; `test_campaign_api.py:14342` testi de aynı.
- **En küçük güçlendirme:** Beklenen `status`, `npc_id`, `success` ve boş olmayan anlatım yazılsın. Bir testte `last_npc_id` listedeki ikinci kişi olsun.

## SUSPICIOUS

### S1. Yeni test 06:00 başlangıcını sabitliyor (yeni dosya)
- **Yer:** `api/tests/test_varied_openings.py:76`, `campaign_time.py:78`
- **Durum:** Başlangıç saatleri 6, 10, 14, 17, 18. Test `dawn` değerini zorunlu kılıyor. Han 07:00'de, dükkân 08:00'de açılıyor. Kod yorumu ilk sahnenin kapalı kapılarla başlamaması gerektiğini söylüyor.
- **Sonuç:** Kabaca her beş kampanyadan birinde ilk han kapalı ve kilitli başlar. Bu, "oyunun ilk bossu han kapısı olmasın" isteğiyle çelişebilir. Saat onaylı olsa da bu birleşim onaylanmış görünmüyor.
- **Eksik test:** Sabit sokak `seed_start`'ı kapattığı için 06:00 ile han akışını sınayan test yok.
- **En küçük düzeltme:** Kadir karar versin. Han kapalı başlamasın isteniyorsa 6 çıkarılsın ve test `min(...) >= 7` beklesin.

## JUSTIFIED (34)

| Alan | Değişiklik |
|---|---|
| Kapı | Hanın kendiliğinden kilitli olmaması; testin kilidi kendisi koyması (`test_campaign_api` iki yer, `test_stage10a_gameplay_repairs`, `test_playable` üç yer) |
| Kapı | Kapalı ama kilitsiz kapıdan geçiş (`test_intent_response_consistency` üç grup, `test_narration_receipt_contract`) |
| Kapı | Zorlama cümlesi (`test_playable`), kilidin öğrenilmesi (`test_campaign_api:6661`, `test_roadmap_w03`), kapanış saati (`test_default_npc_targeting:1754`) |
| İsim | İsim cevabında rol yok (`test_campaign_api:8264,14099`, `test_npc_compound_dialogue_regression`, `test_playable:2256`) |
| Etiket | "Yakındaki kişi" kalktı (`test_intent_response_consistency`, `test_stage10a_narration_intent`, `test_narrative_memory`, `test_npc_transcript_replay_baseline`); ayırt ediciliği `test_npc_visible_labels` tutuyor |
| Hitap | Aynı isimde iki kişi, süresi geçmiş konuşma (`test_campaign_api:950,14342`) |
| Yer | "Doğrulayamam" kalktı, söylenti kaydı korunuyor (`test_experimental_npc_dialogue`, `test_default_npc_targeting:315,1192`); kişinin hanı söylemesi (`test_playable:716`) |
| Hazır satır | Islık ve plan cevabı (`test_lr00_everyday_actions`, `test_interaction_adventure:115`, `test_companion_wait_regressions`, `test_intent_response_consistency:763`); anlatıya ulaşmayı `test_free_attempts` tutuyor |
| Niyet | Model hatası kilitlemez (`test_roadmap_c10_primal_knowledge_http`, `test_roadmap_r02_backend:280`); fikstür depolama hatasına taşındı ve niyet hâlâ açık kalıyor çünkü talep `assert_current`'tan önce (`test_roadmap_r02_intents`) |
| Savaş | `test_regression.py` tam eşitliği koruyor |
| Anlatım | Oyuncunun hissini yazan cümle güvensiz; kontrol olumlu ve `reason_code` eşitliğiyle (`test_narrative_safety_calibration`) |

**Küçük notlar**
- `assertNotIn(npc["role"], ...)` büyük/küçük harfe duyarlı; "bir muhafız" sızıntısı "Muhafız" kontrolünden geçer. `casefold` eklenebilir.
- `.endswith(" biri")` kontrolü tek başına ortak bir etiketi yakalamaz; ayrıştırma ayrı testte.
- Islık satırı `OYUN_TARIFI_KADIR_20261031.md` içinde tek tek geçmiyor; gerekçe genel "mekanik cevap" kuralına dayanıyor.

## Açılış çeşitliliği sabit olmayan sokakla test ediliyor mu?

**Kısmen.**

| Kapsam | Sokak | Durum |
|---|---|---|
| `SeededCastTests` | Gerçek çekim, 16 sabit tohum, fonksiyon düzeyi | Var |
| Saat çeşitliliği | 12 HTTP kampanyası | Var |
| İlk bakış | Tek HTTP kampanyası, `seeded_street = True` | Var, ama rolleri kendisiyle karşılaştırıyor |
| Model hatası akışı | `test_model_failure_never_locks`, gerçek çekim | Var; kişi veya saat içeriğini sınamıyor |
| HTTP'de kampanyalar arası kişi farkı | | Yok |
| HTTP'de hancı çeşitliliği | | Yok |
| Hitap ve kapı akışı | | Yok |

## Ek gözlemler

- Sahibin onayladığı "bilinmeyen mesafe 5 ft" kuralını (`combat_lifecycle.py:171`) doğrudan sabitleyen bir test bulamadım. Küçük bir test eklenmeli: mesafesi olmayan kişiye savaş dışı saldırı, 400 değil gerçek bir açılış vuruşu; savaş içi `distance_unknown` reddi aynen kalır.
- Dükkân saatleri (08-19) kodda var, ancak bu incelemeye verilen onaylar yalnız han saatlerini kapsıyor.
- Commit mesajları büyük ölçüde diff ile uyumlu; W1, W2 ve W4'teki gevşemeleri ise anmıyor.
