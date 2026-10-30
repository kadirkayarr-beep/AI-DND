# Mage Armor selection-only dependency — 2026-10-29

Independent static review approved one Sorcerer catalogue row and its tests. Accepted source Sorcerer PDF142 level1 list and existing C05 header establish class/level membership. No effect description or resolver is newly claimed. Turkish UI notice explicitly says the gameplay effect is not supported yet.

The current catalogue now has seven literal PHB-valid ordinary options plus preserved legacy Chaos Bolt. Do not call all eight PHB2024. This avoids forcing that legacy selection when future level4 requires seven ordinary prepared spells; actual level4 remains blocked.

Actual RED4 assertions/0 errors, focused4 PASS, final related142 executions PASS with unchanged guard. Real current Sorcerer3 selection/save/fresh canonical restore preserves Mage Armor. Registry rejects with spell_resolver_missing; direct spell_scope owner retains unsupported_spell. Full state, slots and RNG stay unchanged. Different existing reasons were preserved, not artificially unified.

Evidence: docs/acceptance/evidence/c06-mage-armor-selection-20261029. Independent reviewer inspected source/code/raw log but did not rerun. No resolver, AC, Wizard description, schema, public starting-level range or level4 change. No browser visibility test for this new option; previous manual runtime is frozen before this addition. No full C05/C06 or spell-mechanics acceptance, commit/push/merge/deployment.
