---
name: Completion review scope
description: Completion can include pre-existing checkout edits in its commit and review.
---

Do not assume a task completion commit or review includes only the files edited
for the assigned task. Check the initial Git status and preserve ownership of
pre-existing changes.

**Why:** Completion of a test-only task included unrelated gameplay edits that
were already dirty at assignment, and the review treated those edits as part of
the task's changes.

**How to apply:** Capture the initial dirty-file inventory before editing. If
review flags unrelated pre-existing work, explain that scope explicitly rather
than reverting another contributor's changes or claiming they were validated
by the task's focused tests.
