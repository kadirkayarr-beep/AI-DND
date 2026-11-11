# Şikâyet izleme sonucu (2026-10-31)

Salt okunur kod izleme, `task/c-series-merge`. Oyunda çalıştırılmadı. Kabul belgesi değildir.

## [still_reachable] 1a. Name shows on screen on the free dialogue route (free_v1), including when the NPC does not want to give it.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/dialogue_runtime.py:102 sends the real name to the model as speaker.name even while name_known_to_player is False.
- ai-dnd/dialogue_runtime.py:206-208 sets name_known_to_player=True on a plain substring test: name.casefold() in spoken_text.casefold(). It has no word boundary, no self-introduction check and no refusal check.
- ai-dnd/living_world.py:53,70 pool contains ordinary Turkish words: 'Yara', 'Hakim', 'Iman'. For a hidden NPC named Yara, a line such as 'Bu sana yarar' or 'yaralı' flips the flag with no name ever spoken (substring match, read from code, not run).
- ai-dnd/dialogue_runtime.py:212-213 prints reply['stage_direction'] raw, and the flag check only reads spoken_text. A stage direction such as 'Marek omuz silkiyor' reaches the screen while the label stays hidden.
- ai-dnd/dialogue_runtime.py:219 marks the turn 'accepted'; the HIDDEN_NPC_IDENTITY_DISCLOSURE scan at ai-dnd/game.py:9547-9565 is never run on this route. ai-dnd/dialogue_commitments.py:14-32 validates places and jobs only, not names.
- ai-dnd/game.py:16527-16532 runs dialogue_runtime.resolve_turn before every legacy query path, so 'adın ne?' reaches the model here when free_v1 is on.
- ai-dnd/dialogue_runtime.py:298 says the NPC may give its name in a natural introduction but gives no instruction for withholding it.
- ai-dnd/docs/PLAYABLE_DIALOGUE.md:26 sets AI_DND_DIALOGUE_MODE=free_v1; ai-dnd/api/session_manager.py:225 applies it to new campaigns only. Without the env var this route is off.

Kök neden: Player knowledge is derived from a substring of model text, and the stage direction is neither scanned nor repaired. Whether the name leaks in a given reply depends on the model, but the flip logic and the missing stage scan are deterministic Python. The substring test turns a sentence where the NPC never gives its name into a learned name.

En küçük düzeltme: Keep the name available to the model but make Python the owner of learning it. (1) In dialogue_runtime.prepare_turn replace line 207 with a word-bounded first-person claim: reuse the claim pattern from npc_speech_boundary.mask_bound_self_name (adım/ismim/ben X, plus 'bana X derler'), and refuse it when 'değil' or a negation follows. (2) Before rendering, repair the stage direction by replacing the hidden name with public_npc_name(npc). Repair, do not reject. (3) Add one prompt sentence saying the NPC may refuse to give its name and, if it does, must not use it in spoken_text or stage_direction. Do not add a new rejection.

Deneme cümlesi: Adın ne? Söylemek istemiyorsan söyleme, ama sana nasıl hitap edeyim?

## [still_reachable] 1b. On the legacy route the NPC can never refuse its name, and any name question flips name and role at once.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/game.py:1453-1474 _handle_query sets name_known_to_player=True and role_known_to_player=True unconditionally, then prints 'Ben X. <role> olarak buradayım. <occupation>'. The only guard is the player negating the request (local_dialogue.identity_disclosure_is_negated, game.py:1454).
- Callers with no NPC-side decision: ai-dnd/game.py:14148, 18461, 18471, 18494.
- ai-dnd/local_dialogue.py:495-504 classifies 'ismi nedir' as npc_identity, and ai-dnd/game.py:1324 matches it too. A question about a third party or a place therefore reveals the addressed NPC's own name. This matches the brief's 'Han konuşulurken İsmi nedir?' case.
- Relationship, persona and role are never read before the disclosure.

Kök neden: The name disclosure is written as a state query, not as an NPC decision. With no mood, trust or persona input, the same answer is given by everyone, and the player's question alone unlocks the role too.

En küçük düzeltme: In _handle_query, stop flipping role_known_to_player and drop the role and occupation clause, so that asking a name returns a name. Add one small gate before the flip: if relationships.read(world) shows a negative score for this NPC, return a natural in-character evasion from a small line bank without flipping the flag. Separately, resolve 'ismi' (third person) against the last discussed entity before it can reach npc_identity; only ismin/adın forms should address the NPC.

Deneme cümlesi: Han hakkında konuşurken: İsmi nedir?

## [likely_fixed] 1c. Unknown name leaking through the UI and API projections.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/api/serializers.py:626-630 and :822 project NPCs through living_world.public_npc_projection, then _NPC_FIELDS (:81-94). The raw world.npcs list is not returned.
- ai-dnd/living_world.py:304-313 overwrites name and role in the projection.
- ai-dnd/api/serializers.py:201-210 conversation interlocutor, :289-301 combat names (fails closed on an unknown id), and :823 shops all go through public projections. public_shop_name at living_world.py:317-334 hides 'X'in Tezgâhı' for an unknown keeper.
- ai-dnd/api/campaign_journal.py:611-617,649 stores the public label and updates it only after Python says the name is known.
- artifacts/ai-dnd-experience/src/pages/game-browser.tsx:422,561,891 and src/lib/action-suggestions.ts:71 only render npc.name from those projections, so the UI has no route of its own to the raw name.
- ai-dnd/game.py:7660 legacy speech label uses public_npc_name, and game.py:9547-9565 scans legacy narration for hidden name and role.
- Remaining narrow exception, free_v1 delivery jobs: ai-dnd/adventure/dialogue_jobs.py:29 passes the raw recipient name to the model, and :66, :136 and ai-dnd/dialogue_commitments.py:47 print it, while that NPC keeps the unknown label on screen.

Kök neden: The projection layer is sound. On-screen names now come from flag flips and raw narration text (1a, 1b), not from the UI. The delivery job card is a small inconsistency: the giver names a recipient the player then sees only as a descriptor.

En küçük düzeltme: No UI change. For the job case, either set name_known_to_player=True on the recipient when the player accepts the job, since the giver told them, or print public_npc_name there. The first fits the fiction better.

Deneme cümlesi: Bu paketi kime teslim edeceğim, adı neydi?

## [still_reachable] 2a. Unknown people are not described by visible traits and are not distinct from each other.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/living_world.py:266-274 public_npc_descriptor returns only 'Bir <rol>' or 'Yakındaki kişi'. The stored appearance field is never used for the label.
- ai-dnd/living_world.py:288-301 public_scene_people builds 'bir <rol>' or 'bir kişi' and ignores the descriptor too.
- ai-dnd/living_world.py:223-230 hides every role outside a short allow-list, so 'Kent sakini' and 'Yolcu' both become 'Yakındaki kişi'.
- ai-dnd/game.py:15362-15371 promotes every referent as role 'Yolcu', even when the ambient event was a priest, child or carter, so a Kent sakini plus a promoted person read 'Yakındaki kişi' twice. Presence text can become 'bir kişi, bir muhafız ve bir kişi'.
- ai-dnd/game.py:1121-1124 ambiguity reply prints identical labels and then 'Hangisini kastettiğini belirt.'
- ai-dnd/game.py:15295-15298 shares the opening-line counter by public label, so two unknown people share one counter.
- artifacts/ai-dnd-experience/src/pages/game-browser.tsx:891 dropdown can show two identical options. Appearance is shown only as a row description at :423, so the data exists and the label ignores it.
- ai-dnd/living_world.py:1450-1470 fixed appearance strings mean there is no variety to draw on anyway.
- ai-dnd/api/narrative_memory.py:274-279 has its own separate 'Yakındaki kişi' fallback.

Kök neden: The hidden-name state has only one fallback label, derived from role. No per-NPC visible trait is stored, so distinctness cannot be produced anywhere downstream.

En küçük düzeltme: Add a small trait bank in living_world.py, picked by sha256 of campaign seed + npc id, skipping traits already used at that location. Store it once as npc['visible_trait'] in create_npc_from_ai (game.py:3789-3804). Make public_npc_descriptor return 'Bir <trait> <rol veya kişi/adam/kadın>', falling back to the current text for saves without the field. Change public_scene_people:295 and narrative_memory:279 to use the same descriptor. Constraint: _GENERIC_SPEAKER_LABEL_RE at game.py:10886-10888 accepts at most two words after 'bir', so keep the trait to one word or widen that regex. Add the trait to resolve_npc_reference (game.py:6046-6051) and grounded_action's noun list (grounded_action.py:412-419), so that 'sakallı olana soruyorum' resolves. In _promote_scene_referent, derive the role from the referent's first alias instead of hard-coding 'Yolcu'.

Deneme cümlesi: Etrafa bakıyorum. Burada kimler var? Sakallı olanla konuşmak istiyorum.

## [still_reachable] 2b. Class or role given away unless noticed (for example, that someone is a druid).
Alan: trace:identity-repetition

Kanıt:
- Works by default: ai-dnd/game.py:3803 hides any role not on the allow-list, and public_npc_role (living_world.py:257-263) returns None for it.
- Deterministic leak, legacy route: ai-dnd/game.py:1458,1466-1474 asking a name flips the role and prints '<Rol> olarak buradayım' plus the occupation. A proposed NPC with a hidden role such as druid would be announced by this path.
- ai-dnd/dialogue_runtime.py:102,106 sends role and occupation to the model in free_v1, and prepare_turn does no role scan. Only the prompt line at :290 ('Meslek/profil kartını her cevapta okuma') limits it. Whether it leaks here depends on the model.
- ai-dnd/game.py:3751 keeps a model-written appearance string; ai-dnd/api/serializers.py:86 and game-browser.tsx:423 show it. The role scan at game.py:9550-9553 reads narration only, so a model appearance like 'druid cübbeli' would reach the panel (model dependent).
- ai-dnd/local_dialogue.py:276 correctly blocks public personal details for hidden roles.

Kök neden: The hidden-role flag is respected by labels, but the name reply unlocks it, and free_v1 and the appearance field have no equivalent of the legacy scan.

En küçük düzeltme: Remove the role flip and role clause from _handle_query (same edit as 1b). In prepare_turn, repair the stage direction for a hidden role the same way as the hidden name. In create_npc_from_ai, drop the role word from appearance when the role is not visibly obvious, as a repair and without rejecting the NPC.

Deneme cümlesi: Selam, adın ne? Bu arada burada ne iş yapıyorsun, belli olmuyor.

## [likely_fixed] 3a. Same name every campaign, such as Marek.
Alan: trace:identity-repetition

