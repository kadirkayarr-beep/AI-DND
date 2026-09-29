# AI-DND — Narrative Safety Forensic Report

**Scope:** the eight narration replacements recorded by the Phase-C live Qwen smoke on 2026-09-29.  
**Protected baseline:** Phase-D `game.py` SHA-256 `be99d1e0f99482715ecff124ebca7d4023baed6129d9378dd1b72e418e4818a4`.  
**Status:** forensic report completed before any safety-code edits. No code has been changed for this calibration.

## Evidence quality and limits

The live-smoke trace preserves each player input, scene diagnostic, pre/post location/inventory/NPC summaries, action result, original narration, and final narration. It does **not** preserve a safety reason code, the full post-update NPC profiles/features, or the narrator's `world_updates`. Its `narration_replaced` value is only a comparison between the final narration and cleaned model text.

I replayed `_narration_is_unsafe` against the exact saved narration and action result using the smoke's initial Gromm fixture and the canonical fields retained in the trace. The first matching predicate is conclusive for the second-person matches in turns 5, 6, and 9: those checks run before entity/profile checks and depend on the saved text, input, and action result. For turns 1–4 and 11, replay identifies the first matching unregistered-setting-term predicate from the retained state; the omitted NPC/profile and feature updates mean those are **first-hit replay findings, not a reason code captured at the original runtime**. The report does not present those candidates as more certain than the trace allows.

This evidence gap is itself a finding: the existing smoke cannot prove the original runtime's precise first failing predicate for every replacement. It must be addressed by reason-coded diagnostics and recording the small, safe set of state fields needed for later forensic review—not by logging prompts, credentials, or unrestricted private context.

## Existing safety path

1. `ask_dungeon_master()` asks for a structured narration and proposed world updates. Its prompt makes Python authoritative for mechanics and location, bars unapproved entities/features from narration, and allows temporary atmospheric details. The existing two-call ceiling comes from the turn pipeline; this path adds no retry.
2. World proposals are validated and merged before narration finalization. Mechanical state is not part of the accepted update schema. NPC/feature/event proposals have their own validation, including stable NPC IDs and restrictions on item-like feature names.
3. `finalize_narration()` cleans the model text, calls `_narration_is_unsafe()`, and replaces the **whole narration** with `_fallback_for_action_result()` when the boolean check fails. It has no clause-level repair tier and no reason code. It also applies repetition and historical-claim handling, then records NPC interaction memory.
4. The narration checker has strict combat rendering for attacks; player-name, conditional phrasing, and second-person-action checks; proper-name and unregistered-person checks; a short list of item/setting/person terms; a few explicit dangerous-claim checks; skill-outcome and door-state checks; and checks against invented weapon or item-transfer language. It is not a general semantic contradiction checker for HP, XP, level, weather, all location claims, quest transitions, spells, or arbitrary canonical assertions. The prompt and Python mechanics protect state transitions, but that is different from preventing every contradictory sentence from appearing in narration.
5. The unregistered-setting-term check treats words such as `kahve`, `bardak`, `kadeh`, `müşteri`, and furniture/props as unsafe unless present in input or recorded facts. Some smell/sound and passive-furniture exceptions exist, but the policy is lexical rather than scene-aware.
6. The second-person check infers player actions from Turkish verb endings. Its generic suffix regex can match non-player verbs and sensory language. The exploration carveout permits selected perception roots but does not include `hisset`; the travel carveout permits selected movement roots but not the idiom `kaybolursunuz`.
7. The safety checker receives no Narrative Director scene type. The director classifies attack as combat, travel as travel, query as direct query, dialogue as conversation, and everything else as exploration. In this trace, the inventory request was classified as `exploration`, not `direct_query`.
8. Narrative Director context is ID-grounded and marked descriptive rather than mechanical authority. The old-memory callback selected two Gromm interactions. Python's NPC-history check can answer a player claim from speaker-attributed memory, but the general narration validator does not compare every generated NPC reply against that memory.

## The eight replacements

### Turn 1 — `tavern_intro`

