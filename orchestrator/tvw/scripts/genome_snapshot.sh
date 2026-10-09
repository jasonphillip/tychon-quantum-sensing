#!/usr/bin/env bash
# genome_snapshot.sh — Tier 3: the reproduction capsule ("genome").
# Everything needed to reconstruct this repo AND the environment that makes it
# behave the way it does, staged locally for later push to the NAS dedicated
# location (/mnt/nas/backups/spark2-tvw-genome-<date>/).
set -euo pipefail
STAMP=$(date +%Y-%m-%d)
STAGE="$HOME/archives/tvw-genome-$STAMP"
SNAP="$HOME/archives/harness-snapshots/$STAMP"
mkdir -p "$STAGE/bundles"

# 1. Git bundles: the four behavior repos + the evidence ground truth (audit workspace)
for r in tychon-verification-workbench claude-config outreach skills; do
  git -C "$HOME/projects/$r" bundle create "$STAGE/bundles/$r.bundle" --all 2>/dev/null
done
git -C "$HOME/audits/ONE_PERSON_AI_RD_2022_PRESENT" bundle create \
  "$STAGE/bundles/audit-workspace.bundle" --all 2>/dev/null || \
  echo "note: audit workspace bundle skipped (not a git repo or error)" >&2

# 2. Harness layer: reuse today's Tier-1 staging (must exist — run harness_snapshot.sh first)
[ -d "$SNAP" ] || { echo "run harness_snapshot.sh first"; exit 1; }
rsync -a "$SNAP/config" "$SNAP/memory" "$SNAP/wiki.tar.gz" "$SNAP/patches" "$SNAP/MANIFEST.txt" "$STAGE/harness/" 2>/dev/null || true
[ -f "$SNAP/tvw-project-claude.tar.gz" ] && cp "$SNAP/tvw-project-claude.tar.gz" "$STAGE/harness/"

# 3. Reproduction instructions
cat > "$STAGE/REPRODUCE.md" <<'EOF'
# Reproducing the Tychon Verification Workbench environment
This capsule contains the repo AND the behavioral layers that make sessions in
it act the way they do. To reconstruct on a fresh machine:

1. Repos: `git clone bundles/tychon-verification-workbench.bundle ~/projects/tychon-verification-workbench`
   (same for claude-config, outreach, skills, audit-workspace). Apply any
   `harness/patches/*.pending.patch` for uncommitted state at capture time.
2. CLAUDE.md wiring: repo CLAUDE.md files are symlinks into
   `~/projects/claude-config/projects/<repo>/CLAUDE.md` — recreate the symlinks
   (`ln -s ../claude-config/projects/<repo>/CLAUDE.md CLAUDE.md`; AGENTS.md -> CLAUDE.md).
3. Global harness: copy `harness/config/CLAUDE.md`, `settings.json`,
   `keybindings.json` into `~/.claude/`; copy `harness/config/hooks/` to
   `~/.claude/hooks/` (chmod +x). Credentials are deliberately NOT in this
   capsule — re-authenticate normally.
4. Memory: copy each `harness/memory/<project-slug>/` to
   `~/.claude/projects/<project-slug>/memory/`.
5. Wiki: extract `harness/wiki.tar.gz` to `~/Desktop/Shared/` (Syncthing share).
6. Plugins/MCP: install the plugin list recorded in `harness/MANIFEST.txt`;
   MCP servers launch via mcp-env-run with keys from `~/.openclaw/.env`
   (not included — secrets never travel in this capsule).
7. NOT included, by design: `~/.corpus` (13G — rebuild via the skills-repo
   corpus pipeline or restore from the NAS corpus backups), session
   transcripts (history, already ingested into corpora), any credential.

What makes the environment "special" is layered context, not code alone:
global rules -> project CLAUDE.md (claude-config) -> project memory ->
SessionStart hook (wiki NOW.md injection) -> lane role. All five layers are in
this capsule. See the companion doc `TVW_Anatomy_*.md` in the shared folder.
EOF

# 4. Capsule manifest
{
  echo "tvw-genome capsule created: $(date '+%Y-%m-%d %H:%M %Z') host: $(hostname)"
  echo "---sha256---"
  (cd "$STAGE" && find . -type f ! -name CAPSULE_MANIFEST.txt -exec sha256sum {} \;)
} > "$STAGE/CAPSULE_MANIFEST.txt"
echo "Tier 3: $(du -sh "$STAGE" | cut -f1) staged at $STAGE"