Kanıt:
- Root cause reproduced with a standalone hash script copying _stable_name's unseeded formula: location fr:city:neverwinter gives npc 1 'Kent sakini' = Marek and npc 2 'Muhafız' = Cael. That is the owner's guard plus companion.
- ai-dnd/reports/playable-living-world-v1-1-smokes/1791333285487268400-a68c9f98/summary.json:119-121 shows npc_001 Marek, Kent sakini, at Neverwinter, confirming that formula ran in a real smoke.
- ai-dnd/living_world.py:1373-1378 now folds the seed into the hash and uses the 101-name pool when a seed exists.
- ai-dnd/api/session_manager.py:220-221 generates uuid4 and calls initialize_campaign_opening before any scene materializes; ai-dnd/api/opening_narrative.py:73-78 and living_world.py:1254-1256 set the seed first, even when no location is resolved.
- ai-dnd/api/main.py:1272-1281 reasserts the seed from campaign_id each turn.
- Saved NPCs keep their stored name, per the _stable_name docstring (living_world.py:1370-1371), so an old save still has Marek.
- Unseeded GameSession or a POST session without a campaign keeps the legacy pool; api/main.py:790. The UI uses create_campaign (game-browser.tsx:1649).

Kök neden: The old unseeded hash used only location, role and NPC number, so the same start gave the same names. New campaigns no longer do this. Not run in this read-only pass; this rests on the code path and the hash reproduction.

En küçük düzeltme: No code change for new campaigns. Tell the owner to judge this only in a new campaign. Optionally add one test: two create_campaign calls at Neverwinter, then a look on each, must not both give Marek and Cael.

Deneme cümlesi: Etrafa bakıyorum. (İki yeni kampanyada) Muhafıza adını soruyorum.

## [still_reachable] 3b. Same opening every campaign: guard plus companion, same scene frame.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/living_world.py:1449-1461 every city scene creates exactly 'Kent sakini' and 'Muhafız', with fixed appearance strings and fixed personalities ('Sakin ve dikkatli.', 'Ölçülü ve nazik.').
- ai-dnd/living_world.py:1462-1477 every tavern is one 'Barmen', always 'Sıcakkanlı', plus the same 'Ahşap masa'. ai-dnd/local_dialogue.py:733-739 reuses that personality as temperament.
- The start catalog offers only Neverwinter: ai-dnd/api/tests/test_campaign_starts.py:61-62 asserts that single option.
- ai-dnd/campaign_time.py:57 starts at 09:00; canonical_start_time is read at :55 and no production code outside campaign_time sets it. ai-dnd/api/world_metadata.py:29-30 defaults to day and clear.
- Therefore ai-dnd/api/opening_narrative.py:102-105 gives the same first sentence and same weather sentence every time, and :121-123 always ends with 'Burada sana dayatılmış bir görev yok; bir sonraki adım sana ait.'
- Only the seeded GREEN ambient event varies (ai-dnd/ambient_event_catalog.py:188-195), plus character notes. About 13 catalog entries fit city, day, clear, by my reading of the catalog.
- ai-dnd/campaign_opening.py build_opening is not called by the create flow: no caller appeared in the production search; the real opening is api/opening_narrative.py.
- ai-dnd/game.py:14925,14927 and 15369 also fix the merchant and promoted-person text.

Kök neden: Names were made variable but the cast, their temperament, the clock and the weather were not. New names on the same two people in the same sentence still read as the same opening. It also conflicts with the brief's suspicious guard and curt barman, since every guard is polite and every barman is warm.

En küçük düzeltme: Replace the tuples in materialize_scene with small per-kind banks of (role, appearance, personality), including sharper tempers, and pick distinct entries with sha256 of the campaign seed. Keep the first entry for an empty seed so fixtures stay the same. In opening_narrative, seed the time of day and weather from campaign_id at creation, and drop the closing sentence or pick from a small bank. This is variety, not a scripted opening; do not add any of the brief's examples. Later, one model-generated cast line would replace the bank.

Deneme cümlesi: Etrafa bakıyorum.

## [depends_on_model] 3c. Marek priming through the model prompt.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/game.py:8427-8428 the dialogue prompt says 'identify the speaker explicitly with the NPC's name (for example, 'Marek: “...”')'.
- ai-dnd/game.py:8202 uses 'Gromm' in the intent prompt.
- ai-dnd/game.py:8318-8333 local_person_proposal lets the model choose a name with no pool or example. create_npc_from_ai accepts it (game.py:3762-3808).

Kök neden: A concrete name in a prompt example is the likeliest name for the model to repeat, either as a speaker label or as a newly proposed person. It also tells the model to label by name, which conflicts with hidden identity. Whether it happens depends on the model.

En küçük düzeltme: Replace 'Marek' at game.py:8428 with the supplied public label, for example '<verilen konuşmacı etiketi>: “...”'. In the local_person_proposal branch, ignore the model's name and use living_world.stable_local_name, which is seeded. That repairs rather than rejects.

Deneme cümlesi: Buralarda şifacı biri var mı, biri yolu gösterebilir mi?

## [still_reachable] 4a. Same lines: NPC personal details repeat between campaigns.
Alan: trace:identity-repetition

Kanıt:
- ai-dnd/local_dialogue.py:242-245 the profile seed is npc_id + location + role. The campaign seed is not used, and generate_npc_id (ai-dnd/game.py:3639-3646) is sequential.
- Computed with a standalone script: npc_001 Kent sakini at Neverwinter always gets resident bank index 2 (fırın) and npc_002 Muhafız always gets guard index 0, in every campaign.
- Banks are tiny: guard 2, bartender 2, traveler 2, merchant 1, craftsworker 1, resident 3 (local_dialogue.py:94-217).
- local_dialogue.py:157 'Tezgâhın köşesindeki küçük çizik yıllardır orada.' is the bartender detail from the brief; a bartender in location id 'tavern' numbered 1 or 2 hashes to bank 0, which contains it.
- ai-dnd/local_dialogue.py:730 dialogue persona seed is npc id only, so temperament and voice repeat by NPC number. local_dialogue.py:738 fixes the goal text for everyone.
- ai-dnd/dialogue_runtime.py:106 feeds these fields to the model in free_v1, so the repetition reaches model replies too.
- ai-dnd/local_dialogue.py:288-289 public_personal_detail recomputes the expected profile from the same inputs, so a seed change must keep this compatible.

Kök neden: The name fix never reached the profile and persona seeds, so a different name carries the same life story, voice and small talk.

En küçük düzeltme: Add a campaign_seed parameter defaulting to '' to new_personal_profile and ensure_dialogue_persona, prefixing it into the hash only when non-empty, so old saves and fixtures hash the same. Pass living_world._campaign_seed(world_state) from create_npc_from_ai. Make public_personal_detail compare against both forms, or store the seed used on the profile. Widen the banks gently; most of the gain is from the seed.

Deneme cümlesi: Bugün neler yaptın, nerelisin?

## [still_reachable] 4b. Same deterministic lines inside and across campaigns on the legacy local replies.
Alan: trace:identity-repetition

Kanıt:
- Fixed single lines: ai-dnd/game.py:15130 'Fena değil, teşekkür ederim', :15148 'Merhaba', :15101, :15140, :18552; ai-dnd/local_dialogue.py:571,576,602-604,608.
- ai-dnd/local_dialogue.py:602-603 'Yerel halka gündelik iş olup olmadığını sorabilirsin' is the mechanical advice the brief rejects.
- Line picks are keyed only to npc id + player text with no campaign seed: ai-dnd/game.py:6696,6720 and ai-dnd/interaction_adventure.py:965. Same NPC number and same question give the same line in every campaign, and the same line again if the player repeats.
- ai-dnd/game.py:15266-15278 _variation_index is unsaved session state keyed by the public label, so it resets on reload and is shared by unknown people. Only look and conversation openings use it.
- ai-dnd/game.py:6711 repeat lines do use a salt, which is the one correct example.
- ai-dnd/game.py:15105-15119 gates personal answers, while most of the others run before any model call on the legacy route. In free_v1 these are bypassed for a resolved NPC (game.py:16527).

Kök neden: Local replies were built as safe answers rather than as speech, with a small number of lines and a seed that ignores campaign and turn.

En küçük düzeltme: Add one helper, for example local_dialogue.pick_line(world, npc, lines, key), hashing the campaign seed, npc id, key and a per-NPC turn count from npc_speech_log, and skipping the previous index for that NPC. Use it at game.py:6696,6720 and interaction_adventure.py:965, and convert the fixed one-liners above to 3-4 line tuples. For the unaddressed work answer, narrate what the player sees instead of advising them. Long term, these replies should go through the model on every route.

Deneme cümlesi: Nasılsın? (aynı kişiye iki kez) Peki burada iş var mı?

## [depends_on_model] 4c. Same encounters and same speech on the model route.
Alan: trace:identity-repetition

Kanıt:
- Encounters are not a fixed sequence. ai-dnd/ambient_event_catalog.py:159-175 avoids recent ids and groups, :188-195 picks by campaign seed. ai-dnd/adventure/encounters.py select (:101) has no caller in the production search. ai-dnd/bounded_encounter.py:17-18 is opt-in through explicit commands.
- Ambient events only add colour. Most BLUE events promote to a generic 'Yolcu' (game.py:15362-15371), so different events lead to the same person (see 2a).
- free_v1 has no anti-repeat step. ai-dnd/dialogue_runtime.py:290 only asks the model not to reuse a pattern, and context carries the last four exchanges (:83-84,108-109). PLAYABLE_DIALOGUE.md:7 says the old repair path is intentionally skipped.
- The ambient text catalog is fixed Turkish sentences with about 65 entries, so long play will show repeats by design (ambient_event_catalog.py:51-117).

Kök neden: Encounter selection varies by campaign. What feels the same is the cast and the model's own habits, which Python cannot settle. Real play is the only test. ai-dnd/docs/PLAYABLE_DIALOGUE.md:3 records that real-model acceptance is still open.

En küçük düzeltme: Do not add an encounter system. Fix the cast and profile seeds first (3b, 4a), since they feed the prompt. Then add a light repair in prepare_turn: if spoken_text matches the last exchange for this NPC after normalize_text, use speech_repeat_line instead of showing it, as the legacy route does at game.py:13336.

Deneme cümlesi: Aynı soruyu tekrar soruyorum: bu şehirde neler oluyor?

## [still_reachable] (1) "Kapıyı açmaya çalışıyorum" on a door in reach: an unlocked door should open, a locked one should be told naturally. The attempt wording takes a different path from "Kapıyı açıyorum".
Alan: trace:door-travel

