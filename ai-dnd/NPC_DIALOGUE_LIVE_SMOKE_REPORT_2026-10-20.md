# NPC Dialogue and Scene Investigation — Live Smoke Report

**Date:** 2026-10-20

**Source commit:** `85b64119fc8b9b2416eac2453c383d6143db5402`
**Branch:** `fix/npc-default-dialogue-path-20261020`

## Safety and scope

- Ran through the FastAPI campaign/turn routes with an in-process ASGI client and temporary SQLite stores.
- Used synthetic Neverwinter campaigns and a synthetic NPC; no private campaign, personal save, or audio was read or modified.
- Authenticated Replit Ollama preflight succeeded and `qwen3:8b` was available.
- `AI_DND_NPC_SPEECH=0`; no experimental NPC-speech mode was enabled.
- Fixture setup made zero model-generation calls. No secret values, prompts, raw headers, or audio were written to this report.

## Live-turn budget and outcome

The limit was six processed game turns and ten model-generation calls. The run used **six HTTP 200 game turns and four Qwen generation calls**. Four read-only model-list requests were made separately for preflight; they are not generation calls. There was also one HTTP 503 harness request; it returned before a game turn advanced and made zero model calls. That harness issue was a missing `list()` forwarding method and was corrected before the successful second scenario.

The four generation phases, from the engine's per-turn telemetry, were:

1. Processed turn 1: narration.
2. Processed turn 2: intent, then narration.
3. Processed turn 3: zero calls; travel was blocked by the locked door.
4. Failed HTTP request: zero calls and no turn advancement.
5. Processed turn 4: narration.
6. Processed turns 5 and 6: zero calls; travel and inspection handling were deterministic.

### Full player-facing responses

#### Processed turn 1 — greeting

**Player:** “Marek, merhaba. Bugün burada neler oluyor?”

**Response:**

> Marek, biraz şaşkınlıkla sana bakar ve sonra kahkahalarla güler. "Merhaba!" diye selamlar. "Bugün çok şey olmamış gibi görünüyor. Sadece sokakta dolaşıyorum ve işlerimi hallediyorum." Duygusal bir tonla konuşurken, gözleri sokağın diğer ucuna uzanır. "Şehirde her zaman bu şekilde geçiyor; kimse özel bir şey yapmıyor. Sen ne arıyorsun?" Sorusunu sorarken, eli kılıcına kaynar. Bu sorduğun soruya cevap vermek için hazırlandığına işaret eder. Artık onunla daha fazlasını konuşmak istiyorsan, nedenini açıklayabilirsin. O da seninle ilgilenebilir.

**Telemetry:** Qwen narration accepted; one narration call. The NPC speaks directly, but the answer is overlong and includes unnecessary narrator framing.

#### Processed turn 2 — first place recommendation

**Player:** “Bu şehirde gidip görebileceğim sakin bir yer önerir misin?”

**Response:**

> Marek: "Marek Hanı'na gidin. Sokağa açılan, sade ve sıcak bir han. Gündelik işlerinizi hallederken biraz dinlenmeniz için uygun."

**Telemetry:** Qwen intent and narration accepted; two generation calls. The recommendation named the canonical local venue.

#### Processed turn 3 — travel to that recommendation

**Player:** “Önerdiğin Marek Hanı yönüne gidiyorum.”

**Response:**

> Marek Hanı Kapısı kapalı. İçeri geçemezsin.

**Telemetry:** Python resolved this as travel; zero model calls. The locked door correctly prevented arrival, so this turn did not establish the scene for an inspection.

#### Failed harness request — not a game turn

The first attempt to start the second temporary scenario returned HTTP 503 because its test-local client wrapper lacked `list()`. It made zero model calls, did not advance campaign state, and returned no player-facing narration. The wrapper was corrected before continuing.

#### Processed turn 4 — second place recommendation

**Player:** “Marek, bu şehirde kısa bir mola vermek için hangi yere gitmemi önerirsin?”

**Response:**

> Marek: "Fenra Hanı'na gidin. Sokağa açılan, sade ve sıcak bir han. Biraz dinlenmek için ideal."

**Telemetry:** Qwen narration accepted; one narration call. The canonical recommendation was identified.

#### Processed turn 5 — travel to the recommendation

**Player:** “Önerdiğin Fenra Hanı yönüne gidiyorum.”

**Response:**

> Fenra Hanı konumuna vardın.

**Telemetry:** Python completed travel to canonical location `location_001`; zero model calls. For this isolated test, the temporary fixture’s canonical venue door was open.

#### Processed turn 6 — inspect the same canonical scene

**Player:** “Buradaki Fenra Hanı Kapısı kilidini dikkatlice inceliyorum.”

**Response:**

> Yakınında incelenecek bir kapı yok.

**Telemetry:** The player remained at `location_001`, but the response contained no concrete finding and no authoritative inspection result (`action_result` was null). This behavior **did not pass**. The six processed-turn limit was reached, so no further live attempt was made.

## Bounded Python selector results

All selectors below ran against the source at the commit listed above.

| Selection | Selected | Ran | Passed | Failed | Skipped |
|---|---:|---:|---:|---:|---:|
| `run_tests.py --suite release` | 25 gates | 511 unittest cases + 12 Combat V1 checks | 519 | 4 | 0 |
| `run_tests.py --suite prototype` | 2 modules | 42 | 42 | 0 | 0 |
| Combat V1 additional repetitions beyond the release run | 4 runs | 48 checks | 48 | 0 | 0 |
| Focused regression invocations | 18 | 18 | 18 | 0 | 0 |
| **Total executions (including repeats and overlapping focused tests)** | — | **631** | **627** | **4** | **0** |

Combat V1 was run once by the release selector and four more times: 12 checks per run, 60 successful executions total. The same 12 checks passed on all five runs:

- Normal hit (d20=15, AC=10)
- Miss (d20=5, AC=20)
- Natural 1 = auto miss (even with AC 0)
- Natural 20 = critical hit
- Zero HP from lethal NPC damage -> dead
- Wrong location - NPC in different location
- No valid target
- No weapon in inventory
- Forged / detached NPC dict
- Full pipeline cross-location attack
- Authoritative prerequisite refusal (`distance_unknown`)
- Authoritative prerequisite refusal (`invalid_combat_target`)

The 18 focused invocations were the 14 API/ownership selectors and four narration regressions: accepted narration precedence, mental-state sentence repair, safe remainder preservation, and mental-state reason-code calibration. All passed.

The four release failures are the same test IDs previously reproduced on the PR22 baseline; no new release failure remains:

- `test_building_detail_inquiry_does_not_start_a_new_tavern_search`
- `test_merchant_search_creates_local_person_and_shop_without_trade`
- `test_v11_semantic_city_observation_and_local_discovery`
- `test_location_npc_and_defeat_authority_remain_strict`

## Review status

- **No-go for merge or publish:** the release selector still has the four baseline failures above, and the live canonical-scene inspection did not produce a concrete finding.
- The narration-repair and Turkish action-matching regressions passed their focused tests. The pushed source commit is `85b64119fc8b9b2416eac2453c383d6143db5402`.
- No deployment was attempted.
