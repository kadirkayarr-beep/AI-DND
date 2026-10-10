# 1501 freeze-candidate validation

Observed on branch `phase8/emergent-storytelling-expansion`, HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`. The check applied the 47 errata patches in memory and did not write to V2.2, the errata, the audit, production packs, profiles, or runtime.

## Input hashes

| Artifact | SHA-256 | Result |
| --- | --- | --- |
| `lore_extraction_candidates_v2_2.draft.json` | `2255bc3b1a3b2a907e8b639528c1adb78e1b37e9a41b04934469fd6c33b46ee4` | PASS |
| `field_errata.json` | `14ef3cdedb439d9f65a52f3d01a3ad6fe4ca75021ccdc5aedd0b93b635fa2859` | PASS |
| `current_1501_ledger.jsonl` | `8e1a846004dfb3d03f3cfbc51dc198c4260f37331b1a1fd85d4b6f780e1d0889` | PASS |
| `findings.md` | `931f939ee79939817c5b6832fd800acc378cc090e1d5bbc750f854239c21f72a` | PASS |
| `proposed_baseline.md` | `e423dd2038d80ba58647fdbbf32651e2b63b89513dcc0c29ba1c806262053739` | PASS |
| `closure_assessment.md` | `35648a9b968b153bcb4ced389db85d88065c60206650612796e8fc59f14ba04e` | PASS |

## Counts

- Current-era ledger: 100. Verdicts: 94 `verified_public`, 5 `verified_restricted`, 1 `verified_clause_excluded`.
- Public candidate: 94 full and 1 partial, 95 total. All 95 IDs appear in the public prose.
- Restricted manifest: 5. No ID is in both manifests.
- Supplemental records: 68, and 0 of them are in the candidate.
- Remaining V2.2 distribution: 13 `not_1501_fact`, 10 `historical_setting`, 10 `conflict_open`, 1 `not_established_1501`.

## Checks that passed

- Every manifest citation title, hash, and page list matches the in-memory patched record.
- The two source hashes each have one title.
- Every included record's V2.1 parent is the ID with `22-` replaced by `21-`, and that parent's V2 and V1 identifiers match the record.
- Every `supported_by` target of an included record is itself included.
- Every edge endpoint is an included public entity.
- Included records are public. Restricted records stay restricted, with public narration and automatic player knowledge not granted.
- `WD22-F-015` includes only the printed ward names and excludes the Castle Ward inference.
- The public prose does not contain the restricted subjects' distinctive terms.
- No included or restricted record is marked APPROVED or REVIEWED. `player_knowledge` stays `not_granted`.

Result of that run: the input hashes passed, the counts matched, and no consistency failure remained.

## Semantic limits that remain

The 100 current-era claims were read against Heroes and Adventures in the prior audit. Name-only entity rows are verified only to the extent that the name is on the cited page. The other 102 records were not re-read for this freeze. Their older keyword ledger is not semantic verification. Castle Ward in 1501 still lacks a source sentence. Supplemental continuity still lacks a 1501 source.

## Not implemented

No pack was loaded, no city was activated, and no model context was built. The future integration test is a plan only.

Smallest later test, after owner approval and still before activation:

1. A Python test loads only this candidate and rejects every ID outside the 95, including all 68 supplemental IDs and all 5 restricted IDs, when building a public context.
2. The same test rejects the Castle Ward sentence from `WD22-F-015`.
3. Two fixtures, one Waterdeep turn and one Baldur's Gate turn, show that Python selects a scene-sized subset. The prompt does not receive all 95 public rows and does not receive a restricted row.
4. The test asserts `player_knowledge` remains `not_granted` and that Qwen text cannot write HP, location, or canon.
5. Waterdeep and Baldur's Gate stay disabled until that test has been run and the owner accepts the candidate.

This candidate is ready for owner review. It is not approved for production. Live release remains NO-GO.
