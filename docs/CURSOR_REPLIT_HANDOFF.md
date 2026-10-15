# AI-DND — Operational handoff (Cursor ↔ Replit)

> **Current operational entry point, updated 2026-10-15.** Use this document for current coordination status, owners, and links. It is not authorization to merge, push, publish, alter live services, or modify campaign data. Recheck live refs and checkout state before each task.

## Authority and document roles

- **Vision and roadmap acceptance authority:** the owner-approved Future Project Bible v2.3.2, identified by the separate [owner approval/freeze record](../ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_OWNER_APPROVAL_2026-10-09.md) and its locked source [Bible](../ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md), SHA-256 `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`. The title's `PROPOSED` is part of the frozen source identity; the separate record contains the approval. Do not edit, copy, replace, or disable the Bible.
- **Executed regression evidence authority:** [`ai-dnd/docs/regression-evidence.md`](../ai-dnd/docs/regression-evidence.md), with its retained run records. A roadmap or handoff is not a test result; do not rewrite historical PASS counts.
- **Operational coordination authority:** this handoff. Use it for current refs, ownership, evidence expectations, and links.
- **History:** dated reports, prior handoffs, and retained run records describe what was recorded at that time. They are not current branch truth and must not be retroactively rewritten.
- Python owns rules, authoritative game state, and persistence; Qwen/Ollama parses intent and narrates; the browser displays server state. The Node/Express + PostgreSQL workspace is separate from the Python campaign API.
- Technical gate details are in [`development-infrastructure.md`](../ai-dnd/docs/development-infrastructure.md); actual evidence semantics and records are in [`regression-evidence.md`](../ai-dnd/docs/regression-evidence.md).

## Operational status — 2026-10-15

These are the live Git refs last checked for this handoff. A branch ref does not imply merge approval or a green validation result.

| Work/ref | Full SHA | Status / owner |
| --- | --- | --- |
| `dev/ai-dnd` | `5a3972c109cf75d8c7eff0965731dcccf1575c1c` | Main shared development line at the last check. |
| PR #3 head | `4a2289fab68c218f6f78daa01cb320f9219f5df8` | Review proposal; distinct from the later Replit task SHA. |
| Replit task branch `agent/pr3-tooling-fixture-isolation-4a2289fa` | `4436324f261c6c03a222f5b2a46e8d61c5b212d2` | Live branch SHA verified; isolated task source, not merged into `dev`. |
| Cursor branch `cursor/narration-claim-binding` | `1f48b011bf02bb00ae91d765579bc11bc0bb15ad` | Last live-verified at `2026-10-15T19:23:28Z`; independent review is pending. A branch SHA does not establish that all tests passed or integration is complete. |

