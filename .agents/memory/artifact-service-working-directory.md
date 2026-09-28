---
name: Artifact service working directory
description: Working-directory behavior for managed artifact development services.
---

Managed artifact development commands run from the artifact directory. Relative paths to sibling project folders therefore need to account for that directory or explicitly change to the workspace root.

**Why:** A FastAPI service command using `cd ai-dnd` failed because that directory was not present from the artifact working directory; `cd ../../ai-dnd` launched the service correctly.

**How to apply:** Check the working directory before writing relative development commands. Do not assume production build/run commands use the same directory; compare existing artifact service conventions and validate those paths separately.