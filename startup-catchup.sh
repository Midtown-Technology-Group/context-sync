#!/usr/bin/env bash
#
# Startup catch-up script
# Run this on login/startup to sync if cron was missed
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run catch-up only (won't re-run if already synced today)
exec "${SCRIPT_DIR}/cron-sync.sh" --catch-up-only
