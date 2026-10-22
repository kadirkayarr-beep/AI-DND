# Start here — AI-DND

## Current source and runtime

- Canonical checkout: `C:\Users\Kadir\Desktop\AI - DND`.
- Shared branch: `dev/ai-dnd`, repository `kadirkayarr-beep/AI-DND`.
- Gameplay baseline: `e06253f5ad34559486554973073e515c17b20ca9`.
- The subsequent archive/documentation commit changes no product source, contract, configuration, test or dependency. Obtain its exact identity with `git rev-parse HEAD`; compare with `git rev-parse origin/dev/ai-dnd` before exchanging changes.
- Runtime launched 2026-10-22 16:37 UTC from the gameplay baseline: API PID 19692 / port 8008, experience UI PID 40064 / port 22785. These are recorded observations, not permanent PID guarantees. Documentation cleanup does not restart or upgrade a running process.
- Player URL: http://127.0.0.1:22785/ai-dnd-experience/
- On this computer use the desktop shortcut **AI-DND - Guncel Ortak Surum**. It invokes `C:\Users\Kadir\Documents\Codex\2026-10-22\task\Start-Current-AI-DND.ps1`, which verifies the source/runtime and loads the approved existing local login configuration in place. Keep that local configuration and wrapper; neither is published here.
- The repository `start_local.ps1` is the generic player entry point, but does not load the local login configuration itself. Do not accidentally use a historical checkout or assume an already listening port is current.

## Short reading order

1. This file for current status and commands.
2. [AGENTS.md](AGENTS.md) for ownership and workspace constraints.
3. [COMMON_BASELINE_2026-10-22.md](COMMON_BASELINE_2026-10-22.md) for integration decisions and exact known failures. Its runtime-switch paragraph describes the pre-transition checkpoint; the observation above supersedes that paragraph.
4. [API guide](ai-dnd/api/README.md), [engine guide](ai-dnd/README.md), and `lib/api-spec/openapi.yaml` only as needed for the review.
5. [Development docs](ai-dnd/docs/README.md) for specific approved design contracts. Historical prompts and reports are evidence, not new instructions or current acceptance.

## Checks and open issues

From the canonical root: `./dev.ps1 -List` lists daily checks; `./dev.ps1` runs them. Full API discovery is the separate `./dev.ps1 -ApiDiscover` command. Do not substitute model-dependent smoke runs for deterministic checks.

UI: `corepack pnpm --filter @workspace/ai-dnd-experience run typecheck`, `run test`, `run build`, and the separate `run test:ui` browser-fixture gate. Use synthetic providers and temporary databases for API tests; never reuse the live campaign DB. Full verification details and prior results are in the baseline document; these are not fresh full-suite PASS claims.

The preserved `TwoPlayerIsolationTests` failures are:

- `test_a_saved_but_inactive_campaign_is_409_for_its_owner_and_404_for_everyone_else`
- `test_a_signed_in_stranger_gets_the_same_answer_as_for_a_missing_record`

Local ownership behavior remains unchanged: 409/404 differences remain, including distinguishable foreign-active and missing records. This is not a full security-gate pass. Reported dialogue, tavern/door and sitting gameplay defects remain open pending testing on the verified runtime. Health 200 and anonymous 401 checks passed after transition; no model turn, authenticated human acceptance or stable release acceptance was performed by this transition/cleanup task. External Claude/Gemini reviews have not been started.

## Archived material

Unreferenced historical development-run outputs and pasted prompt files were moved to `C:\Users\Kadir\Documents\AI-DND-Arsiv\2026-10-22\repo-cleanup`, preserving repository-relative paths with a SHA256 manifest. They remain recoverable locally and in Git history at the gameplay baseline. Historical JSON run manifests may still list their original paths as snapshots of the old tree; those are archival observations, not active file links or runtime inputs.

Referenced reports, approved specifications, fixtures, generated API clients, licenses, assets and all product sources remain. Untracked agent configuration, personal saves, credentials, other worktrees and desktop transfer packages were not swept into this cleanup. Do not bulk-read old evidence when reviewing current behavior; retrieve a specific archived record only when needed.

## External books and deliveries

Large owner-provided books and historical deliveries now live outside the repository. See [EXTERNAL_SOURCES.md](EXTERNAL_SOURCES.md) for portable research setup and the separate full-book identity check. Default CI validates reviewed source metadata and application behavior; it does not claim to have checked unavailable book bytes. Runtime product code is unchanged by this extraction.
