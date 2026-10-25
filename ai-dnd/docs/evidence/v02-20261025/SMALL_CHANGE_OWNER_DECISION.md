# Faz 5 Karar Belgesi: Küçük Nedensel Olay, NPC Bilgisi ve Yalan Sınırı

Durum: **onaylandı ve uygulandı (K4)**; kullanıcı: "bunları da onaylıyorum". Faz 4 önce yapıldı.

Uygulanan: `scheduled_events.py` yeni etki türleri `mark_remove` ve `surface_item_custody` (`SURFACE_EFFECTS`; gizli, `NON_INTERRUPTIVE`, `aftermath_visible` yok; aksi `ValueError`). Mutasyon yalnız `equipment_economy.apply_scheduled_surface_effect` içinde: eylemci NPC olay mekânında canlı ve etkin olmalı, aksi halde hiçbir şey değişmez. Yalnız eylemci NPC'ye opak `witnessed:<event_id>` notu (`relationships.note`); oyuncu bilgisi değişmez. Kanıt: `api/tests/test_scene_small_events_contract.py` (9 test).

Bilinen sınırlar (dürüst kayıt): olayı oyun içinde kendiliğinden başlatan bir tetikleyici yok, yalnız sunucu tarafı `register_event`. NPC diyalog paketi yalnız opak işareti taşır; neden içeriği paketten kasıtlı olarak çıkarıldığı için NPC nedeni henüz sözle anlatamaz. `npc_mistake_stays_attributed_not_canon`, `model_contradiction_not_reclassified_as_intentional_lie`, `secret_word_in_harmless_smalltalk_does_not_block_speech` testleri bu kapsamda yazılmadı (diyalog yalan sınırı yüzeyi, ayrı iş). `incidents/*` değiştirilmedi.

## Mevcut durum (kanıtlı)

- Zamanlanmış olay sahibi: `scheduled_events.register_event/process_events` (nedensellik: `causal_group`, `dependencies`, `window_start/end`).
- Bilgi kapsamı: `incidents/awareness.py`, `incidents/knowledge.py`. Yalan sınırı: `dialogue_runtime.deception_context` (salt okunur doğrulama).
- Mevcut testler: `test_dialogue_deception`, `test_dialogue_live_context`, `test_incident_continuity`, `test_incident_projection`.
- **Eksik:** olayın masa izi veya eşya gözetimi üzerinde etki alanı yok (Faz 4'e bağlı). "Küçük olay oldu, nedeni kayıtlı, oyuncu nedeni bilmiyor" için onaylı küme yok.

## Önerilen başlangıç kümesi (yalnız ikisi)

| Olay | Etki | Tetik / ufuk | Oyuncu/NPC bilgi edinimi |
|---|---|---|---|
| `mark_cleaned` | Yetkili bir `feature_mark` bir kez silinir | oyuncu ayrıldıktan sonra, mekânda bir NPC varken, tek sefer | Oyuncu dönünce sonucu görür, nedenini değil. Tanık NPC bilir, diğer NPC bilmez. |
| `item_custody_change` | Mevcut bir yüzey eşyasının sahibi Faz 4 sahibi üzerinden değişir (kimlik korunur) | aynı sınır | Aynı kural. Söylenti ortak olgu olmaz. |

Rastgele hırsızlık oranı, yeni zamanlayıcı altyapısı ve tüm-dünya simülasyonu seçilmiyor.

## Gereken testler (karar sonrası)

`test_cleaning_changes_only_authorized_mark_once`, `test_existing_item_custody_change_conserves_identity`, `test_offscreen_effect_has_cause_but_no_auto_player_knowledge`, `test_rumor_and_unwitnessed_change_do_not_become_shared_truth`, `test_return_observes_result_not_secret_cause`, `test_large_change_without_causal_basis_is_rejected`, `test_grounded_large_event_not_suppressed_merely_for_scale`, `test_locked_fact_text_absent_from_npc_packet`, `test_secret_word_in_harmless_smalltalk_does_not_block_speech`, `test_npc_knowing_fact_and_willing_to_share_are_distinct`, `test_npc_mistake_stays_attributed_not_canon`, `test_model_contradiction_not_reclassified_as_intentional_lie`, `test_observer_knowledge_not_shared_with_other_npc`.

## Karar gereken

1. Başlangıç kümesi bu iki olay mı, daha az mı, farklı mı?
2. Ufuk kuralı "oyuncu ayrıldıktan sonraki ilk dönüş" olarak yeterli mi?
3. Faz 4 yüzey sahibi (SURFACE_OWNER_DECISION.md) önce onaylanacak mı? Sıra: Faz 4, sonra Faz 5.

Onay gelmeden `scheduled_events.py` ve `incidents/*` değişmez.
