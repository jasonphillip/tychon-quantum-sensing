#!/usr/bin/env bash
# run_beelink_verification.sh — run shls sw_run + Libero closure on Beelink
# for the current local branch, then extract reports + run the corpus audit.
#
# Usage: run_beelink_verification.sh <tag> [<bee-host>] [<bee-repo-path>]
#
# Exit codes:
#   0 = success (closure ran and audit passed)
#   2 = SSH unreachable (Beelink not available)
#   3 = branch missing on Beelink
#   4 = SmartHLS sw_run failed
#   5 = Libero closure failed
#   6 = audit failed

set -uo pipefail

TAG="${1:?TAG required}"
BEE="${2:-bee}"
BEE_REPO="${3:-~/dev/projects/polarfire-hybrid-control}"

LOCAL_BRANCH="$(git symbolic-ref --short HEAD)"
REPORT_DIR="libero/reports/${TAG}"
LOG="${REPORT_DIR}/beelink_verification.log"

mkdir -p "${REPORT_DIR}"

log() {
    printf '[%(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*" | tee -a "${LOG}"
}

log "tag=${TAG} branch=${LOCAL_BRANCH} bee=${BEE} bee_repo=${BEE_REPO}"

if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "${BEE}" hostname >>"${LOG}" 2>&1; then
    log "FAIL: ssh ${BEE} unreachable (BatchMode, ConnectTimeout=8)"
    exit 2
fi

log "pushing branch ${LOCAL_BRANCH} to origin (best effort)"
git push origin "${LOCAL_BRANCH}" 2>&1 | tee -a "${LOG}" || true

# Beelink fetches from the `spark1` remote (ssh://badwillhunt@spark1/...) so
# we don't need GitHub SSH on Beelink. Fall back to origin if spark1 isn't
# configured.
log "remote checkout via spark1 remote"
REMOTE_FETCH_CMD="(git fetch spark1 ${LOCAL_BRANCH}:refs/remotes/spark1/${LOCAL_BRANCH} 2>/dev/null || git fetch origin ${LOCAL_BRANCH}:refs/remotes/origin/${LOCAL_BRANCH})"
REMOTE_TRACK_REF="refs/remotes/spark1/${LOCAL_BRANCH}"
ssh "${BEE}" "bash -lc 'cd ${BEE_REPO} && ${REMOTE_FETCH_CMD} && git checkout -B ${LOCAL_BRANCH} ${REMOTE_TRACK_REF} 2>/dev/null || git checkout -B ${LOCAL_BRANCH} refs/remotes/origin/${LOCAL_BRANCH}'" 2>&1 | tee -a "${LOG}"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    log "FAIL: branch ${LOCAL_BRANCH} not reachable on ${BEE}"
    exit 3
fi

log "remote SmartHLS sw_run"
ssh "${BEE}" "bash -lc 'cd ${BEE_REPO}/hls && shls sw_run'" 2>&1 | tee -a "${LOG}"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    log "FAIL: shls sw_run"
    exit 4
fi

log "remote Libero closure"
ssh "${BEE}" "bash -lc 'cd ${BEE_REPO} && bash libero/scripts/closure_with_watchdog.sh'" 2>&1 | tee -a "${LOG}"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    log "WARN: Libero closure exited non-zero — capturing reports anyway"
fi

log "extracting reports under ${REPORT_DIR}"
ssh "${BEE}" "bash -lc 'cd ${BEE_REPO} && bash libero/scripts/extract_reports.sh ${TAG}'" 2>&1 | tee -a "${LOG}"

log "pulling report bundle locally"
git fetch origin 2>&1 | tee -a "${LOG}"
git pull --ff-only origin "${LOCAL_BRANCH}" 2>&1 | tee -a "${LOG}" || true

log "running corpus audit"
if python3 tools/audit_libero_reports.py --strict "${REPORT_DIR}" 2>&1 | tee -a "${LOG}"; then
    log "audit OK"
    exit 0
fi
log "FAIL: audit"
exit 6
