# V2.1 validation report

Command: `python tmp-validate-v21.py` from `C:\Users\Kadir\Desktop\AI-DND-phase8-expansion`.

Branch `phase8/emergent-storytelling-expansion`. HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`.

Failed checks: 0.

## Results

- PASS json parses without duplicate keys
- PASS record ids unique — 202 records, 202 unique
- PASS 115 V1 ids traceable — covered 115 missing []
- PASS 180 V2 ids accounted — accounted 180
- PASS disposition covers every V2 id once
- PASS forward and reverse mapping
- PASS structured references resolve
- PASS citation pages are integer lists
- PASS every citation hash is a known source
- PASS no invented Heroes or Adventures folio
- PASS source file hashes match citations
- PASS every cited page is inside that PDF — {'569020fece5281a8aba01fac59a2fbb804dfe3f32af75df70aa20d7f3363c528': 218, '65bc8ed7b87e1f89466b8598464f90d024b87df83d0c87a45cc0feddf8b36848': 437, '8f582d64c01c84fca6a2e6106aa616ca8daa929fd7cc6243de56525d1f35f455': 228, '3f111653187e0a28f2864d2f90234c81b1643ef8012eda21e701603b69da2614': 260, 'c1f480cec0d650102e697c8e1a64edf4339bfa72a5897911d33519a3a32c6a51': 162, '23208efec1de9bc1bda1a3214f8fd75f4a3aec982d1231c8d669a9898c85dcec': 322}
- PASS conflict references exist in the conflict document
- PASS epoch linked on supplemental rows
- PASS skullport state linked — WD21-E-014,WD21-F-058-4,WD21-F-065,WD21-F-066,WD21-F-069
- PASS no public row embeds a restricted secret
- PASS allowed use is narration of a Python result
- PASS all records DRAFT UNREVIEWED and not loadable
- PASS rejected claims are not current setting facts
- PASS markdown and json ids agree — md 202 json 202
- PASS markdown claims match json — mismatches 0
- PASS published V2 hashes unchanged
- PASS V1 directory still has nine files — 9
- PASS production pack and profile diff is empty
- PASS branch is phase8/emergent-storytelling-expansion — phase8/emergent-storytelling-expansion
- PASS HEAD is f63d952506064cd59e960f1e3efa6627d4e52053 — f63d952506064cd59e960f1e3efa6627d4e52053

## Git status after the checks

The checks ran while temporary generator scripts were still in the worktree. Those scripts were deleted afterward. `git diff --stat` was empty. Final `git status --short`:

```
?? ai-dnd/docs/evidence/phase8-expansion/lore-review-v2-1/
?? ai-dnd/docs/evidence/phase8-expansion/lore-review-v2/
?? ai-dnd/docs/evidence/phase8-expansion/lore-review/
```

## V2 hashes compared with the published V2 report

- `Waterdeep_V2_Candidates.md` `8816419a0fd2071411fcdc0dce3f6811a861115ba6fe78447cdf781e0b2b0a35` expected `8816419a0fd2071411fcdc0dce3f6811a861115ba6fe78447cdf781e0b2b0a35` match `True`
- `Baldurs_Gate_V2_Candidates.md` `66e8233b9abbda9c0e3d54004d1d5adf3980b760b22edde02e81282af76aa411` expected `66e8233b9abbda9c0e3d54004d1d5adf3980b760b22edde02e81282af76aa411` match `True`
- `V1_to_V2_Record_Mapping.md` `b4a62efcceebefa87b029fdac0a1f942c770f425d807ed680363ed487e49c313` expected `b4a62efcceebefa87b029fdac0a1f942c770f425d807ed680363ed487e49c313` match `True`
- `V2_Conflicts_And_Owner_Decisions.md` `312282c42455eee624896f1f25069e2924f247122048ceb2a0b650831042ff37` expected `312282c42455eee624896f1f25069e2924f247122048ceb2a0b650831042ff37` match `True`
- `lore_extraction_candidates_v2.draft.json` `66d64df8536dbfa65410931387efc6398efd05337406c02eac3e8ffdcdad9f3c` expected `66d64df8536dbfa65410931387efc6398efd05337406c02eac3e8ffdcdad9f3c` match `True`
- `V2_Independent_Review_Readiness.md` `76d5551ed144f019d194d136ca6c40e75fc6b1d3f9439c9d814d3831d39ddf98` expected `76d5551ed144f019d194d136ca6c40e75fc6b1d3f9439c9d814d3831d39ddf98` match `True`

## V1 hashes recorded by this run

The nine V1 files were not written by this correction. No earlier published content hash for those nine files was stored in the V2 package, so this run records the current hashes.

- `Baldurs_Gate_Lore_Review_Draft.md` SHA-256 `07d863ef1982dbb28ae911c3cdab6ddb9e5dce7f4c477ce31e304bb7f5d14f67`
- `Baldurs_Gate_Source_Extraction_Candidates.md` SHA-256 `322bff7844d596c201491e45626bec5613ec6864bded182a7b79ad0cbbb379c7`
- `Lore_Activation_Readiness.md` SHA-256 `03ffdacebd572c48c11572ab837a359cb0f1cd61e9ed1a9854d9d64e7b1c42d7`
- `Lore_Conflicts_And_Gaps.md` SHA-256 `369f8cbe0d67923e2fac44e12ba759c09f2098d22b03ef21534505665d536424`
- `lore_extraction_candidates.draft.json` SHA-256 `fcd6678d4f0adaa02829361186ddc7203fb299639f37b879cac0057e75d34fca`
- `Lore_Review_Queue.md` SHA-256 `ea39bb73370e409e057704dd2725601f3ba9dda3ddebb892f4e66099bb0a3816`
- `Source_Provenance_And_Conflicts.md` SHA-256 `50baf15a01487c22ad84f8aca8c3c58cf8827527612a7a22f5709b2c8bf15968`
- `Waterdeep_Lore_Review_Draft.md` SHA-256 `3a39d24d1a094454a89752771104287b5bb77136553b5eac1b74d5d80da0f94d`
- `Waterdeep_Source_Extraction_Candidates.md` SHA-256 `da69f97c0b32f11efb1ad45b0a8ed61a64a11035fca362941cbc807ecc98b90b`

## V2.1 content hashes

- `Waterdeep_V2_1_Candidates.md` SHA-256 `c3c3cfeafef966ba5d9fbf081e5eef7f10b88b931de0c09d1b778bee9b7136fc`
- `Baldurs_Gate_V2_1_Candidates.md` SHA-256 `1ed6afc1dd1e0200ad60bc51a6fb782ca60c3337d14e77048a99add02c7a7796`
- `V2_to_V2_1_Record_Mapping.md` SHA-256 `ac91dfb22ea82b3cd3fbc1826049ebfd4661175e32e3152cab00b816ca030267`
- `V2_1_Conflicts_And_Owner_Decisions.md` SHA-256 `6d00f8e4758ef6e5d52c1ef7e2891d53fef074e14cc35d5d589500a9804df218`
- `lore_extraction_candidates_v2_1.draft.json` SHA-256 `c95221dca8af57b859a55ac6d80ff203988ae10a65768a94fb7de0a4a5e6dc43`

- `V2_1_Independent_Review_Readiness.md` SHA-256 `130e836b545ab2a9e5d35e4a390ca2fc40d5337859b17119b3d0aacca05a8e20`

This validation report is excluded from the list above because its own hash cannot appear inside itself.
