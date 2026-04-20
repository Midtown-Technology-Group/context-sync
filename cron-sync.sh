#!/usr/bin/env bash
#
# Work Context Sync - Cron wrapper with catch-up logic
# Handles missed executions when device is off/asleep
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="/mnt/c/Users/ThomasBray/OneDrive - Midtown Technology Group LLC/Knowledge"
LOCK_DIR="${VAULT_PATH}/.sync-state"
LAST_RUN_FILE="${LOCK_DIR}/last-successful-sync"
TODAY="$(date +%Y-%m-%d)"
LOG_FILE="${LOCK_DIR}/sync.log"

# Ensure directories exist
mkdir -p "${LOCK_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "${LOG_FILE}"
}

run_sync() {
    local target_date="$1"
    local reason="$2"
    
    log "Starting sync for ${target_date} (${reason})"
    
    cd "${SCRIPT_DIR}"
    
    # Run the actual sync (core = calendar + mail + todo)
    if ./run.sh "${target_date}" calendar mail todo 2>&1; then
        # Record success
        echo "${target_date} $(date '+%H:%M:%S')" > "${LAST_RUN_FILE}"
        log "SUCCESS: Sync completed for ${target_date}"
        
        # Also create/update a marker in the vault
        touch "${VAULT_PATH}/work-context/daily/.last-sync"
        return 0
    else
        log "ERROR: Sync failed for ${target_date}"
        return 1
    fi
}

should_run_today() {
    # Check if we already ran today
    if [[ ! -f "${LAST_RUN_FILE}" ]]; then
        # Never run before - should run
        return 0
    fi
    
    local last_run
    last_run="$(head -1 "${LAST_RUN_FILE}" | cut -d' ' -f1)"
    
    if [[ "${last_run}" == "${TODAY}" ]]; then
        # Already ran today
        log "SKIP: Already synced today at $(tail -1 "${LAST_RUN_FILE}" | cut -d' ' -f2-)"
        return 1
    fi
    
    # Last run was on a different day - need to run
    return 0
}

catch_up_if_needed() {
    # If last run was yesterday (or earlier), run for today
    if [[ ! -f "${LAST_RUN_FILE}" ]]; then
        return 0
    fi
    
    local last_run_date
    last_run_date="$(head -1 "${LAST_RUN_FILE}" | cut -d' ' -f1)"
    
    # Calculate days since last run (rough check)
    if [[ "${last_run_date}" != "${TODAY}" ]]; then
        log "CATCH-UP: Last run was ${last_run_date}, today is ${TODAY}"
        return 0
    fi
    
    return 1
}

# Main execution
main() {
    log "--- Cron sync check started ---"
    
    # Check if we should run (once per day max)
    if should_run_today; then
        if catch_up_if_needed; then
            run_sync "${TODAY}" "catch-up or first run"
        else
            run_sync "${TODAY}" "scheduled run"
        fi
    else
        log "No action needed - already synced today"
    fi
    
    log "--- Cron sync check complete ---"
}

# Handle arguments
if [[ "${1:-}" == "--force" ]]; then
    # Force run even if already ran today
    log "FORCE: Running sync despite previous completion"
    run_sync "${TODAY}" "forced"
elif [[ "${1:-}" == "--catch-up-only" ]]; then
    # Only run if we missed a day
    if catch_up_if_needed; then
        run_sync "${TODAY}" "catch-up"
    else
        log "No catch-up needed - already up to date"
    fi
else
    main
fi