Kanıt:
- ai-dnd/grounded_action.py:225-322 reads the verb as open with attempt=True, and bind gives kind=door with score 40.
- ai-dnd/grounded_action.py:2563-2565: `generic_door = generic_door and step["verb"] == "open" and (not info.get("attempt") or lockpick_prefix)`. The comment says generic try-opening 'belongs to the legacy Athletics owner'. So _direct_door_step is False, _owned_single_step is False and _decide defers at :2770.
- ai-dnd/game.py:1196 counts 'açmaya çalış' as force_attempt. ai-dnd/game.py:1201-1204 then returns an Athletics check whenever `door["locked"] or ... force_attempt`, so an unlocked door also rolls.
- ai-dnd/game.py:14229-14299: the deterministic check runs before resolve_python_world_action at :14310, so the 'Kapıyı itiyorsun; ... açılıyor' branch at :1608-1617 is never reached for this wording.
- ai-dnd/game.py:8852-8863: a successful Athletics roll opens a locked door with no breaking and no tool.
- ai-dnd/game.py:12921-12925: the fallback says '{name} kilitli kalır.' on any failure, which is false for an unlocked door. With a working model the narration is model output; the validator at :10482-10487 only rejects a 'kilitli' claim.
- ai-dnd/test_playable_living_world.py:2303-2334 pins the Athletics path for a locked door. No test covers an unlocked door with this wording.

Kök neden: Two door owners exist. The natural owner, grounded_action._do_open, handles opening with no roll and with locked-door prose. The attempt form is deliberately excluded from it and goes to a legacy rule that treats 'trying' as forcing. In Turkish, 'açmaya çalışıyorum' is the plain way to say it, so the player pays a Strength roll against an ordinary door.

En küçük düzeltme: At grounded_action.py:2565 drop the attempt exclusion: `generic_door = generic_door and step["verb"] == "open"`. The turn then goes to _do_open (:1514): unlocked opens with no roll, locked gets the existing 'kilitli; yerinden oynamıyor' text. 'Kapıyı zorlayarak açmaya çalışıyorum' stays legacy because its prefix is two words. Remove 'açmaya çalış' from game.py:1196 so the legacy branch agrees. Update test_playable_living_world.py:2303-2334 and test_narrative_safety_calibration.py:500. Optionally trim the menu sentence at :1540.

Deneme cümlesi: Kapıyı açmaya çalışıyorum

## [still_reachable] (1) and (3) Inside a han or venue, the door the player came through does not exist for door verbs. The player gets "Burada açıp kapatabileceğin bir kapı görünmüyor".
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:14843-14850 and ai-dnd/grounded_action.py:1208-1216: a venue door's location is the street (parent), not the venue.
- ai-dnd/game.py:2899-2907: _current_door only matches door.location == world.location, so it returns None inside.
- ai-dnd/grounded_action.py:420-426: candidates() skips doors with location != here, so bind gives target None and _direct_door_step is False (:2531). The turn defers at :2770, before the _current_door_target check at :2790.
- ai-dnd/grounded_action.py:1359-1363, 1374-1385: _inside_entry_door already knows this door, but a single-step 'kapıyı açıyorum' never reaches it.
- ai-dnd/game.py:1486-1513: with no door found, door_action returns the 'blocked' reply.
- ai-dnd/game.py:14082-14094: 'kapıyı inceliyorum' inside gets 'İçeride inceleyebileceğin belirgin bir kapı göremiyorsun.'

Kök neden: Door lookup is by the door's own location. The grounded multi-step path knows about the entry door from inside; the single-step path and every legacy path do not. The reply is a false 'no door' refusal from code, not from the model.

En küçük düzeltme: In game._current_door, when `here` is empty, fall back to _venue_door_for(world_state["location"]) (:2841). That covers deterministic_check, resolve_python_world_action, _inspection_findings and the validator. Mirror it in grounded_action.candidates(): after the door loop, append a door candidate for _inside_entry_door-equivalent data, with place_id=None so _prefer_side does not move the player. The reply at game.py:1512 then only fires where no door really exists; reword it there as plain narration.

Deneme cümlesi: (Hanın içindeyken) Kapıyı açıyorum

## [still_reachable] (1) "Hangi kapı olduğu bağlamdan anlaşılır": with several doors on the street and no standing position, the door is guessed.
Alan: trace:door-travel

Kanıt:
- ai-dnd/grounded_action.py:576-583: two doors both score 40, so target=None and ambiguous is set.
- ai-dnd/grounded_action.py:2770: the single step is not owned, so _decide defers before the clarify branch at :2814.
- ai-dnd/game.py:2899-2907: legacy `next(iter(here), None)` takes the first door in list order. The attempt then rolls and may change that door (:8860-8865).
- ai-dnd/grounded_action.py:542-543: when last_target_id is a door, the +6 breaks the tie. That covers only doors touched by the player, not a door or place the conversation was about.

Kök neden: Context only means near_target_id or last_target_id, which physical acts set. NPC talk and recently named places never feed it, so the fallback is list order with no ask and no reasoning.

En küçük düzeltme: Reuse the 'last said place' helper from the '(4) oraya' finding: in bind, when doors tie, add a small bonus to the door whose place_id matches the place the active or last NPC just named. If doors still tie, have _decide return clarify for door verbs instead of deferring to _current_door (one condition before :2770: `first["ambiguous"]` and verb in the door verbs).

Deneme cümlesi: (İki kapalı hanın olduğu sokakta, NPC birini anlattıktan sonra) Kapıyı açmaya çalışıyorum

## [still_reachable] (2) Doors locked by default at taverns or inns. The first han a player searches for is always locked.
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:14805: `_ensure_local_tavern(parent_location_id, *, open_for_entry=False)`.
- ai-dnd/game.py:14843-14854: the new door gets 'locked': not open_for_entry and the description 'Kapalı ve kilitli.'
- ai-dnd/game.py:15611-15628: a tavern search calls _ensure_local_tavern(root_location) with the default, so it is locked at any hour, and the reply repeats 'Sokağa açılan kapısı kapalı ve kilitli.' (:2832-2833).
- ai-dnd/grounded_action.py:2754-2761: the first inn search is deliberately deferred to this owner.
- ai-dnd/game.py:14819-14820: `existing` returns first, so a later open_for_entry=True (:15676-15678) cannot repair an inn found by search.
- ai-dnd/game.py:15068-15072: the NPC line 'kapısı kilitli; şu anda orada dinlenemezsin' follows from it.
- ai-dnd/test_playable_living_world.py:2287-2298 pins this as expected behaviour.

Kök neden: The default on the only first-discovery path is locked. No hour, seed or reason decides it. This is the owner's 'ilk boss han kapısı' case, in code and pinned by a test.

En küçük düzeltme: Have _ensure_local_tavern decide the door with the rule in the next finding instead of `not open_for_entry`: open and unlocked during business hours, `open_for_entry` always opens. Keep the 'new venues only' save rule (:14842). Update test_playable_living_world.py:2297-2298.

Deneme cümlesi: Yakınlarda bir han arıyorum

## [still_reachable] (2) Inns made by the grounded path or from NPC talk: locked outside 10:00-23:00, one in five locked even in hours, none created open, and a lock never lifts with time.
Alan: trace:door-travel

Kanıt:
- ai-dnd/grounded_action.py:1206-1216: `business = 10 <= hour < 23`, `locked = not business or _seed(...) % 5 == 0`, 'open': False always. If campaign time is unreadable, hour is None and the door is locked (:1199-1207).
- ai-dnd/grounded_action.py:1170-1175: shops are the same shape (locked 1 in 4 in hours, 8-19). The depo, ambar, konak and kule spec is door 'locked' at :1104-1112.
- ai-dnd/dialogue_runtime.py:164: NPC-proposed venues use the same _create_venue.
- Writes to locked=False are only player actions: ai-dnd/grounded_action.py:1600, 1621; ai-dnd/exploration.py:404, 406; ai-dnd/game.py:8862. So 'Kapalıyız! Akşamüstü gel.' (grounded_action.py:1439) never comes true.
- ai-dnd/grounded_action.py:2133-2145: the open-place search needs door.open is True, which new venues never have, so 'açık bir han arıyorum' falls to 'şu an açık olduğunu doğrulayabildiğin bir yer bulamıyorsun', another mechanical 'doğrula' line.

Kök neden: Door state is decided once at creation, with no idea that a public house is normally open and with no link to the campaign clock afterwards.

En küçük düzeltme: Add one helper, e.g. grounded_action._public_door_state(world, location_id), used by _create_venue and _ensure_local_tavern: during business hours {open: True, locked: False}; otherwise closed, with a lock only on a rare seed. An unknown hour counts as open. Drop the `% 5` in-hours lock for taverns. For 'Akşamüstü gel', re-evaluate in _venue_entry_door or _do_knock: a closed seeded public door unlocks when current hours are business hours and the player has not locked or broken it. Reword :2145 as 'Şu an açık bir yer göremiyorsun.'

Deneme cümlesi: Akşam olunca hana gidip kapısını açıyorum

## [still_reachable] (2) and (4) A closed but unlocked door stops the walk: "Tamam, hana gidiyorum" ends at the door, and named travel gets "... kapalı. İçeri geçemezsin." even though nothing is locked.
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:2851-2874: _venue_entry_door returns any door with `not door.get("open")`, locked or not.
- ai-dnd/game.py:7188-7189: commit_location_change refuses on that result.
- ai-dnd/timed_gameplay.py:379-389, 441-443: _blocked_venue_result gives '{name} kapalı. İçeri geçemezsin.' The same text is at ai-dnd/game.py:13846, 14200, 16280.
- ai-dnd/grounded_action.py:2577-2628: go + a named place is not owned (only approach, reference or via_pronoun are), so 'Kızılhan'a gidiyorum' to an existing place defers to legacy travel, game.py:14189-14192 start_travel.
- ai-dnd/grounded_action.py:1283-1287: _arrive_front enters only if door.open or door.broken; otherwise it stops with 'kapalı ama kilitli görünmüyor'. Meanwhile _enter (:1308-1315) already opens an unlocked door by itself.

Kök neden: 'Closed' is treated as an obstacle. Together with doors never being created open, every first visit costs an extra turn or a mechanical refusal, even though _enter proves the engine can walk through an unlocked door.

En küçük düzeltme: In _venue_entry_door, return the door only when `door.get("locked")` is true, and set door['open'] = True for an unlocked one inside commit_location_change just before the move. In _arrive_front:1284, use `verb == "go" and not door.get("locked")` to call _enter. Reword the locked text in _blocked_venue_result as natural prose and call _mark_lock_seen there. Update the tests pinning the old sentence, including test_roadmap_w03.py.

Deneme cümlesi: Tamam, hana gidiyorum

