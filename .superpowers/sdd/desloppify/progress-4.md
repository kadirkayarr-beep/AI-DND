# progress-4 (round 4: mechanical score)
Start: overall 62.4 / objective 75.0 / strict 62.3 (from `status`, last scan).
Ruling: test files named test_<module>.py (desloppify maps tests to modules by that name) — tool's only reliable mapping; modules whose basename is not unique (models, state, projection, rewards, __init__) are skipped — cost if wrong: coverage items stay open.
Ruling: pure-logic tests build plain dict worlds or use game.create_session (engine level, not a campaign), so fixed_town is not needed — none of the new tests creates a campaign.
## test_coverage done
batch1: arbiter, faction, deadlines, awareness, pack_loader, envelope, gate, coin, routes_catalog, opening_narrative (10 modules, 10 test files)
