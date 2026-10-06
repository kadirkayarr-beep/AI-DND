#!/bin/bash
set -euo pipefail

CI=true pnpm install --frozen-lockfile
# AI-DND owns SQLite campaign migrations. Do not push the unused, empty
# PostgreSQL template schema automatically during unrelated task merges.
