# Barbarian Danger Sense — scoped ACCEPTED

Applied Barbarian2+ Dexterity-save Advantage is supported through the existing weapon/unarmed save owner. The actual NPC grapple caller, session RNG, condition/automatic-failure handling, source cancellation, fresh restore and late rollback have verified coverage. No UI action, new resource, spell routing or full-class claim.

**Final source:** related guarded376/376 PASS and fresh independent8/8 PASS. These overlapping runs are not summed. Earlier independent283 PASS belongs to the pre-correction source only. Genuine initial RED8 methods/12 expected assertion failures and strict applied>raw correction RED1/1 expected failure are retained. The initial independent PATH refusal happened before product-test execution and is retained separately.

Self-contained checkpoint evidence is in [`evidence/c10-barbarian-danger-sense-20261029/`](evidence/c10-barbarian-danger-sense-20261029/):
- [`HANDOFF.md`](evidence/c10-barbarian-danger-sense-20261029/HANDOFF.md): scope, source provenance, final file hashes, test distinctions and rollback.
- `source-manifest.json`, `scoped.patch`, before-file snapshots and `checkpoint-evidence-sha256.json`: exact source/evidence binding.
- `danger-regression-final/child-1.raw.log`: final376 PASS, SHA256 `c5662a40de33818bba1f9b9bb1dda05e0cb7ee7cd0c506e7f49d605534941b29`.
- `danger-independent-final/child-1.raw.log`: final independent8 PASS, SHA256 `fd817242f6cafb5babb83b8344b01e8bfeb9ab9aa7cfa3fa5077ca0167061557`.
- All referenced earlier raw logs/run-evidence reports are copied unchanged into their named subdirectories. Paths in the original handoff referring to external WORK can now resolve within this evidence directory. Its external-work wording is retained as contemporaneous provenance.

Final `weapon_attack.py` SHA256 `3844fd76bc144683ce7b5fb3d74558de7bc00b398ec18a550fc061c9b222eecb`; new test SHA256 `a2e19b1752dbfabd2b82bd39297e078b6a57393aa2c4835deda4bccf35aafdbc`. Other three owned file hashes are in the source manifest. One stale Sorcerer-start test expectation was aligned to already approved starts1–5, retaining Barbarian rejection tests; it is not a Danger Sense behavior fix.

No raw book text copied. Other save routes, Rage, Reckless Attack, Unarmored Defense, mastery and full C06/C10 remain pending. The next-leaf note is read-only, not implementation or acceptance. No push, merge, deployment, auth/security or personal-data actions. Evidence and docs frozen for source checkpoint.