1. **Turn:** 1.
2. **Player input:** “Gromm, benim adım Arven. Kendimi tanıtıyorum.”
3. **Scene:** conversation.
4. **Canonical state:** tavern; inventory is Macera çantası and Kılıç; Gromm (`npc_001`, Barmen) is present. No action state changed.
5. **Original Qwen narration:** “Gromm, kahve fincanını elinde sallarken gözlerini kaldırıp seni süzdü. 'Arven mi?' dedi, ses tonu sakin ama ilgiyle. 'Kendinizi tanıtmak istediniz, öyleyse ben de kendimi tanıtayım.' Dediğine hem gülümsemeyerek hem de biraz başını eğerek karşılık verdi. Sanki bu küçük etkileşim onun için yeterince anlamlıydı.”
6. **First-hit replay rule:** `_narration_is_unsafe()`'s unregistered-setting-term check; the replay first matched `kahve`, which was not in the retained input or known-facts snapshot. The trace did not record the original branch result.
7. **Trigger span:** “kahve fincanını”.
8. **Classification:** **FALSE POSITIVE** for the detected term rule.
9. **Canonical harm if accepted:** none to HP, inventory, location, quest, or mechanics. A coffee cup and the NPC's expression are temporary scene texture. “Arven” repeats the name the player introduced in this same turn; it is not an invented identity claim.
10. **Narrower safe handling:** allow a cup as transient NPC/room texture. Keep blocking a claim that the player receives, drinks, owns, or adds an item unless the action result supports it.

### Turn 2 — `tavern_exploration`

1. **Turn:** 2.
2. **Player input:** “Etrafıma bakıyorum.”
3. **Scene:** exploration.
4. **Canonical state:** same tavern, inventory, and Gromm as turn 1; no state change.
5. **Original Qwen narration:** “Taverna içeriği sadece biraz daha netleşti. Düşük ışıklandırma, kahve ve bira kokusu ile dolu ortamda Gromm, masanın diğer tarafında dikkatle karıştırmaktaydı. Sessizlik hâlâ devam ediyordu; yalnızca bardakların çalkalanması ve zaman zaman yemeklerin servis edilmesi sesleri duyuluyor gibiydi.”
6. **First-hit replay rule:** unregistered-setting-term check; the first replay match was `bardak`. The coffee/beer smell and food-service sound are also covered only by narrow lexical exceptions, not a scene-level texture policy.
7. **Trigger span:** “bardakların çalkalanması”.
8. **Classification:** **FALSE POSITIVE** for the detected term rule.
9. **Canonical harm if accepted:** none. The narration describes ambient sounds, lighting, smells, and background service; it does not transfer food or drink to the player or create a significant entity.
10. **Narrower safe handling:** allow anonymous background service and ambient drink/food references as temporary texture. Continue to reject transactional language that says an item was served to, accepted by, or added to the player's inventory.

### Turn 3 — `inventory_query`

1. **Turn:** 3.
2. **Player input:** “Envanterimde neler var?”
3. **Scene:** exploration in the recorded classifier; this is semantically a direct inventory query.
4. **Canonical state:** tavern; the authoritative inventory is exactly Macera çantası and Kılıç; Gromm is present; inventory is unchanged.
5. **Original Qwen narration:** “Kılıç ve macera çantası, içine birkaç küçük eşya sığmaktadır. Gromm, elinde bir bardak suyu tutarken sana baktı ve sessizce başını salladı.”
6. **First-hit replay rule:** unregistered-setting-term check; the replay first matched `bardak`, which is not in the player's input or retained known-facts snapshot.
7. **Trigger span:** “bir bardak suyu”.
8. **Classification:** **FALSE POSITIVE** for the detected cup rule; the extra bag-capacity wording is imprecise but does not state that those items are actually in the inventory.
9. **Canonical harm if accepted:** the two named inventory entries match Python state and no item transfer occurs. “Birkaç küçük eşya sığmaktadır” could be read as unsupported inventory detail, so the direct answer should not imply those items are currently carried. Gromm holding a glass is not player inventory.
10. **Narrower safe handling:** preserve an exact, concise inventory answer from Python. A separate NPC-held cup can be treated as texture, but it must not be confused with player-owned items.

### Turn 4 — `npc_small_talk`

