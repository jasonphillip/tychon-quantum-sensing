#!/usr/bin/env bash
# push_snapshots_to_nas.sh — moves the locally staged Tier 1/2/3 snapshots to
# the NAS. Scheduled once via a self-removing cron line (tag: tvw-snap-push-once);
# safe to run manually. Internal-only remote per standing authorities.
set -euo pipefail
STAMP=${1:-$(date +%Y-%m-%d)}
LOG="$HOME/archives/harness-snapshots/push-$STAMP.log"
exec >>"$LOG" 2>&1
echo "=== push run $(date '+%Y-%m-%d %H:%M %Z') ==="

NAS_BACKUPS="/mnt/nas/backups"
ls "$NAS_BACKUPS" >/dev/null 2>&1 || { echo "NAS not reachable — leaving cron entry for retry"; exit 1; }

# Tier 1 archive
SRC1="$HOME/archives/harness-snapshots/$STAMP"
DST1="$NAS_BACKUPS/ws2-harness-snapshots/$STAMP"
if [ -d "$SRC1" ]; then
  mkdir -p "$DST1"
  rsync -a "$SRC1/" "$DST1/"
  (cd "$DST1" && sha256sum -c <(grep -A100000 -- '---sha256---' MANIFEST.txt | tail -n +2) --quiet) \
    && echo "Tier 1 verified on NAS" || { echo "Tier 1 VERIFY FAILED"; exit 1; }
fi

# Tier 3 genome capsule (dedicated place)
SRC3="$HOME/archives/tvw-genome-$STAMP"
DST3="$NAS_BACKUPS/ws2-tvw-genome-$STAMP"
if [ -d "$SRC3" ]; then
  mkdir -p "$DST3"
  rsync -a "$SRC3/" "$DST3/"
  (cd "$DST3" && sha256sum -c <(grep -A100000 -- '---sha256---' CAPSULE_MANIFEST.txt | tail -n +2) --quiet) \
    && echo "Tier 3 genome verified on NAS" || { echo "Tier 3 VERIFY FAILED"; exit 1; }
fi

# Tier 2 harness-state repo -> NAS bare remote
STATE="$HOME/projects/harness-state"
BARE="/mnt/nas/projects/git/harness-state.git"
if [ -d "$STATE/.git" ]; then
  [ -d "$BARE" ] || git init --bare -q "$BARE"
  git -C "$STATE" remote get-url nas >/dev/null 2>&1 || git -C "$STATE" remote add nas "file://$BARE"
  git -C "$STATE" push -q nas main 2>/dev/null || git -C "$STATE" push -q nas master 2>/dev/null || git -C "$STATE" push -q nas HEAD
  echo "Tier 2 harness-state pushed to NAS"
fi

# Self-remove the one-shot cron line
crontab -l 2>/dev/null | grep -v 'tvw-snap-push-once' | crontab - || true
echo "one-shot cron entry removed; push complete"
