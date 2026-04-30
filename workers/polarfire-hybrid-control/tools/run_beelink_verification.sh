#!/usr/bin/env bash
# Run the corpus-grounded verification path on the Beelink tool host.
#
# This script is intentionally noninteractive. It exits with a clear blocked
# reason instead of prompting for credentials, GUI actions, or destructive
# cleanup.

set -euo pipefail

REMOTE="${BEE_REMOTE:-bee}"
REMOTE_REPO="${BEE_REPO:-~/dev/projects/polarfire-hybrid-control}"
TAG="${1:-$(date +%F-%H%M%S)-beelink}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
REPORT_DIR="libero/reports/${TAG}"
LOG="${REPORT_DIR}/beelink_verification.log"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)

mkdir -p "$REPORT_DIR"

{
    echo "# Beelink Verification"
    echo ""
    echo "- Date: $(date -Iseconds)"
    echo "- Remote: ${REMOTE}"
    echo "- Remote repo: ${REMOTE_REPO}"
    echo "- Branch: ${BRANCH}"
    echo "- Report tag: ${TAG}"
    echo ""
} | tee "$LOG"

run_local() {
    echo "+ $*" | tee -a "$LOG"
    "$@" 2>&1 | tee -a "$LOG"
}

run_remote() {
    local command="$1"
    echo "+ ssh ${REMOTE} ${command}" | tee -a "$LOG"
    ssh "${SSH_OPTS[@]}" "$REMOTE" "$command" 2>&1 | tee -a "$LOG"
}

if ! run_remote "hostname"; then
    {
        echo ""
        echo "BLOCKED: noninteractive SSH to ${REMOTE} failed."
        echo "Command: ssh -o BatchMode=yes -o ConnectTimeout=8 ${REMOTE} hostname"
        echo "Reason: host unreachable, DNS failure, or missing noninteractive credentials."
    } | tee -a "$LOG"
    exit 2
fi

REMOTE_REPO_Q="$(printf "%q" "$REMOTE_REPO")"
BRANCH_Q="$(printf "%q" "$BRANCH")"

REMOTE_CHECKOUT_CMD="
set -euo pipefail
cd ${REMOTE_REPO_Q}
git status --short --branch
git fetch --all --prune
if git show-ref --verify --quiet refs/heads/${BRANCH_Q}; then
    git switch ${BRANCH_Q}
elif git show-ref --verify --quiet refs/remotes/origin/${BRANCH_Q}; then
    git switch --track origin/${BRANCH_Q}
else
    echo 'BLOCKED: branch ${BRANCH} is not present locally or on origin on the Beelink.'
    exit 3
fi
git status --short --branch
"
run_remote "$REMOTE_CHECKOUT_CMD"

run_remote "set -euo pipefail; cd ${REMOTE_REPO_Q}; make hls-test"

if run_remote "command -v libero >/dev/null 2>&1"; then
    run_remote "set -euo pipefail; cd ${REMOTE_REPO_Q}; bash libero/scripts/closure_with_watchdog.sh"
    run_local bash libero/scripts/extract_reports.sh "$TAG"
    run_local python3 tools/audit_libero_reports.py "$REPORT_DIR"
else
    {
        echo ""
        echo "SKIPPED: Libero CLI was not found on ${REMOTE}."
        echo "Command: command -v libero"
        echo "Reason: SmartHLS software verification can run without Libero, but closure/report refresh cannot."
    } | tee -a "$LOG"
fi

echo "" | tee -a "$LOG"
echo "DONE: Beelink verification log at ${LOG}" | tee -a "$LOG"