## [likely_fixed] (3) "Kapı niye kilitliydi?" answered with "Burada açıp kapatabileceğin bir kapı görünmüyor": the exact sentence.
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:1486-1498: 'kilit' sets door_action, but _model_query_type_is_plausible is true for 'niye' and grounded_action.plan finds no physical verb, so door_action=False and :1501-1513 is skipped.
- ai-dnd/api/tests/test_natural_door_phrases.py:41-44 pins that resolve_python_world_action returns None for this sentence with no door.
- ai-dnd/dialogue_runtime.py:243-260: in free_v1 a question is not a physical act and goes to the NPC.
- The answer itself depends on the model. Without an NPC the turn is ordinary narration. ai-dnd/game.py:8987 then gives the generic 'Çevrede şimdilik belirgin bir değişiklik olmuyor...' if narration is rejected.
- ai-dnd/game.py:10462-10469, 10482-10487: the validator reads present state, so a past-tense answer with 'kilitli kaldı' about a now-open door is rejected as DOOR_STATE_CONTRADICTION. The form 'kilitliydi' does not match `\bkilitli\b`. Whether this triggers depends on model wording.

Kök neden: The refusal itself was removed for questions. What remains: reasons for a lock are not stored anywhere, so the answer is only as good as the model, and the validator does not separate past from present.

En küçük düzeltme: No change needed for the refusal. Optional: in _fallback_narration, for a door question with no outcome, answer from the door's saved state or admit not knowing ('Neden kilitli olduğunu bilmiyorsun; kilit sağlam görünüyor.') instead of the generic line. Do not script a reason.

Deneme cümlesi: Kapı niye kilitliydi?

## [still_reachable] (3) Sibling of the same refusal: statements and non-opening verbs still reach game.py:1512 when no door is at the location.
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:1486-1488: door_action matches substrings: 'kilit' and 'bak', 'it', 'aç', 'kır' anywhere in the text.
- ai-dnd/game.py:1489: the physical-verb filter runs only if _model_query_type_is_plausible, which needs a question cue (:1289-1301). Statements 'Kapı kilitliydi.' or 'Kapının kilidi kırılmıştı.' have none, so door_action stays True.
- ai-dnd/game.py:1504-1513: the reply is 'açıp kapatabileceğin', even for 'Kapıya bakıyorum', because this branch comes before the look branch at :1620-1622.
- Reached when the model intent is not explore or query, since ai-dnd/game.py:14301-14308 returns first. The intent is model output, but the refusal text is not.

Kök neden: A substring rule from before grounded_action still decides the turn when the sentence has no question cue. A remark about a door is treated as a door operation.

En küçük düzeltme: At game.py:1489 remove the `_model_query_type_is_plausible` gate so the grounded_action.plan physical check always runs: `if door_action:`. A sentence with no physical door verb then returns None and goes to narration or the NPC. Check the test at test_door_tool_acceptance.py for the typed 'target_unknown' absence, which still holds for real attempts.

Deneme cümlesi: Kapı kilitliydi.

## [still_reachable] (4) "Tamam, oraya gidiyorum" after an NPC named a place: the character should go there.
Alan: trace:door-travel

Kanıt:
- ai-dnd/grounded_action.py:565-568: 'oraya' binds only to last_target_id or near_target_id.
- Nothing connects speech to those fields. Writers are grounded_action.py:1018-1019, 1326, 1699, 1745 and game.py:2872 only. ai-dnd/npc_statements.py:434-513 stores references but touches no target memory.
- ai-dnd/grounded_action.py:959-967: _implicit_escort_target needs an open escort or show commitment. 'Kızılhan'a gidebilirsin' creates none (npc_statements.py:87-97).
- ai-dnd/grounded_action.py:2764-2769: result is 'clarify'. The comment says 'with nothing said or seen before', but it also fires right after an NPC named the place.
- ai-dnd/grounded_action.py:2768: options[:4] follow candidates() order (npcs, doors, places, features, references, :399-475), so the just-named reference can be cut off the list shown by _finish_clarification (:2983).
- If last_target_id holds an older door, place or feature, the score-30 bind wins (:806-807, 2612-2613) and the player walks to the OLD target. Stale NPC targets defer at :2762.
- Existing support: reference-kind targets already materialize and move (:1091-1096, 1220-1237, 2581), and 'hana gidiyorum' or 'Marek'in söylediği ...' work (:544-545).

Kök neden: The statement ledger knows what was just said, but the pronoun resolver only reads physical-target memory. The move machinery works; the link from 'oraya' to the ledger is missing.

En küçük düzeltme: Add npc_statements.last_said_place(world, npc_id, max_age_turns=6): walk that NPC's statements newest first and return the first reference_ids entry's reference. In grounded_action.bind, before the last/near fallback at :565, when the clause has a pronoun and verb is go, approach or enter, take flags active_npc_id or last_npc_id and look it up. If ref.location_id is set, use that place candidate (references with a location are skipped at :469). Otherwise use the reference candidate, with score 30. _owned_single_step then owns it (:2581, 2612) and _do_move does the rest. Also move references earlier in the options list at :2768.

Deneme cümlesi: (NPC bir yer adı söyledikten sonra) Tamam, oraya gidiyorum

## [still_reachable] (4) No special sentence: bare forms with no pronoun, such as "Tamam, gidiyorum" or "O zaman gideyim", after an NPC named a place.
Alan: trace:door-travel

Kanıt:
- ai-dnd/grounded_action.py:2738-2741: target None and no commitment.
- ai-dnd/grounded_action.py:2764-2766: clarify needs a pronoun, so it is skipped. :2770 then defers.
- ai-dnd/grounded_action.py:2788-2804: model_ground is after :2770, so a single-step move never reaches it.
- ai-dnd/game.py:8703-8710: legacy travel with no reference becomes 'narrative'. ai-dnd/game.py:14166-14167 gives 'Hangi konuma gitmek istediğini belirt.' if travel survives. The result depends on the classifier, but no path moves the player.
- ai-dnd/grounded_action.py:127: _IMPLICIT_GO is defined; no use of it in this path was found in the read sections.

Kök neden: Implicit destinations are only supported for escort promises, not for 'the place we were just talking about'.

En küçük düzeltme: In the loop at _decide:2738-2741, after _implicit_escort_target returns None, call the same last_said_place lookup. On a hit, set step['target'] to its candidate and step['via_pronoun']=True. Limit it to go/approach with no other object tokens than filler (tamam, peki, olur, o zaman, hadi), and only if the statement is recent.

Deneme cümlesi: Tamam, gidiyorum

## [still_reachable] (4) Fixed refusals near game.py 7945-8007: "doğrulayamam" overwrites what the NPC said about a place.
Alan: trace:door-travel

Kanıt:
- ai-dnd/game.py:8000-8002: 'Yalnızca söylenti olarak {name} adını duydum; varlığını ya da gidilebilir olduğunu doğrulayamam.'
- ai-dnd/game.py:8005-8007: 'Bunu yalnızca doğrulanmamış bir söylenti olarak aktarabilirim; ...'
- ai-dnd/game.py:7951-7954: the same for a hidden-name hit.
- ai-dnd/game.py:7947-7949, 7993-7995: '{name} şu anda kilitli; açıldığını doğrulamadan oraya gitmeni önermem.' This states an unknown lock, against the note at :7973-7974.
- ai-dnd/game.py:7988-7991: an unlisted place is replaced by 'Bildiğim ve şu anda gidebileceğin yerlerden ...'
- Reached at ai-dnd/game.py:18973-18978 in default mode, because experimental_dialogue_session is true for routed NPC speech (:18702-18705, 18818). The gate is local_dialogue.py:347-369: a place word plus öner or tavsiye in the player's line.
- Knock-on: the replaced line is what gets recorded (game.py:7538-7553). The generic refusal at :8006 has no place noun or existence word (npc_statements.py:315-327), so 'Yakında bir han var' leaves no reference for a later 'oraya'.
- Pinned by ai-dnd/api/tests/test_experimental_npc_dialogue.py:1118 and test_default_npc_targeting.py:1171-1239.

Kök neden: NPC speech is post-edited into validator language to protect the 'place is not verified' rule. But references are already attributed and only materialize if the player follows them, so the rewrite protects nothing and breaks both the voice and the later travel.

En küçük düzeltme: In _ground_local_place_recommendation_reply, replace :7998-8008 with `return spoken_text` and :7984-7996 likewise: speech stays attributed, the ledger stores a 'rumor' reference and _materialize_reference makes it real if followed. Keep only the hidden-name guard (:7931-7954), and give it in-character lines that assert no lock and no verification ('Orayı pek bilmem.'). Update the pinned tests, keeping W03's rule that an unknown lock is never spoken. Stage-direction trimming at :8012 stays.

Deneme cümlesi: Bana bu civarda bir han tavsiye eder misin?

## [depends_on_model] (4) free_v1 dialogue campaigns: whether an NPC-named place is remembered at all.
Alan: trace:door-travel

Kanıt:
- ai-dnd/dialogue_runtime.py:197-202: npc_statements.record runs only `if places:`, and places come only from the model's place_proposals (:124, 182-186).
- ai-dnd/dialogue_commitments.py:24-28: a named non-generic place without a known location or proposal raises 'Unbound named place commitment.' Kind 'generic' names pass with no record.
- ai-dnd/api/session_manager.py:225: this mode applies only with AI_DND_DIALOGUE_MODE=free_v1; no start script sets it (ai-dnd/docs/PLAYABLE_DIALOGUE.md:26 documents it).
- ai-dnd/grounded_action.py:2703-2704 and ai-dnd/dialogue_runtime.py:239: with Söyle mode selected the line stays speech by design. The UI default is 'do' (artifacts/ai-dnd-experience/src/pages/game-browser.tsx:1169).

Kök neden: In free mode the ledger is fed by the model's structured proposals rather than by what was shown, so 'oraya' can only follow a place the model also declared.

En küçük düzeltme: In prepare_turn, call npc_statements.record unconditionally and keep the `if places:` block only for resolve_reference. Whether to relax the raise in dialogue_commitments is a separate owner decision; I did not trace how the error is handled for the player.

Deneme cümlesi: (free_v1 modunda NPC yer adı söyledikten sonra) Tamam, oraya gidiyorum

## [still_reachable] (1a) Suggestion buttons are generic: 'Çevreyi gözlemle' and 'Envanterimi gözden geçir' appear whatever the scene is.
Alan: trace:suggestions-freedom

Kanıt:
- artifacts/ai-dnd-experience/src/lib/action-suggestions.ts:35-42: the list always starts with 'observe', including in combat.
- action-suggestions.ts:86-93: 'inventory' is added whenever state.inventory.length > 0.
- action-suggestions.ts:67-76: the only scene input is the first 2 NPC names ('X ile konuş'); features, doors, referents, conversation and quests are ignored.
- action-suggestions.ts:47-51: combat attack suggestions need an inventory item containing 'kılıç', so a fighter with an axe gets only observe and inventory.
- artifacts/ai-dnd-experience/tests/action-suggestions.test.mjs:57 pins 'Çevreyi gözlemliyorum.', so that test must change with the fix.

