#!/usr/bin/env bash
# overnight_runner.sh — single-shot Beelink probe + verify + commit + push.
#
# Designed to be invoked by a systemd-run --user --on-active=... transient
# timer at a fixed point during the night. Each invocation is independent and
# idempotent: if Beelink is unreachable, log + exit 0 (do NOT fail the
# timer); if Beelink is reachable, run make beelink-verify TAG=$TAG, then
# git add the log + any new report bundle, commit, push.
#
# Idempotency contract:
#   - If libero/reports/$TAG/ already exists for the current HEAD, skip the
#     synthesis re-run and only refresh the audit.
#   - If git push fails (auth, conflict), do NOT force-push. Log and exit 0.
#   - Never edit anything outside docs/overnight-runs/ and libero/reports/.
#
# Usage:
#   overnight_runner.sh <TAG>      e.g. overnight-r1
#
# Environment:
#   BEE_REMOTE  ssh host alias (default: bee)
#   BEE_REPO    remote repo path (default: ~/dev/projects/polarfire-hybrid-control)
#
# Logs: docs/overnight-runs/${TAG}.log
# Repo: this script must be invoked from the repo root.

set -uo pipefail

TAG="${1:?usage: overnight_runner.sh <TAG>}"
REPO_ROOT="${REPO_ROOT:-~/projects/polarfire-hybrid-control}"
BRANCH="${BRANCH:-codex/corpus-verification}"

cd "$REPO_ROOT"

LOG_DIR="docs/overnight-runs"
LOG_FILE="${LOG_DIR}/${TAG}.log"
REPORT_DIR="libero/reports/${TAG}"

mkdir -p "$LOG_DIR"

log() {
    echo "$(date -Iseconds) $*" | tee -a "$LOG_FILE"
}

log "=== overnight_runner start TAG=${TAG} ==="
log "branch=${BRANCH}"

# 1. Sync git state — fetch but do not blow away local work.
git fetch origin --prune 2>&1 | tee -a "$LOG_FILE" || log "WARN: git fetch failed"

# Ensure we are on the right branch. If we're not, check it out (only if the
# checkout is fast-forward; never overwrite uncommitted work).
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" != "$BRANCH" ]; then
    log "current branch is ${current_branch}; switching to ${BRANCH}"
    if ! git switch "$BRANCH" 2>&1 | tee -a "$LOG_FILE"; then
        log "ERROR: cannot switch to ${BRANCH} (uncommitted changes? branch missing?). Exiting."
        exit 0
    fi
fi

git pull --ff-only origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE" || log "WARN: git pull --ff-only failed (continuing)"

HEAD_SHA="$(git rev-parse HEAD)"
log "HEAD=${HEAD_SHA}"

# 2. Probe Beelink.
if ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new bee hostname >/dev/null 2>&1; then
    BEE_STATUS="up"
    log "Beelink reachable"
else
    BEE_STATUS="down"
    log "Beelink unreachable (ssh -o BatchMode=yes -o ConnectTimeout=8 bee hostname failed)"
fi

# 3. If down, log and exit 0. Commit the probe log so future runs can see it.
if [ "$BEE_STATUS" = "down" ]; then
    log "=== overnight_runner end (Beelink down) ==="
    git add "$LOG_FILE" || true
    if ! git diff --cached --quiet; then
        git -c user.name="overnight-runner" -c user.email="overnight@local" \
            commit -m "overnight ${TAG}: Beelink down — probe only" 2>&1 | tee -a "$LOG_FILE" || log "WARN: commit failed"
        git push origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE" || log "WARN: push failed (no force-push)"
    fi
    exit 0
fi

# 4. Beelink up — run verification. Idempotency check first.
if [ -d "$REPORT_DIR" ] && [ -f "${REPORT_DIR}/beelink_verification.log" ]; then
    LAST_HEAD="$(grep -m1 'HEAD=' "${REPORT_DIR}/beelink_verification.log" 2>/dev/null | awk '{print $2}' || true)"
    if [ "$LAST_HEAD" = "$HEAD_SHA" ]; then
        log "report bundle already exists for HEAD=${HEAD_SHA}; skipping synthesis re-run, refreshing audit only"
        SKIP_SYNTH=1
    fi
fi

if [ -z "${SKIP_SYNTH:-}" ]; then
    log "running make beelink-verify TAG=${TAG}"
    if ! make beelink-verify TAG="${TAG}" 2>&1 | tee -a "$LOG_FILE"; then
        log "WARN: make beelink-verify exited non-zero (likely Libero unavailable or partial closure)"
    fi
fi

# 5. Audit (always runs).
log "running audit-reports-strict on ${REPORT_DIR}"
make audit-reports-strict REPORT_DIRS="${REPORT_DIR}" 2>&1 | tee -a "$LOG_FILE" || log "audit reported strict violations"

# 6. Commit + push.
git add "$LOG_FILE" "$REPORT_DIR" 2>&1 | tee -a "$LOG_FILE" || true
if ! git diff --cached --quiet; then
    audit_verdict="unknown"
    if grep -q "All strict-eligible bundles pass" "$LOG_FILE"; then
        audit_verdict="strict pass"
    elif grep -q "strict violation" "$LOG_FILE"; then
        audit_verdict="strict violations"
    elif grep -q "BLOCKED" "$LOG_FILE"; then
        audit_verdict="blocked"
    fi
    git -c user.name="overnight-runner" -c user.email="overnight@local" \
        commit -m "overnight ${TAG}: Beelink up — ${audit_verdict}" 2>&1 | tee -a "$LOG_FILE" || log "WARN: commit failed"
    git push origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE" || log "WARN: push failed (no force-push)"
fi

log "=== overnight_runner end TAG=${TAG} ==="
exit 0
