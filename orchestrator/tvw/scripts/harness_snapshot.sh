#!/usr/bin/env bash
# harness_snapshot.sh — Tier 1 (dated archive) + Tier 2 (harness-state git repo)
# Captures everything that makes the TVW environment behave the way it does:
# global config, hooks, all project memories, the wiki, and git bundles of the
# four behavior-defining repos. Secrets are excluded by pattern and the staged
# tree is content-scanned before the script reports success.
# Usage: harness_snapshot.sh [--repo-only]   (--repo-only = Tier 2 commit only, for cron)
set -euo pipefail

STAMP=$(date +%Y-%m-%d)
STAGE="$HOME/archives/harness-snapshots/$STAMP"
STATE_REPO="$HOME/projects/harness-state"
REPOS=(
  "$HOME/projects/tychon-verification-workbench"
  "$HOME/projects/claude-config"
  "$HOME/projects/outreach"
  "$HOME/projects/skills"
)
EXCLUDES=(--exclude='.credentials*' --exclude='*token*' --exclude='*secret*' \
  --exclude='*apikey*' --exclude='*.pem' --exclude='*.key' --exclude='id_rsa*' \
  --exclude='*credentials*' --exclude='__pycache__' --exclude='*.pyc')

secret_scan() { # scan a directory for high-signal secret markers; fail loudly
  local dir="$1"
  if grep -rIl --exclude='*.bundle' -E 'sk-ant-[A-Za-z0-9_-]{20}|ghp_[A-Za-z0-9]{30}|github_pat_[A-Za-z0-9_]{30}|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC )?PRIVATE KEY|xoxb-[0-9A-Za-z-]{10}' "$dir" 2>/dev/null | head -5 | grep .; then
    echo "SECRET SCAN FAILED in $dir — aborting" >&2; exit 1
  fi
}

# ---------- Tier 2: harness-state git repo (always runs) ----------
mkdir -p "$STATE_REPO"
cd "$STATE_REPO"
[ -d .git ] || git init -q
mkdir -p claude memory wiki
rsync -a --delete "${EXCLUDES[@]}" "$HOME/.claude/hooks/" claude/hooks/
for f in CLAUDE.md settings.json keybindings.json; do
  [ -f "$HOME/.claude/$f" ] && cp "$HOME/.claude/$f" claude/
done
for m in "$HOME"/.claude/projects/*/memory; do
  [ -d "$m" ] || continue
  proj=$(basename "$(dirname "$m")")
  rsync -a --delete "${EXCLUDES[@]}" "$m/" "memory/$proj/"
done
rsync -a --delete "${EXCLUDES[@]}" "$HOME/Desktop/Shared/wiki/" wiki/
secret_scan "$STATE_REPO"
git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "snapshot $(date '+%Y-%m-%d %H:%M %Z')"
fi
echo "Tier 2: harness-state at $(git rev-parse --short HEAD) ($(git rev-list --count HEAD) snapshots)"

[ "${1:-}" = "--repo-only" ] && exit 0

# ---------- Tier 1: dated archive ----------
mkdir -p "$STAGE"/{config,memory,bundles,patches}
rsync -a "${EXCLUDES[@]}" "$HOME/.claude/hooks/" "$STAGE/config/hooks/"
for f in CLAUDE.md settings.json keybindings.json; do
  [ -f "$HOME/.claude/$f" ] && cp "$HOME/.claude/$f" "$STAGE/config/"
done
rsync -a "${EXCLUDES[@]}" "$HOME"/.claude/projects/*/memory "$STAGE/memory/" 2>/dev/null || true
for m in "$HOME"/.claude/projects/*/memory; do
  [ -d "$m" ] || continue
  proj=$(basename "$(dirname "$m")")
  rsync -a --delete "${EXCLUDES[@]}" "$m/" "$STAGE/memory/$proj/"
done
tar -C "$HOME/Desktop/Shared" -czf "$STAGE/wiki.tar.gz" wiki
for r in "${REPOS[@]}"; do
  name=$(basename "$r")
  git -C "$r" bundle create "$STAGE/bundles/$name.bundle" --all 2>/dev/null
  if ! git -C "$r" diff --quiet || ! git -C "$r" diff --cached --quiet; then
    git -C "$r" diff HEAD > "$STAGE/patches/$name.pending.patch" || true
  fi
done
# TVW project-local .claude (untracked settings), secrets-filtered
[ -d "$HOME/projects/tychon-verification-workbench/.claude" ] && \
  tar -C "$HOME/projects/tychon-verification-workbench" "${EXCLUDES[@]}" -czf "$STAGE/tvw-project-claude.tar.gz" .claude

# Manifest
{
  echo "created: $(date '+%Y-%m-%d %H:%M %Z') host: $(hostname)"
  echo "model: claude-fable-5 (session-reported)"
  echo "claude-cli: $(claude --version 2>/dev/null | head -1 || echo unknown)"
  echo "plugins: $(ls "$HOME/.claude/plugins/cache" 2>/dev/null | tr '\n' ' ')"
  echo "crontab:"; crontab -l 2>/dev/null | sed 's/^/  /'
  echo "---sha256---"
  (cd "$STAGE" && find . -type f ! -name MANIFEST.txt -exec sha256sum {} \;)
} > "$STAGE/MANIFEST.txt"
secret_scan "$STAGE"
echo "Tier 1: $(du -sh "$STAGE" | cut -f1) staged at $STAGE"