Kök neden: getContextualActionSuggestions is a fixed template with NPC names filled in. It reads almost none of the GameState it receives.

En küçük düzeltme: In action-suggestions.ts drop the unconditional 'observe' and 'inventory' entries and build the list from scene data (see finding 1c). Keep the 4-item slice. Show 'observe' only when the scene yields nothing else. Replace the 'kılıç' check with active targets on the player's turn.

Deneme cümlesi: Çevreme bakıyorum. (Then open the suggestions in a scene with an NPC and a door: neither 'Çevreyi gözlemle' nor 'Envanterimi gözden geçir' should appear.)

## [likely_fixed] (1b) Are the buttons always visible, how much space do they take, can they be collapsed by default?
Alan: trace:suggestions-freedom

Kanıt:
- game-browser.tsx:315-340: suggestions sit inside <details class='world-experimental'> with no open attribute, so they are collapsed by default under the label 'Deneysel'.
- game-browser.tsx:682 and :1010: that block renders only in WorldTabs, tab DÜNYA, inside the DrawerSheet modal. It is not in the story column.
- Reaching a suggestion means opening the drawer, staying on or choosing DÜNYA, and expanding Deneysel. Clicking one only drafts text and closes the drawer (:1010, :328).
- game-browser.tsx:852-853: the composer is closed by default behind 'Hamle yap', so free typing is always available.
- index.css:253: buttons are min-height 34px with 10px text, flex-wrapped. Up to 4 base items plus up to 6 affordances gives at most 10 buttons (game-browser.tsx:309-314; adventure/projection.py:77).
- game-browser.tsx:341-356: pending_event_decisions buttons are inside the same collapsed 'Deneysel' block, while line 322 disables exploration until a decision is made.

Kök neden: The 'covers the chat' complaint no longer holds, but the fix overshot. The feature is now buried three steps deep under 'Experimental', so 'opens when the player asks' is not met. Scheduled-event decisions are hidden in the same collapsed block.

En küçük düzeltme: Move the .action-suggestions block out of ExperimentalWorldControls into the composer area (StoryColumn, near game-browser.tsx:852) as its own <details>, closed by default, e.g. summary 'Fikir lazım mı?'. Keep the behaviour of drafting text without sending. Render pending_event_decisions outside any collapsed block. No engine change. Update the data-testid expectations in play-screen-ui-regression.test.mjs.

Deneme cümlesi: Hamle yap'a basıp 'Ne yapabilirim?' yazmadan önce öneri satırını aç. (UI check: closed by default, one click to open, chat height unchanged.)

## [still_reachable] (2) Could suggestions be situational without a model call?
Alan: trace:suggestions-freedom

Kanıt:
- Not implemented today, but the data is already in the client. living_world.py:1855-1933 public_scene_projection gives scene.npcs (name, role, appearance), features, referents with addressable_alias, last_activity and player_position.
- lib/api-spec/openapi.yaml:3906 exposes doors on the state.
- game-browser.tsx:845-848 already uses state.conversation.interlocutor.
- game-browser.tsx:311 merges state.campaign_adventures.affordances, but those are fixed labels ('İz ara', 'Odayı incele') from adventure/projection.py:5-11.
- state.quests and state.combat.participant_records are already read by the client.

Kök neden: No model is needed. The pure function just never consumes these fields.

En küçük düzeltme: Extend getContextualActionSuggestions with pure rules, each only if the data exists. A referent with addressable_alias gives 'X'e yaklaş'. A closed door gives 'Kapıyı dene'. An unmentioned feature gives '<feature> bak'. An active interlocutor gives 'Burada iş var mı diye sor' and 'Oradan uzaklaş'. An active quest objective at this location gives its description. Low HP gives 'Soluklan'. Vary with a stable hash of scene.activity_revision so the same scene does not always show the same order. These are grammar over live data, not scripted examples.

Deneme cümlesi: Kapıyı açmaya çalışıyorum. (A closed-door suggestion should disappear once the door is open, and no model call should occur for building the list.)

## [still_reachable] (3a) Where does 'Hamle sonuçlanamadı' come from?
Alan: trace:suggestions-freedom

Kanıt:
- game-browser.tsx:2031 is the only source of the string. It appears only in the submitTurn .catch, meaning a non-503 HTTP failure. A game refusal returned as HTTP 200 never shows it.
- game-browser.tsx:2034 and :152-155: the detail is 'Bu hamleyi şu haliyle gerçekleştiremiyorsun.' even when the server crashed with a 500, so an infrastructure failure reads as an in-game refusal.
- API sources: ai-dnd/api/main.py:1149, 1151 and 1416 (combat 400/409), 1417, 1464, 1470, 1540, 1572 and 1632 (500 engine_error and related), 1062 and 1093 (action_id_conflict), 1263 (session_restore_failed), 602-607 (quarantine).
- Deterministic player-reachable case: ai-dnd/combat_lifecycle.py:112-136. An attack verb whose target cannot be matched by raw name or role raises CombatRequestError invalid_combat_target (400) before the turn runs.
- combat_lifecycle.py:119-123 matches only n.name and n.role, not the public descriptor, so an NPC the player knows by appearance cannot be targeted. Do mode sends target_id null out of combat (action-suggestions.ts:26-28).
- Regex at combat_lifecycle.py:124-126 covers only 'o adam', 'ona' and similar. A 400 no_weapon case exists at :116-117.
- UI text for that case is combat-ui-contract.ts:40 'Bu hedef artık geçerli değil. Görünen rakiplerden birini seç.'

Kök neden: A pre-flight validator treats an unresolved free-text attack as a malformed request and returns an HTTP error, instead of letting the engine resolve or ask in fiction. The UI has only one generic title for every failure.

En küçük düzeltme: In validate_request, when a natural message has no combat_id and no target_id and targets is empty or ambiguous, do not raise. Let the turn continue to the owner. In game.py, match targets against living_world.public_npc_name(npc) and appearance. If exactly one NPC is active or addressed, bind it. If several match, return HTTP 200 with a clarification naming them. Separately, use title 'Bir aksaklık oldu' with a retry message for 5xx in game-browser.tsx:2031-2034 so crashes do not look like refusals.

Deneme cümlesi: Kapüşonlu adama saldırıyorum.

## [unknown] (3b) After the name is said correctly, every action and the 'Konuşmayı bitir' button hit 'Hamle sonuçlanamadı'.
Alan: trace:suggestions-freedom

Kanıt:
- Button path: game-browser.tsx:2281 submits 'Konuşmayı bitiriyorum.' in do mode. It is deterministic at game.py:16496-16523, but only inside run_turn.
- main.py still runs the shared wrapper around it: validate_request (1141), model preflight (1195-1218), plan_living_world_turn (1302), _lore_context_for_turn (1306), and afterwards update_narrative_memory (1545), update_campaign_journal (1605) and serialize_session_state (1616).
- Any persistent exception in those shared steps fails every turn, because the rollback (1237-1248, 1384-1386) restores the same state.
- The attack validator is ruled out for this button: 'Konuşmayı bitiriyorum' has no attack verb (combat_lifecycle.py:112), and the is_attack_decision path does not depend on the name being known.
- Commit fb1cec7 fixed a hidden-name veto in game.py, but that changed target resolution, not an exception path, so it does not prove this complaint is gone.
- main.py:1397 logs the real exception with exc_info, while the player sees only the generic toast.
- The preflight at main.py:1195 also blocks this deterministic button when the model is down, giving the 'Dünya şu an sessiz' title instead. It is not in the MechanicalTurnContext exemption at 1169-1186.

Kök neden: Not determinable from reading the code. The symptom fits one persistent exception in the wrapper shared by all turns, but no such exception was found by inspection.

En küçük düzeltme: Reproduce in the guarded launcher: name disclosure followed by end-conversation, then read the 'Engine turn failed' traceback logged at main.py:1397. Independently, add the end-conversation request to the MechanicalTurnContext condition at main.py:1169-1186 so the button works without the model.

