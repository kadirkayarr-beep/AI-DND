# AI-DND — Cursor ↔ Replit agent handoff protocol

> Status: **Proposed** (2026-10-11). This document is a coordination proposal, not authorization to run Git operations or alter live services. Do not treat branch names below as permanent or authoritative. Confirm the active checkout each time.

## Purpose and sources of truth

- Python game rules, the FastAPI game adapter and SQLite campaign persistence own authoritative game state. Qwen/Ollama parses Turkish intent and narrates; the browser does not invent mechanical state.
- The Node/Express + PostgreSQL workspace is separate from the Python campaign API; do not move campaign persistence or game routes to it.
- Consult `replit.md`, `ai-dnd/README.md`, `ai-dnd/api/README.md`, and the active checkout's `AGENTS.md` and `.cursor/rules/` before work.
- The GitHub repository is the exchange/inspection point for **committed source changes**, not a replacement for Replit's uncommitted working files or live SQLite data. No single branch is inherently canonical without an explicit owner decision.

## Observed starting point — verify again before using

On 2026-10-11, Replit reported its local branch as `maintenance/pre04-runtime-health`, with **no configured upstream** and extra local commits relative to an unfetched `origin/main`. The visible GitHub remote had branches `main`, `phase8/emergent-storytelling-expansion`, `integration/replit-b672668-cursor-5a5e789` and a Replit backup branch. The Cursor checkout's actual branch and HEAD were **not verified**. These are observations only; they may change.

## Mandatory preflight for each new task

1. Record active machine/checkout, branch, HEAD, upstream, and staged/unstaged/untracked state. Never assume a branch from a file, a previous conversation or an old local ref.
2. Check for other active agents/chats. Record exactly which feature and files each agent owns. **One writer per overlapping file set.** When uncertain, do not edit shared files.
3. Record the proposed change scope, working branch, target branch and known risks. Obtain explicit owner permission before any push, branch reconciliation, merge, force operation, publish, or production DB modification.
4. Do not checkout, reset, stash, clean, pull with rebase, or overwrite a dirty working tree in an attempt to make it "clean." Preserve unknown/untracked evidence files.
5. Verify the current remote heads before discussing divergence; local `origin/main` is not proof of live GitHub state.

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

## Human-readable handoff receipt

Every completed change should report:

```text
Task / owner:
Checkout / branch / HEAD:
Base ref / proposed target:
Changed files:
Commits proposed for sharing:
Data or runtime risk:
Tests actually run / skipped and why:
Untracked or concurrent work intentionally preserved:
Reviewer approval still needed:
```

## Stop conditions

Stop without mutating code or data if the checkout is not the expected one, another agent is writing the same files, untracked material is unexplained, branch ancestry cannot be verified, SQLite ownership/backup status is unclear, or the requested action would require an unapproved push, migration, merge or deployment. Report the blocker and suggest a small, reversible next step.

## Follow-up decisions (not yet made)

1. Confirm Cursor's real checkout/branch/HEAD and current local changes.
2. Choose and publish an explicit shared integration base and file ownership matrix.
3. Decide whether a protected `main` branch and required PR checks can be enabled with the user's GitHub access.
4. Verify live SQLite backup and restore procedures **in isolation** before relying on them.