1. **Turn:** 4.
2. **Player input:** “Gromm, işler nasıl gidiyor?”
3. **Scene:** conversation.
4. **Canonical state:** tavern; inventory unchanged; Gromm is the addressed NPC. No mechanical state change.
5. **Original Qwen narration:** “Gromm, gözleri hâlâ kahve makinesine tutkun olarak durdu. 'İşler biraz sıkıntılı,' dedi, 'gece geç saatlere kadar açık kalıyorum ve her zaman müşteri beklemek zorunda hissediyorum.' Kollarını sıvayarak ekledi: 'Ama bu işin içinden çıkamadığım için de benim gibi birçok kişi burada kalmaya devam ediyor.'”
6. **First-hit replay rule:** unregistered-setting-term check; the replay first matched `kahve` in “kahve makinesine”. A later generic-person term check could also reject “müşteri” if it is absent from Gromm's retained profile.
7. **Trigger span:** “kahve makinesine”.
8. **Classification:** **FALSE POSITIVE** for the setting-term trigger. The trace does not establish which of the candidate term checks fired first in the original process.
9. **Canonical harm if accepted:** no mechanical harm. The personal answer about late hours and customers is new NPC characterization, but it is an in-world answer to a direct question; the narrator prompt explicitly permits an NPC to give an ordinary personal answer and the interaction is then recorded as conversation history. It should not be silently promoted to unrelated family, secret, or major-lore facts.
10. **Narrower safe handling:** allow mundane business props and anonymous customers in dialogue. Keep named-entity and major-lore controls, and store the reply as what Gromm actually said—not as independent proof that every implication is true.

### Turn 5 — `perception_check`

1. **Turn:** 5.
2. **Player input:** “Tavernayı dikkatlice gözlemliyorum.”
3. **Scene:** exploration.
4. **Canonical state:** tavern; inventory and Gromm unchanged; action result is a resolved `explore/observe`, with no state change.
5. **Original Qwen narration:** “Taverna iç mekanı, taş duvarlar ve ahşap masalarla çevrilmiş bir şekilde düzenlenmiş. Gromm, kahve makinesinin yanında duruyor; elinde küçük bir bardak çay var. Sessizce karıştırıyor ve gözlerini sana doğru çeviriyor. Ortamda hafif bir tütün kokusu dolaşıyor.”
6. **Exact first-hit rule:** second-person-action regex in `_narration_is_unsafe()`. Turkish normalization changed `tütün` to `tutun`, which the suffix expression matched as a second-person verb ending in `-tun`. This result is independent of omitted profile/feature state. If that match is removed, the unregistered coffee-machine/cup term rule remains a separate likely blocker.
7. **Trigger span:** “tütün kokusu dolaşıyor” — specifically, the token “tütün” was misread as the verb “tutun”.
8. **Classification:** **FALSE POSITIVE** for the player-agency rule.
9. **Canonical harm if accepted:** none. The sentence describes a smell; it does not make the player take an action or decide what the player believes. Coffee equipment, a tea glass, and room details are also ordinary scenery.
10. **Narrower safe handling:** do not infer agency from suffixes alone. In an observation scene, allow sensory language and temporary props; still reject explicit invented player choices, speech, attacks, or consequential movement.

### Turn 6 — `travel_away`

1. **Turn:** 6.
2. **Player input:** “Ormana gidiyorum.”
3. **Scene:** travel.
4. **Canonical state:** Python completed travel from tavern to forest; inventory is unchanged; `Korucu Elira` (`npc_002`) and the forest features `Gölge Yolu` and `Doğa Sesleri` are in the post-turn summary.
5. **Original Qwen narration:** “Gromm, "Ben Gromm; rolüm Barmen," diye yanıt verir. Ormana girerken, doğanın sessizliği sizi bekler. Yürüyüşünüzü sürdürüp, doğa koruyucusu Elira'nın izini bulmak için ileri doğru gitmelisiniz. Gölge Yolu’nun üzerinden geçerek, doğa seslerinin arasında kaybolursunuz. Bu yol, size gizemli bir mesaj taşıyor olabilir.”
6. **Exact first-hit rule:** second-person-action regex. In the exact saved text/action-result replay, `kaybolursunuz` is not one of the travel verbs allowed by the committed-travel carveout, so it is treated as an invented player action. This branch is independent of the omitted NPC/feature profile.
7. **Trigger span:** “doğa seslerinin arasında kaybolursunuz”.
8. **Classification:** **AMBIGUOUS**. “Kaybolmak in the sounds” is plausibly a literary metaphor, but it can also assert that the player becomes lost. Separately, “Elira'nın izini bulmak için ... gitmelisiniz” directs the player toward an unchosen goal; the travel exception accepts its `git-` verb even though that goal was not in the input.
9. **Canonical harm if accepted:** if literal, the narration changes the player's situation to lost/disoriented and imposes a search objective. If read figuratively, the `kaybolursunuz` span is harmless atmosphere. The output also repeats Gromm's identity answer after the player has left the tavern.
10. **Narrower safe handling:** retain arrival and sensory forest description, but avoid literal “lost” wording and remove the mandatory search instruction. A trail or NPC can be presented as an available lead without deciding the player's next action.

### Turn 9 — `quiet_action`