Deneme cümlesi: Senin adın Marek, değil mi? (Use the NPC's actual hidden name, then press 'Konuşmayı bitir'.)

## [depends_on_model] (3c) Free player attempts with no owner get a clarification or a shrug instead of a plausible outcome.
Alan: trace:suggestions-freedom

Kanıt:
- game.py:14531-14542: intent interact or door with no owner returns status 'unresolved' and grounded_action.clarification_text.
- game.py:19269-19275 then shows that text as final, with no model narration.
- grounded_action.py:2458-2468: the text is 'Kime ya da neye yöneldiğini seçemedim (...). Hangisini kastediyorsun?'
- game.py:14522-14530 and 9026-9029: rest and use_item give status 'unsupported' and 'Hangi eşyayı nasıl kullanmak istediğini belirtir misin?', shown verbatim via the status list at 17364-17371.
- game.py:14543-14544: narrative or unknown intents fall through to model narration, with _generic_no_change_response as the fallback (8987-9007): 'Çevrede şimdilik belirgin bir değişiklik olmuyor...'
- There is no general attempt resolver. Skill rolls start only from keyword lists at game.py:1150-1209 or model skill intents (14229-14249). everyday_actions.py resolves only bell, knock, read, follow and perform.
- Which branch runs depends on the intent the model returns (game.py:19197-19243).

Kök neden: The engine has a typed owner list. An attempt classified as interact or use_item with no owner is treated as a question to the player rather than an event in the world.

En küçük düzeltme: In game.py:14531 keep clarification only when grounded_action.plan reports a real ambiguity. Otherwise fall through to the else at 14543 with action 'narrative' and state_changes [], and do the same for use_item and rest. The narrator describes the attempt, and the existing agency guards already prevent state claims. Change the model-failure fallback from 'nothing changes' to a line that reflects the attempt and gives a world reaction. Optional next step: if the model gives a skill, roll it through the existing perform_skill_check branch.

Deneme cümlesi: Masadaki bardağı kapıp duvara fırlatıyorum.

## [still_reachable] (3d) Combat answers free attempts with a system message.
Alan: trace:suggestions-freedom

Kanıt:
- game.py:14117-14135: in active combat any intent outside attack, combat, dialogue, query, unknown and narrative gets 'Bu çatışma sürümünde desteklenen tek mekanik hamle saldırıdır; bu eylem durumu değiştirmedi.'
- game.py:1186-1187 maps 'saklan' and 'gizlen' deterministically to Stealth, and normalize_intent 8609-8619 turns that into intent 'stealth', which is not in the allowed set.
- Neither action_economy.py nor monster_combat.py parses 'saklan' from natural text. action_economy.py:19 lists 'hide' only as a kind.
- game.py:17364-17371: status 'unsupported' is shown verbatim with no narration.
- game.py:14160-14161: normal travel in combat raises CombatRequestError combat_travel, and combat_lifecycle.py:165-169 raises the same at preflight, producing the toast instead of a story reply.

Kök neden: An old version message survives on the combat path. It breaks the fiction and also understates the game, since structured actions such as hide, dash and disengage exist.

En küçük düzeltme: At game.py:14125 map natural intents to existing action_economy kinds where legal, starting with stealth to hide, by passing through action_economy.natural_command. For the rest, replace direct_response with an in-fiction line that keeps the turn. For example, the attempt costs nothing and the enemy presses on. Do not name the engine or its version. For fleeing, convert combat_travel to a disengage or dash proposal rather than an HTTP 400.

Deneme cümlesi: Devrilen masanın arkasına saklanıyorum.

## [still_reachable] (3e) Unknown-name refusal: 'Burada X adıyla tanıdığın biri görünmüyor'.
Alan: trace:suggestions-freedom

Kanıt:
- The 'Selamlar, ismin nedir?' case is fixed: local_dialogue.py:615-619 DISCOURSE_ADDRESSES includes 'selamlar'.
- The rule is still any single capitalised word followed by a comma (local_dialogue.py:683), and only that fixed list is exempt.
- game.py:18119-18123 then returns status invalid_target with final text 'Burada {X} adıyla tanıdığın biri görünmüyor. Kiminle konuşmak istiyorsun?' when target_id is None and there is no combat.
- Do mode sends target_id null (action-suggestions.ts:26-28).
- So 'Anladım, ...', 'Güzel, ...', 'İyi, ...', 'Teşekkürler, ...' or 'Kardeşim, ...' should reach the same refusal. This was traced by reading, not run.
- In free_v1 with an active NPC, dialogue_runtime.resolve_turn (game.py:16527) answers first, so the legacy route is the exposed one. Legacy is the default: session_manager.py:225 reads AI_DND_DIALOGUE_MODE, and only docs/PLAYABLE_DIALOGUE.md:26 sets it.
- api/tests/test_stage10a_narration_intent.py:58-67 pins that an unknown name ('Elara, ...') must not use the bartender's memory.

Kök neden: Any capitalised first word before a comma is assumed to be a person's name. The exemption is a list, so each new Turkish discourse word is a new bug.

En küçük düzeltme: In unresolved_named_address, return a name only if it matches a registered NPC or known speech reference that is absent here, so the reply can be 'X burada değil'. Otherwise return None and let the active conversation continue. If the 'Elara' test must stay exact, keep the refusal only for no-active-interlocutor and rephrase it naturally, and for an active conversation let the NPC answer with no memory access, which satisfies that test's intent. Decide with the test owner, since this loosens a pinned case.

Deneme cümlesi: Anladım, peki burada işler nasıl gidiyor?

## [depends_on_model] (3f) In free_v1, an NPC reply with a bad proposal loses the whole turn instead of being repaired.
Alan: trace:suggestions-freedom

Kanıt:
- dialogue_runtime.py:182-190: place name mismatch, prepare_place, dialogue_jobs.prepare and dialogue_commitments.validate all raise DialogueResponseError on a bad proposal or lexical tripwire.
- api/main.py:1408-1412 turns that into 503 invalid_dialogue_response after rollback; the player sees 'Dünya şu an sessiz'.
- dialogue_commitments.py:25-38: tripwires include an unknown named place, 'bir iş var' with no job, and a spoken reward mismatch.
- dialogue_jobs.py:60 raises 'This job is already closed.' when the model re-proposes a refused job. dialogue_jobs.py:61-62 raises when job capacity is full.
- game.py:18730-18733 notes the legacy path has fallbacks, so this is specific to free_v1.
- dialogue_runtime.py:310: the model label there is hard-coded to 'qwen3:8b'. Whether the adapter overrides this was not traced.

Kök neden: Authority checks are correct, but the failure mode is reject-whole-turn. The spoken line is usually usable with the proposal removed.

En küçük düzeltme: In prepare_turn, wrap each proposal: on DialogueResponseError from prepare_place or dialogue_jobs.prepare, drop that proposal and keep the speech if the speech does not name it. If it does, trim the sentence with the existing npc_speech_boundary sentence filters. For dialogue_commitments.validate, repair by removing the offending clause. Raise only if nothing speakable remains.

Deneme cümlesi: Daha önce sorduğum o iş hâlâ duruyor mu, ne dersin?

## [still_reachable] (3g) Mechanical wording in deterministic replies ('doğrulanamadı', 'biraz daha araştır').
Alan: trace:suggestions-freedom

Kanıt:
- game.py:18114 'Bu kişi önerisi mevcut kampanya durumuyla doğrulanamadı; sahnede değişiklik yapmadım.'
- game.py:12889 'Bu seyahat hedefi doğrulanamadı; konumun değişmedi.'
- game.py:18311 'Dükkânda sana sunulmuş bir ürün ya da fiyat yok; bu yüzden alışveriş yapamıyorsun.'
- grounded_action.py:2657 'Aktarılan NPC sözü oyuncunun hareketi sayılmaz.'
- grounded_action.py:1758 'Bunu inceleyemiyorsun.'
- timed_gameplay.py:447 'Bu yol fiziksel olarak kapalı; başka bir kayıtlı rota seçebilirsin.'
- interaction_adventure.py:972-975 'biraz daha bakınmak ya da birine sormak yeni bir kapı açabilir', which is the 'biraz daha araştır' pattern.
- Door refusal 'Burada açıp kapatabileceğin bir kapı görünmüyor.' (game.py:1512) now needs a physical step (1488-1498), so 'Kapı niye kilitliydi?' should not hit it.
- game.py:1499-1500 still answers door-break claims without a check.

Kök neden: System receipts are used as player-facing text. Which lines are reachable depends on the route: 18114, 12889 and 972 depend on model proposals, while 18311 is deterministic when shops exist.

En küçük düzeltme: Rewrite only these strings as world description, with no 'doğrulanamadı', 'kayıtlı' or 'sayılmaz', and keep statuses unchanged. Add those words to a test that scans deterministic response constants. For 18311, use a keeper or scene reaction instead of explaining the economy system.

Deneme cümlesi: Tezgâhtaki bıçağı satın alıyorum.

## [still_reachable] (4a) People with their own goals: is there an NPC goal or offscreen progress system?
Alan: trace:suggestions-freedom

Kanıt:
- local_dialogue.py:104-214: immediate_goal is static flavour such as 'Günlük işlerimi bitirip eve dönmek.'
- local_dialogue.py:738: persona goal default is 'Günlük işlerini tamamlamak ve kendi hayatını sürdürmek.'
- dialogue_runtime.py:80 leaves immediate_goal out of the facts sent to the model. Only persona_context may carry a goal.
- scheduled_events.py:571-585: default routines are one work/rest loop, seeded only in free_v1 (dialogue_runtime.py:394, is_enabled check at scheduled_events.py:574).
- scheduled_events.py:535-568 moves location and activity only; the routine has no goal or progress field.
- scheduled_events.py:144 register_event is the real offscreen clock, but production callers are adventure/deadlines.py:22 and table absence (scheduled_events.py:221, 267), plus validated definitions (:139).
- adventure/deadlines.py:37-68 only closes a quest as missed, with effects=() at :28.
- incidents/horizon.py:1 says 'The generator never simulates distant places.', and :11 says time alone is not a trigger.
- incidents/commit.py:127-149: left-behind incidents become IGNORED or EXPIRED with no follow-on.
- incidents/threads.py:1: threads are an id index only.
- living_world.py is scene state and carries no NPC goal logic. LIVING_WORLD_V2_GAMEPLAY_CONTRACT.md:39-41 says consequence-bearing events are not enabled.
- Narrow reactive pieces do exist: dialogue_runtime.py:364-392 (relationship notes, one deception motive, injury observation).

Kök neden: NPCs have schedules, not aims. Nothing advances a person's intention, and a closed incident or quest produces no later state. Links between events therefore exist only as model memory.

En küçük düzeltme: Without new infrastructure, add a small saved 'pursuit' on an NPC: goal text from the existing issue/immediate_goal (local_places.py:345), a due time, and one effect. Use scheduled_events.register_event with visibility hidden and an npc_location or activity effect. It then flows through existing player_observed handling when the player returns. Create pursuits from real events only: a refused offer, an expired incident, or a kept or broken commitment. Include immediate_goal in dialogue_runtime.py:80 facts. This is the only item here needing a feature rather than a patch, and it should not script any owner example. Routines also need to run outside free_v1 or free_v1 must become the default.

Deneme cümlesi: Bugün neyin peşindesin, ben gidince ne yapacaksın?

## [still_reachable] (4b) Refusing an NPC offer: does the world stay consistent and does the person carry on?
Alan: trace:suggestions-freedom

Kanıt:
- dialogue_commitments.py:60-62: a job offer card says only 'Görev günlüğünden kabul edebilirsin.' Accept and refuse exist as journal buttons (quest-journal-section.tsx:89, :99; game.py:19735).
- In free_v1 a spoken 'hayır' goes to resolve_turn and prepare_turn, which never touches the quest (dialogue_runtime.py:228-272, 172-225). The quest stays DISCOVERED.
- dialogue_commitments.py:15 keeps that open job in allowed_jobs, so the NPC can keep discussing it.
- scheduled_events.py:543-546, 553: the giver of any AVAILABLE, DISCOVERED, ACTIVE, BLOCKED or accepted quest is pinned, so a refused giver cannot leave or follow a routine while the job stays open.
- adventure/play.py:115-119 arms a 3600 second deadline via settle_session (adventure/deadlines.py:8). If the window is marked missed, it closes as FAILED (:37-55). Whether that closes reliably for a job was not verified.
- After that close, a re-proposal of the same job raises at dialogue_jobs.py:60 and gives a 503 (main.py:1408).
- Legacy mode: interaction_adventure.py:936 recognises only 'reddediyorum', 'guvenmiyorum' and 'kabul etmiyorum'; 'istemiyorum' and 'ilgilenmiyorum' are not matched.
- interaction_adventure.py:1264-1269 abandons a thread only if a thread is bound via model-supplied thread_id (:1158).
- interaction_adventure.py:1277-1278: the reply is 'Kararını açıkça ortaya koyuyorsun. Sonraki adımın hâlâ sana ait.', with no NPC reaction or relationship note.
- The transition to ABANDONED itself is legal and clean (adventure/transitions.py:16, adventure/play.py:39-52).

Kök neden: Refusal exists as a UI quest transition, not as a spoken act. Saying no changes nothing, the giver stays pinned, and no consequence or NPC reaction is produced.

En küçük düzeltme: In dialogue_runtime.observe_turn or just before _generate_reply, detect a plain refusal when this NPC has exactly one DISCOVERED dialogue job and call adventure_play.abandon, adding relationships.note(world, npc_id, 0, 'declined:'+quest_id). Abandoned status already releases the pin at scheduled_events.py:544. Let the model see 'player_declined' in context so the NPC answers in character. Treat a closed job in dialogue_jobs.py:60 as a dropped proposal, not an error. Extend the refuse regex in interaction_adventure.py:936 with 'istemiyorum' and 'ilgilenmiyorum', and replace line 1278 with the NPC's reaction. Negation false positives need test cases.

Deneme cümlesi: Hayır, bu işle ilgilenmiyorum, kendin halledersin.

## [depends_on_model] (5) Does the game write the player's feelings or actions?
Alan: trace:suggestions-freedom

Kanıt:
- Legacy narration is guarded. game.py:9944-10081 rejects INVENTED_PLAYER_ACTION, game.py:10083-10087 rejects INVENTED_PLAYER_MENTAL_STATE, game.py:10118-10124 rejects forced actions, and game.py:12979 trims the sentence.
- The free_v1 path has no such guard. dialogue_runtime.py:213 shows stage_direction and spoken_text directly, and :219 marks safety 'accepted' without calling finalize_narration.
- The only instruction there is the prompt at :293 'Oyuncu yerine hareket, karar veya başarılı mekanik sonuç üretme'.
- _append_initiative at :439 is also unguarded.
- intent_contract.py:101 unauthorized_player_decisions has no production caller; the only uses are in api/tests/test_roadmap_w09.py.
- Deterministic lines that decide for the player: interaction_adventure.py:1176 'Bu sorunun peşini bırakmamaya karar veriyorsun.' and :1278 'Kararını açıkça ortaya koyuyorsun.'
- The system prompts forbid it, but leak-through is model behaviour.

Kök neden: The safety layer was built for the legacy narrator. The newer speech path relies on the prompt alone, and the ready-made checker was never wired in.

En küçük düzeltme: In dialogue_runtime.prepare_turn, run intent_contract.unauthorized_player_decisions on stage_direction. If above 0, blank stage_direction and keep the speech (repair, not reject). Apply the same check to the initiative line. Rewrite interaction_adventure.py:1176 and :1278 so they reflect the player's own quoted words without stating a decision or feeling.

Deneme cümlesi: Hedefim bu kasabadaki en güçlü lordun koruması olmak.

## [likely_fixed] (1) "Selamlar, ismin nedir?" read as an address to someone called Selamlar
Alan: trace:dialogue-context

Kanıt:
- ai-dnd/local_dialogue.py:615-619 DISCOURSE_ADDRESSES contains "selamlar", "merhabalar", "gunaydin", "hey", "dostum", "pardon" and others
- ai-dnd/local_dialogue.py:683-689 unresolved_named_address takes the first capitalized word before a comma and returns None for words in that set, so the exact sentence no longer reaches the refusal
- ai-dnd/api/tests/test_intent_response_consistency.py:852-856 pins Selamlar and six other words; the string entered the file in f6f3f96 (2026-10-23)
- STILL OPEN, same class: the set is a denylist. Any other capitalized word plus comma is treated as a person, e.g. Olur, Teşekkürler, Anladım, Sağol, Güzel, Kardeşim, Abi, Hocam, Efendim. "olur" is not in the set, although 920e623 was titled '"Olur," read as a name'
- ai-dnd/game.py:18119-18123 hard refusal in every interaction mode when target_id is None and there is no combat, even during an active conversation; status invalid_target, is_final=True, text 'Burada X adıyla tanıdığın biri görünmüyor. Kiminle konuşmak istiyorsun?'
- ai-dnd/game.py:6081-6082 the same check returns status none from resolve_npc_reference, and game.py:17985 blocks the sole-NPC fallback, so free_v1 also gets no NPC (dialogue_runtime.py:265-269 returns None) and falls through to the same refusal
- Traced by reading only; no test was run

Kök neden: The exact report is covered by a word list. The design is still 'unknown capitalized word before a comma means an absent person, so refuse', and that fails on any Turkish discourse word not listed.

En küçük düzeltme: In game.py:18120, do not refuse when an interlocutor is focused (focused_npc_before_targeting is not None) or one NPC is the sole candidate. Let the turn continue to that NPC so it can answer naturally, including 'Garrick mi? Burada öyle biri yok.' Keep a refusal only when nobody can answer. Add common words to DISCOURSE_ADDRESSES (olur, tesekkurler, tesekkur, sagol, anladim, guzel, abi, kardesim, hocam, efendim, ahbap). test_unknown_explicit_address_does_not_reuse_active_interlocutor must keep its 'not Lysa:' intent, so only the reply route changes, not who is addressed as Garrick.

Deneme cümlesi: Teşekkürler, ismin nedir?

## [depends_on_model] (2) Talking about an inn, "İsmi nedir?" answered with the NPC's own name (topic tracking)
Alan: trace:dialogue-context

Kanıt:
- ai-dnd/local_dialogue.py:495-504 regex includes bare "ismi"/"adi", so a third-person 'its name' is classified npc_identity
- ai-dnd/game.py:1323-1327 and 1369-1373 _detect_query_type does the same and returns npc_identity whenever npc_target is active and no place or NPC is named
- ai-dnd/local_dialogue.py:671-676 is_identity_only_question only fullmatches adin/adiniz/ismin/isminiz, so 'ismi nedir' does NOT take the deterministic shortcut at game.py:18493. All _handle_query call sites were checked (14148, 18157, 18461, 18471, 18494); none answers the exact sentence on the dialogue route
- The turn therefore reaches the speech model at game.py:18821-18836 (free_v1: dialogue_runtime.py:271, before all of this). The answer comes from the model
- ai-dnd/game.py:7778-7793 _is_short_followup uses a closed word set without ismi/adi/sahibi/nedir, so 'İsmi nedir?' is not a follow-up: game.py:7803-7809 adds no 'answer about your previous reply' line, and perspective plus recent_player_utterances stay in the context (game.py:7757, 7770)
- ai-dnd/game.py:7752 and interaction_adventure.py:368-407 conversation_focus exposes only a door-lock subject; a place, inn or person named in the last reply has no structured topic. Only raw last_exchange text carries it (game.py:7766)
- ai-dnd/interaction_adventure.py:848-860 with game.py:18887-18903: if the model proposes meaning=identity, Python answers with the NPC's ROLE as a deterministic line; also model-triggered
- Related: 'Hanın ismi nedir?' with a registered, known place is classified location at game.py:1363, and game.py:18153-18169 answers 'Bulunduğun yer: X.' or a place hint, outside 'say' mode

Kök neden: There is no topic model. Third-person possessive questions are classified as questions about the addressee, and the only follow-up signal is a word list that misses them. A small model gets a recent-subject hint only as free text, so it can drift to itself.

En küçük düzeltme: Make ismi/adi count as identity only when an NPC is explicitly named, in both local_dialogue.py:496 and game.py:1324. Extend _is_short_followup with a bounded third-person form such as ^(ismi|adi|sahibi|yeri|kimin|nerede)( ne| nedir)?$ so the existing recap and 'answer about that reply' line fire. No new state and no new rule are needed. Keep second-person ismin/adin unchanged.

Deneme cümlesi: İsmi nedir?

## [still_reachable] (3) "Burada nerede iş bulabilirim?" answered off topic
Alan: trace:dialogue-context

Kanıt:
- ai-dnd/local_dialogue.py:449-456 the sentence classifies as local_work
- ai-dnd/interaction_adventure.py:940 hint 'generate' matches only 'is var mi', 'is ariyorum', 'bir is', so this phrasing gets no interaction proposal and no job generation
- DO mode (UI default), ai-dnd/game.py:18543-18578: fixed line '{npc}, “Şu an sana önerebileceğim belirli bir iş yok,” der.' for every NPC, every time, without consulting the model. On topic but mechanical; no-NPC variant at local_dialogue.py:602-603 'Bu çevrede şu an belirli bir iş teklifi görünmüyor. Yerel halka gündelik iş olup olmadığını sorabilirsin.'
- SAY mode, game.py:18545 skips that answer. With speech disabled, game.py:15105-15122 returns the same denial via local_dialogue.py:569-573; with AI_DND_NPC_SPEECH=1 the turn goes to the speech model
- Source of the scratch reply: local_dialogue.py:157 'Tezgâhın köşesindeki küçük çizik yıllardır orada.' is projected by local_dialogue.py:250-297 and appended to shareable_profile_facts at game.py:7704-7706 on every speech turn. The context has no job or work data, so that is the most concrete fact a model can reach for. Picking it is model-dependent; the feed is deterministic
- free_v1 differs: dialogue_runtime.py:80 relevant_background excludes personal_detail, job_targets are supplied (line 92) and the prompt forbids irrelevant personal detail (line 290). The default launcher does not set AI_DND_DIALOGUE_MODE (session_manager.py:225, start_local.ps1), so a default campaign is legacy

Kök neden: Two owners, both weak. DO mode answers from a canned denial with no knowledge of the NPC, and SAY mode gives the model a random personal detail but no work facts, so it answers with what it has.

En küçük düzeltme: Gate game.py:7704-7706 so personal_detail is added only when personal_question_kind is personal_context (pass a flag from the 18824 call). In game.py:18548, use the canned line only when npc_target is None and let a present NPC take the speech route. Add 'is bul\w*|is nerede' to the generate hint at interaction_adventure.py:940 so the existing proposal path can run. test_npc_persona_context.py and test_stage_profile_contract.py touch this detail and may need review.

Deneme cümlesi: Burada nerede iş bulabilirim?

## [depends_on_model] (4) "Bu çevrede bar var mı?" should get a human answer based on what the NPC knows, not "doğrulayamıyorum"
Alan: trace:dialogue-context

Kanıt:
- 'bar' is unknown to the venue vocabulary: ai-dnd/living_world.py:130-134 _TAVERN_TERM (taverna|meyhane|han|tavern|inn), living_world.py:139-144 _VENUE_RE, and npc_statements.py:39-40 PLACE_NOUNS have no bar. is_tavern_search (living_world.py:725-739) is therefore false and the owner answers at game.py:15041-15080 do not run
- Exact sentence: '?' makes it dialogue (game.py:952), so with a present NPC it goes to the speech model at game.py:18821. No deterministic 'doğrula' line exists on this route
- ai-dnd/local_dialogue.py:347-369 is_local_place_recommendation_request is false here (no öner/tavsiye word), so _ground_local_place_recommendation_reply is skipped. The 'doğrulayamam' lines therefore need a recommendation wording, e.g. 'Buralarda iyi bir meyhane önerir misin?' or a sentence with yer/mekan
- When that wording is used in a legacy campaign, game.py:7951-7954 and 8000-8008 REPLACE the NPC's line with 'varlığını ya da gidilebilir olduğunu doğrulayamam' if the model names a place that is not a canonical local option. game.py:18973 still applies this; it is still_reachable
- ai-dnd/game.py:7745-7775 the legacy speech context has no place list (the options exist only at game.py:7839), so the NPC cannot say 'köşedeki han var'. free_v1 has available_places (dialogue_runtime.py:86-94)
- A malformed or rejected model reply falls to interaction_adventure.immersive_unknown (game.py:19045, 19072): acceptable tone, but one of four fixed lines that ignores what the NPC knows

Kök neden: The NPC is not given what it knows about nearby places, and a guardrail rewrites an unverified place into verification vocabulary spoken by the NPC. 'Bar' also misses the venue words, so the working owner reply is skipped.

En küçük düzeltme: Add bar/pub/birahane forms to _TAVERN_TERM with word boundaries and to PLACE_NOUNS (check that barmen does not match). Add _local_place_recommendation_options(npc_target, world_state) to _experimental_npc_dialogue_context so the NPC can use real places. Rewrite game.py:7952-7953, 7994-7995, 8001-8002 and 8006-8007 in human voice, e.g. 'Öyle bir yer duydum ama kendi gözümle görmedim.' test_experimental_npc_dialogue.py:1118 pins the old text and must change with it.

Deneme cümlesi: Bu çevrede bar var mı?

## [still_reachable] (4b) Inventory of deterministic mechanical replies a player can hit in dialogue
Alan: trace:dialogue-context

Kanıt:
- VERIFICATION WORDING: game.py:7952-7953, 8001-8002, 8006-8007 'doğrulayamam'; game.py:7948-7949, 7994-7995 'açıldığını doğrulamadan oraya gitmeni önermem'; game.py:18114 'Bu kişi önerisi mevcut kampanya durumuyla doğrulanamadı; sahnede değişiklik yapmadım.' (the worst one: system voice); grounded_action.py:2145 'açık olduğunu doğrulayabildiğin bir yer bulamıyorsun'; timed_gameplay.py:492 'Yönünü doğrulayamadın'
- META/SYSTEM VOICE: game.py:18092-18094 'Bu kişi yalnızca bu kampanyanın mevcut sahnesine eklendi.'; game.py:18311 'Dükkânda sana sunulmuş bir ürün ya da fiyat yok'; game.py:18533 'Bu bölgede sana sunulmuş etkin bir görev yok.'; game.py:18531 'Üstlenebileceğin işler şunlar:'
- 'KEEP RESEARCHING' WORDING: interaction_adventure.py:973-974 'Çevrende bu düşünceyi destekleyen bir iz göremiyorsun; biraz daha bakınmak ya da birine sormak yeni bir kapı açabilir.' (used by _unverified flows and finish_conversation paths when npc is None); game.py:11113-11114 'doğrusunu öğrenmek için biraz daha dinlemen gerekecek'; game.py:11117-11118 and 11121-11122 distance and ruler rumor lines; local_dialogue.py:602-603 'Yerel halka gündelik iş olup olmadığını sorabilirsin.'; timed_gameplay.py:639 'Hangi yeri araştırmak istediğini belirt.'
- FIXED 'NO INFO' NPC LINES: interaction_adventure.py:950-959 four immersive_unknown lines (reached from game.py:11151, 11166, 11169, 17438, 17478, 18874, 19045, 19072); game.py:11162-11163 'kesin bir şey söyleyemem'; game.py:15140-15141 'Yolların ne durumda olduğunu bilemem'; game.py:15078 'Yakınlarda bildiğim belirli bir han yok'; game.py:15101 'Şimdilik göze çarpan özel bir şey yok'; game.py:15130 'Fena değil, teşekkür ederim'; game.py:15148 'Merhaba'
- WORK LINES: game.py:18552; local_dialogue.py:571, 576-577, 602-603, 608
- TARGET/CLARIFY REFUSALS: game.py:18123 and 18130 'Kiminle konuşmak istiyorsun?'; game.py:18644 'Böyle bir konuşmayı kimin yaptığını kestiremiyorsun'; game.py:18642 'şu anda burada değil'; game.py:15255; game.py:18414 and 18412 'adını bilmiyorum' (natural); game.py:9031 'Karşındaki kişi sözünü dinliyor, ancak buna ekleyeceği bir şey bulamıyor.'; game.py:9032 'ne yapmak istediğini biraz daha belirgin anlatabilirsin'; speech_clarification_line at game.py:6689 and 19100
- UI empty state, not dialogue: artifacts/ai-dnd-experience/src/pages/game-browser.tsx:602 'Henüz doğrulanmış bir bilgi yok.'
- Scope: free_v1 campaigns bypass most of these when an NPC resolves, because dialogue_runtime.resolve_turn runs first at game.py:16526; legacy campaigns (launcher default) hit them
- The list comes from targeted greps plus reading the dialogue path, so it may not be exhaustive

Kök neden: Each guardrail ships its own canned string, written for correctness rather than voice. When Python rejects model text it substitutes authority wording instead of letting the NPC stay in character.

En küçük düzeltme: Wording only, no routing change, in priority order: 18114, 18094, 7952/8001/8006, interaction_adventure.py:973, 11113, 18311, 18533, grounded_action.py:2145. Remove 18094 entirely (it adds nothing for the player). Tests pin some of these strings (test_campaign_api.py, test_experimental_npc_dialogue.py) and need matching updates.

Deneme cümlesi: Buralarda iyi bir meyhane önerir misin?

## [unknown] (5) After a name is given, every action including end conversation fails with "Hamle sonuçlanamadı"
Alan: trace:dialogue-context

Kanıt:
- The title comes only from artifacts/ai-dnd-experience/src/pages/game-browser.tsx:2031, for any failure that is not 503 and not deadline expiry. That means a 500, 4xx or client-side exception, not a model refusal; 503 shows 'Dünya şu an sessiz'
- No name-linked crash found in the code read. remember_explicit_player_name (local_dialogue.py:699-715) and record_npc_interaction (game.py:6364-6418) write entries that pass campaign_validation.py:118-129. Journal rename is handled (campaign_journal.py:646-656). Narrative memory stores the name safely (narrative_memory.py:274-279, 415-421). TurnOutcome truncates to its limits (main.py:232-239). game._validate_save_payload has no check on name_known_to_player
- End conversation itself is deterministic with no model call (game.py:16496-16523, UI at game-browser.tsx:2281) and is tested (test_wave3_conversation_ux.py:105, test_default_focus_acceptance.py:85). If it fails, the fault sits in the shared pipeline: main.py pre-run gates, autosave, or the client
- The sticky mechanism was real and is mostly closed. HANDOFF_ARSIV_20261030.md:53 records that rolled-back engine_error, narrative_memory_error and journal_error 500s left the pending action open with no way out but retry, which blocks every later move. HANDOFF_ARSIV_20261030.md:61 and main.py:1117-1131, 1417, 1572, 1642 show these now use refuse_before_commit with not_applied=true, closed by game-browser.tsx:2001-2011 (449b0fa, 66410ae, 2026-10-27)
- Still-open sticky cases by design: session_restore_failed 409 and quarantine (main.py:190, 1252-1263, 602-607), campaign_stale from assert_current (main.py:1133-1138), autosave persistence_error 500 (main.py:1737-1740). These keep pending, so a later new move gets 'Önceki hamle henüz doğrulanamadı' (game-browser.tsx:133-136, 1834-1836) and only Retry shows 'Hamle sonuçlanamadı'
- A repeat of that exact title on each NEW move fits a repeating refused 500 better, or a client exception: the .catch at game-browser.tsx:1994 also receives any error thrown in the .then after closePending at 1908, so a committed turn could display this title. No such throw was proven
- Also reaches this title: require_player_can_act raises plain ValueError (game.py:3048-3058), which becomes 500 engine_error at main.py:1417. Not name-related
- The brief itself says listed experiences may no longer be broken. Reproduction needs the server log line for the failing turn (error_type at main.py:1398) and the response code; none exists in this worktree for that session

Kök neden: Not established. The likely historic mechanism was one rolled-back server error leaving a pending action that blocked all later moves, including the end-conversation button; the name was probably the turn on which that failure happened, not the cause. That is inference, not proof. What triggered the original failure is unknown.

En küçük düzeltme: Do not change engine code until reproduced. Add one HTTP regression test in the style of test_default_focus_acceptance.py: name exchange, then a normal action, then 'Konuşmayı bitiriyorum.', asserting 200 and conversation_ended. Small UI hardening: in game-browser.tsx:2029-2034, show the server detail.code (or a distinct title for a post-commit client error) so the next report identifies the branch. Fix the separate bug in the next finding as well, since it creates false name turns.

Deneme cümlesi: Adım Kadir.

## [still_reachable] Adjacent finding for (5): ordinary sentences are read as the player's name
Alan: trace:dialogue-context

Kanıt:
- ai-dnd/local_dialogue.py:409-417 the patterns run with re.IGNORECASE and the name group is any word. Pattern 3 `\bben\s+NAME\s*[,!.]?\s*$` matches 'Ben gidiyorum.' and 'Ben çıkıyorum.' Pattern 1 `(adım|ismim)\s+NAME` matches 'Bir adım atıyorum.' and 'Geri adım atıyorum.'
- Only ne/nedir and adim/ismim are excluded (local_dialogue.py:427-431)
- game.py:948 makes such a sentence dialogue; with an NPC resolved, game.py:18441-18489 replies 'Memnun oldum, gidiyorum. Adını hatırlayacağım,'
- free_v1 also stores it: dialogue_runtime.py:193-195 writes 'Benim adım gidiyorum.' into NPC memory
- Regex behaviour is certain from reading. Whether a movement owner intercepts a given sentence first (timed_gameplay at game.py:17565, scene plan at 17682) was not traced for each phrasing

Kök neden: The first-person disclosure patterns accept any word as a name, including conjugated verbs, because case-insensitive matching removes the capitalization signal the first regex relies on.

En küçük düzeltme: Require a name-shaped token in patterns 1 and 3: drop re.IGNORECASE for the name group, or reject finite verb endings (-iyorum, -uyorum, -ıyorum, -üyorum, -acağım, -eceğim) after matching. Keep lowercase 'adım kadir' working for pattern 1 via the verb-ending check.

Deneme cümlesi: Ben çıkıyorum.