Links: [dev branch](https://github.com/kadirkayarr-beep/AI-DND/tree/dev/ai-dnd) · [Replit task branch](https://github.com/kadirkayarr-beep/AI-DND/tree/agent/pr3-tooling-fixture-isolation-4a2289fa) · [Cursor branch](https://github.com/kadirkayarr-beep/AI-DND/tree/cursor/narration-claim-binding) · [PR #3](https://github.com/kadirkayarr-beep/AI-DND/pull/3).

### Work ownership

- **Cursor:** narration-claim binding and its own focused tests; independent review remains pending.
- **Replit:** gate/tooling and verification infrastructure, travel/venue routing, and API work.
- Keep concurrent ownership disjoint. One writer per overlapping file set; use a separate task branch/worktree from an explicitly verified SHA. Do not infer that a task branch is merged because it is published.

### Recorded CI/gate and paired-run status

- Prior changes in the task lineage include `62dc355` (tooling-fixture isolation from GitHub CI provenance) and `4a2289f` (LR00 review packet recorded without a PASS claim); travel/venue routing continued in `c33c6f6` and `4436324`.
- The paired historical comparison reported **baseline: 122 tests, 29 errors; candidate: 123 tests, the same 29 errors and one additional pass**. This is not a green package or a PASS claim.
- The temporary raw paired logs are no longer accessible. Treat those counts as a reported historical comparison, not independently reverified evidence. Do not recreate or silently upgrade the result.

## Mandatory preflight for each new task

1. Record active machine/checkout, branch, HEAD, upstream, and staged/unstaged/untracked state. Never assume a branch from a file, a previous conversation or an old local ref.
2. Check for other active agents/chats. Record exactly which feature and files each agent owns. **One writer per overlapping file set.** When uncertain, do not edit shared files.
3. Record the proposed change scope, working branch, target branch and known risks. Obtain explicit owner permission before any push, branch reconciliation, merge, force operation, publish, or production DB modification.
4. Do not checkout, reset, stash, clean, pull with rebase, or overwrite a dirty working tree in an attempt to make it "clean." Preserve unknown/untracked evidence files.
5. Verify the current remote heads before discussing divergence; local remote-tracking refs are not proof of live GitHub state.

## Branch and integration policy

- Prefer a **separate task branch for each agent** from a mutually verified base, e.g. `cursor/<task>` and `replit/<task>`; use an `integration/<task>` branch for review. Existing historical branches are not automatically task branches.
- Before integrating anything from Replit, identify its actual local commits and agree on the remote destination; it currently may have **no upstream**. Never bulk-push or wholesale-merge a long-running Replit maintenance branch just to transfer one fix.
- Exchange **explicit, reviewed commits/PRs**, not a ZIP of the complete workspace and not silent file copying. Review the commit range and per-file diff; avoid importing unrelated package, configuration, asset or evidence changes.
- Keep `main` untouched until a requested, reviewed integration passes required checks. Do not force-push, rewrite history or automatically deploy.
- A proposed protocol document or draft PR is *not* approval to merge it or to run sync commands.

## Protected state and test isolation

- Never reset, seed, overwrite, delete, restore or migrate the owner's campaign SQLite DB without specific approval and a verified, recoverable backup.
- SQLite canonical path can default to `ai-dnd/saves/campaigns.sqlite3`; `AI_DND_CAMPAIGN_DB` can redirect it. Confirm the actual runtime environment. Use a fresh temporary DB for tests and manual simulated turns.
- Replit's in-process `GameSession` state is not equivalent to persisted SQLite state. Avoid actions that unexpectedly replace a live process or redeploy a session.
- `DATABASE_URL` and Drizzle's `db push` concern the **separate PostgreSQL workspace**; never run schema pushes on production.
- Run relevant deterministic checks **only after ensuring they cannot touch live data**; the documented aggregate runner is `python ai-dnd/run_tests.py`. Treat model-dependent live smoke tests as a separate, explicitly approved category. Report actual results, not assumptions.
- Keep secrets, local database files, `.env`, runtime caches and local evidence out of commits.

## Required task and verification receipt

For each completed task, record the fields below. Use the existing retained evidence rather than a second copied test list. Never include secret values; record only relevant environment variable names and safe state such as set/unset or redacted.

```text
Task / owner / scope:
Checkout: full absolute working-tree path; branch; full HEAD:
Base ref/SHA and candidate ref/SHA (report separately):
Working directory (cwd):
Exact command and argv:
Environment: relevant variable names and redacted/set-unset state only:
OS / architecture / shell:
Python version and lock identity (lockfile path plus recorded digest/version):
Selected / started / passed / failed / errors / skipped / not-run counts:
Exit code; completion state (completed / interrupted / incomplete):
Source changed during run? start/end SHA and recorded comparison:
Failed test IDs (fully qualified; list none explicitly if none):
Evidence links: matching run.json and output.log; state if unavailable:
Changed files / data or runtime risks:
Untracked or concurrent work intentionally preserved:
Reviewer approval still needed:
```

## Stop conditions

Stop without mutating code or data if the checkout is not the expected one, another agent is writing the same files, untracked material is unexplained, branch ancestry cannot be verified, SQLite ownership/backup status is unclear, or the requested action would require an unapproved push, migration, merge or deployment. Report the blocker and suggest a small, reversible next step.

## Historical record — 2026-10-11 (preserved; not current status)

### Observed starting point — verify again before using

On 2026-10-11, Replit reported its local branch as `maintenance/pre04-runtime-health`, with **no configured upstream** and extra local commits relative to an unfetched `origin/main`. The visible GitHub remote had branches `main`, `phase8/emergent-storytelling-expansion`, `integration/replit-b672668-cursor-5a5e789` and a Replit backup branch. The Cursor checkout's actual branch and HEAD were **not verified**. These are observations only; they may change.

### Follow-up decisions recorded at that time (historical)

1. Confirm Cursor's real checkout/branch/HEAD and current local changes.
2. Choose and publish an explicit shared integration base and file ownership matrix.
3. Decide whether a protected `main` branch and required PR checks can be enabled with the user's GitHub access.
4. Verify live SQLite backup and restore procedures **in isolation** before relying on them.