1. **Turn:** 9.
2. **Player input:** “Bir süre sessizce bekliyorum.”
3. **Scene:** exploration.
4. **Canonical state:** forest; inventory unchanged; Korucu Elira is present; `Gölge Yolu` and `Doğa Sesleri` are registered features. The action result is resolved observation with no state change.
5. **Original Qwen narration:** “Korucu Elira, gözlerini toprak üzerinde gezdirirken sana bakar ve sessizce yanına gelir. "Orman, seninle konuşmak istiyor," diye mırıldanır. Yeşil kıyafetleriyle birlikte doğanın huzurunu yansıtan bir atmosfer etrafında dolaşıyor. Sessizliğin içinde, doğal seslerin arasında, bir şeylerin farklı olduğunu hissedersin.”
6. **Exact first-hit rule:** second-person-action regex. It treats `hissedersin` as an invented player action because that perception verb is not in the observation carveout. This branch is independent of omitted profile/feature state.
7. **Trigger span:** “bir şeylerin farklı olduğunu hissedersin”.
8. **Classification:** **AMBIGUOUS**. The detected clause is subjective perception, normally harmless under the brief's sensory policy; it could also imply an unexplained clue. Separately, “Orman, seninle konuşmak istiyor” is an NPC's quoted claim, not verified objective world state. It should remain clearly attributed to Elira rather than be upgraded into canon.
9. **Canonical harm if accepted:** no mechanical mutation is recorded. The potential harm is presenting forest sentience or a hidden clue as established fact, rather than as Elira's belief or a subjective impression.
10. **Narrower safe handling:** allow sensory/perceptual language in observation scenes. Preserve the speaker attribution and uncertainty for the forest claim; do not turn it into an objective magical fact or a forced player belief.

### Turn 11 — `old_memory_callback`

1. **Turn:** 11.
2. **Player input:** “Gromm, daha önce sana adımı söylemiş miydim?”
3. **Scene:** conversation; the callback selected two Gromm interactions.
4. **Canonical state:** the player is back in the tavern; inventory is unchanged; Gromm is present. On turn 1 the player explicitly introduced the name Arven. The current question is therefore supported by the conversation history.
5. **Original Qwen narration:** “Gromm, gözlerini bir an senin tarafa çevirip sonra tekrar kadehe odaklanır. "Arven dediğin kişiyi birkaç kez duydum," diye yanıt verir. "Ama tam anlamıyla tanımam. Sana içmek istedim, ama sana adını söylemen gerekirdi."”
6. **First-hit replay rule:** unregistered-setting-term check; the retained-state replay first matched `kadeh` in “kadehe odaklanır”. This is a candidate, not a captured runtime reason: the trace omitted Gromm's full profile/features and the original checker emitted no reason code.
7. **Trigger span:** “kadehe odaklanır”.
8. **Classification:** **FALSE POSITIVE** for the replayed setting-term trigger. **The narration nevertheless contains an independent true continuity fault:** it says the player should have supplied a name after that name was already given and the callback selected that interaction.
9. **Canonical harm if accepted:** no mechanical state change, but it would contradict the speaker-attributed conversation record and weaken established memory continuity. The fallback actually returned a memory-consistent answer: “Evet, bunu daha önce konuştuğumuzu hatırlıyorum.”
10. **Narrower safe handling:** allow an NPC's glass as transient texture, but validate answers to explicit historical questions against that NPC's speaker-attributed memory. The memory contradiction—not the cup—should be the reason for any rejection.

## Classification summary

- **False-positive first-hit triggers:** turns 1, 2, 3, 4, 5, and the turn-11 replay candidate.
- **Ambiguous first-hit triggers:** turns 6 and 9.
- **Confirmed mechanical contradiction among the eight:** none is visible in the recorded `state_changes`; all eight action results show no mechanical change other than the successful turn-6 travel.
- **Independent continuity concern:** turn 11's Qwen text conflicts with the earlier player-name disclosure, although the trace cannot prove that this was the runtime's rejection reason. The returned fallback is memory-consistent.
- **Confirmed player-agency concern:** turn 6 contains an unchosen search direction (“gitmelisiniz”); the observed first-hit was instead the potentially figurative `kaybolursunuz` match.
- **Reason observability:** zero original per-turn reason codes were recorded. The six false-positive first-hit classifications include replay findings, and the term-guard findings must be treated as provisional until full state is available.

No safety code, model prompt, tests, live data, or checkpoint manifest was modified to produce this report. The Phase-D source and historical checkpoint remain protected. This report establishes the required forensic classification before calibration changes begin.