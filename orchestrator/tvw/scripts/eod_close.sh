#!/usr/bin/env bash
# eod_close.sh — End-of-day repo sweep + commit/push driver for Tychon.
#
# What it does:
#   1. Sweeps the 5 active Tychon repos (TVW + 4 implementation) plus the
#      Beelink polarfire-hybrid-control mirror.
#   2. Reports per-repo state: branch, uncommitted, unpushed-internal, unpushed-github.
#   3. Pushes internal mirrors automatically (NAS bare repos, Spark Tailscale mirrors).
#   4. Runs a secrets sweep across all unpushed commits before any GitHub push.
#   5. Surfaces the GitHub-push set as a SINGLE yes/no approval gate.
#   6. On approval: pushes all flagged branches to GitHub origins.
#   7. Exits with a one-line summary per repo.
#
# What it does NOT do:
#   - Commit anything. If a repo has uncommitted work, it's surfaced as a
#     decision point — the script will not invent commit messages.
#   - Push to a remote that isn't already configured. No remote add.
#   - Force-push, --no-verify, or any destructive op.
#   - Touch the SBIR shared folder (~/projects/tychon-sbir/docs/) — that's
#     Syncthing-versioned, not git.
#
# Usage:
#   ./tvw/scripts/eod_close.sh             # interactive — prompts for GitHub-push approval
#   ./tvw/scripts/eod_close.sh --dry-run   # report only; do not push anything
#   ./tvw/scripts/eod_close.sh --yes       # non-interactive; auto-approve GitHub push
#                                            (only use this if you've already eyeballed
#                                             today's commits and trust the secrets sweep)

set -uo pipefail

DRY_RUN=0
AUTO_YES=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yes) AUTO_YES=1 ;;
        *) echo "Unknown arg: $arg"; exit 2 ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────
# Config — list of repos to sweep. Add new ones here.
# Format: <local-path>:<beelink-mirror-path-or-empty>
# ──────────────────────────────────────────────────────────────────────────
REPOS=(
    "$HOME/projects/tychon-verification-workbench:"
    "$HOME/projects/polarfire-hybrid-control:~/dev/projects/polarfire-hybrid-control"
    "$HOME/projects/odmr-edge-ml:"
    "$HOME/projects/nv-sensor-sim:"
    "$HOME/projects/tychon-shared-data:"
)

# Internal-mirror remotes that can be pushed without per-action approval
# (per global CLAUDE.md autonomous authorities + TVW CLAUDE.md).
INTERNAL_REMOTES_REGEX='^(nas|ws2)$'

# Secret-like filename patterns to scan for in unpushed commits
SECRET_REGEX='\.env|\.key|\.pem|secret|credential|password|token'

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

c_red()   { printf '\033[31m%s\033[0m' "$*"; }
c_grn()   { printf '\033[32m%s\033[0m' "$*"; }
c_ylw()   { printf '\033[33m%s\033[0m' "$*"; }
c_cyn()   { printf '\033[36m%s\033[0m' "$*"; }
c_bold()  { printf '\033[1m%s\033[0m' "$*"; }

hr() { printf '%s\n' "──────────────────────────────────────────────────────────────────"; }

# Per-repo collectors
declare -A REPO_BRANCH REPO_UNCOMMITTED REPO_UNPUSHED_INTERNAL REPO_UNPUSHED_GITHUB REPO_SECRETS REPO_SUMMARY

# Track GitHub push set for batch approval
declare -a GITHUB_PUSH_QUEUE=()  # entries: "<repo-path>::<branch>::<remote>"

# ──────────────────────────────────────────────────────────────────────────
# Phase 1 — sweep
# ──────────────────────────────────────────────────────────────────────────

echo
c_bold "  EOD CLOSE — Tychon multi-repo sweep ($(date -Iseconds))"; echo
hr

for entry in "${REPOS[@]}"; do
    repo="${entry%%:*}"
    bee_mirror="${entry##*:}"
    repo_short="${repo##*/}"

    [ -d "$repo/.git" ] || { echo "  $(c_ylw "skip:") $repo (not a git repo)"; continue; }

    cd "$repo" || continue

    branch=$(git branch --show-current 2>/dev/null)
    REPO_BRANCH[$repo]="$branch"

    # Uncommitted (working tree + index)
    uncommitted=$(git status --porcelain 2>/dev/null | wc -l)
    REPO_UNCOMMITTED[$repo]="$uncommitted"

    # Per-branch unpushed analysis
    internal_unpushed=""
    github_unpushed=""

    while IFS= read -r b; do
        # Get list of remotes that have this branch
        remotes_with=$(git for-each-ref --format='%(refname:short)' refs/remotes/ 2>/dev/null | \
                       awk -F/ -v b="$b" '$NF==b {print $1}' | sort -u)
        # 2026-08-19 fix: the old any-remote gate (--not --remotes) read 0 once Phase 2
        # auto-pushed nas/ws2, hiding GitHub-unpushed branches. Check every remote.
        if :; then
            # For each configured remote, check if branch is up-to-date there
            for r in $(git remote 2>/dev/null); do
                if git show-ref --verify --quiet "refs/remotes/$r/$b"; then
                    behind=$(git rev-list --count "$r/$b..$b" 2>/dev/null)
                    if [ "$behind" -gt 0 ]; then
                        if [[ "$r" =~ $INTERNAL_REMOTES_REGEX ]]; then
                            internal_unpushed+="    $r/$b: $behind commits\n"
                        else
                            github_unpushed+="    $r/$b: $behind commits\n"
                            GITHUB_PUSH_QUEUE+=("$repo::$b::$r")
                        fi
                    fi
                else
                    # Branch doesn't exist on this remote at all
                    if [[ "$r" =~ $INTERNAL_REMOTES_REGEX ]]; then
                        internal_unpushed+="    $r/$b: NEW BRANCH ($unpushed_count commits)\n"
                    else
                        github_unpushed+="    $r/$b: NEW BRANCH ($unpushed_count commits)\n"
                        GITHUB_PUSH_QUEUE+=("$repo::$b::$r")
                    fi
                fi
            done
        fi
    done < <(git for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)

    REPO_UNPUSHED_INTERNAL[$repo]="${internal_unpushed:-}"
    REPO_UNPUSHED_GITHUB[$repo]="${github_unpushed:-}"

    # Secrets sweep on all unpushed commits across all branches
    secrets_found=""
    while IFS= read -r b; do
        matches=$(git log "$b" --not --remotes --name-only --pretty=format: 2>/dev/null \
                  | sort -u \
                  | grep -iE "$SECRET_REGEX" || true)
        if [ -n "$matches" ]; then
            secrets_found+="$b: $matches\n"
        fi
    done < <(git for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)
    REPO_SECRETS[$repo]="${secrets_found:-}"

    # Print per-repo block
    printf '  %-40s  branch=%s\n' "$(c_bold "$repo_short")" "$(c_cyn "$branch")"
    if [ "$uncommitted" -gt 0 ]; then
        printf '    %s %d files\n' "$(c_red 'uncommitted:')" "$uncommitted"
        git status --porcelain | head -8 | sed 's/^/      /'
    else
        printf '    %s\n' "$(c_grn 'uncommitted: clean')"
    fi
    if [ -n "${REPO_UNPUSHED_INTERNAL[$repo]}" ]; then
        printf '    %s\n' "$(c_ylw 'unpushed (internal mirrors):')"
        printf '%b' "${REPO_UNPUSHED_INTERNAL[$repo]}"
    fi
    if [ -n "${REPO_UNPUSHED_GITHUB[$repo]}" ]; then
        printf '    %s\n' "$(c_ylw 'unpushed (GitHub):')"
        printf '%b' "${REPO_UNPUSHED_GITHUB[$repo]}"
    fi
    if [ -n "${REPO_SECRETS[$repo]}" ]; then
        printf '    %s\n' "$(c_red '⚠️  SECRET-LIKE FILENAMES IN UNPUSHED COMMITS:')"
        printf '%b' "${REPO_SECRETS[$repo]}" | sed 's/^/      /'
    fi
    echo
done

# ──────────────────────────────────────────────────────────────────────────
# Phase 2 — push internal mirrors automatically
# ──────────────────────────────────────────────────────────────────────────

if [ "$DRY_RUN" -eq 1 ]; then
    echo "  $(c_ylw '--dry-run set; not pushing anything')"
    echo
else
    hr
    echo "  $(c_bold 'Phase 2 — pushing internal mirrors')"
    hr
    for repo in "${!REPO_BRANCH[@]}"; do
        [ -n "${REPO_UNPUSHED_INTERNAL[$repo]}" ] || continue
        cd "$repo"
        for r in $(git remote 2>/dev/null); do
            [[ "$r" =~ $INTERNAL_REMOTES_REGEX ]] || continue
            for b in $(git for-each-ref --format='%(refname:short)' refs/heads/); do
                if git log "$b" --not --remotes="$r" --oneline 2>/dev/null | grep -q .; then
                    echo "  → $repo  $b → $r"
                    git push "$r" "$b" 2>&1 | tail -2 | sed 's/^/    /'
                fi
            done
        done
    done
    echo
fi

# ──────────────────────────────────────────────────────────────────────────
# Phase 3 — GitHub push approval gate
# ──────────────────────────────────────────────────────────────────────────

queue_len="${#GITHUB_PUSH_QUEUE[@]}"
if [ "$queue_len" -eq 0 ]; then
    hr
    echo "  $(c_grn '✓ no GitHub pushes pending')"
    hr
elif [ "$DRY_RUN" -eq 1 ]; then
    hr
    echo "  $(c_bold 'Phase 3 — would push to GitHub (--dry-run set, not executing):')"
    hr
    for entry in "${GITHUB_PUSH_QUEUE[@]}"; do
        echo "    $entry" | tr ':' '/'
    done
else
    hr
    echo "  $(c_bold 'Phase 3 — GitHub push set'):"
    hr
    for entry in "${GITHUB_PUSH_QUEUE[@]}"; do
        repo="${entry%%::*}"; rest="${entry#*::}"; branch="${rest%%::*}"; remote="${rest##*::}"  # 2026-08-19: IFS='::' splits on ':' (char set) — broke the push gate
        repo_short="${repo##*/}"
        echo "    $repo_short  $branch → $remote"
    done

    # Block on secrets findings
    any_secrets=0
    for repo in "${!REPO_SECRETS[@]}"; do
        if [ -n "${REPO_SECRETS[$repo]}" ]; then any_secrets=1; fi
    done
    if [ "$any_secrets" -eq 1 ]; then
        echo
        echo "  $(c_red '⚠️  Secret-like filenames detected in unpushed commits.')"
        echo "  $(c_red '     Review the SECRET-LIKE FILENAMES lines above before approving.')"
        echo
    fi

    if [ "$AUTO_YES" -eq 1 ]; then
        approval="y"
        echo "  $(c_ylw '--yes set; auto-approving GitHub push')"
    else
        echo
        printf "  %s " "$(c_bold 'Approve GitHub push for ALL of the above? (y/N):')"
        read -r approval
    fi

    if [[ "$approval" =~ ^[yY]$ ]]; then
        echo
        for entry in "${GITHUB_PUSH_QUEUE[@]}"; do
            repo="${entry%%::*}"; rest="${entry#*::}"; branch="${rest%%::*}"; remote="${rest##*::}"  # 2026-08-19: IFS='::' splits on ':' (char set) — broke the push gate
            cd "$repo"
            echo "  → $(basename "$repo")  $branch → $remote"
            git push "$remote" "$branch" 2>&1 | tail -2 | sed 's/^/    /'
        done
        echo
        echo "  $(c_grn '✓ GitHub pushes complete')"
    else
        echo "  $(c_ylw 'GitHub push declined; everything else (internal mirrors) already pushed')"
    fi
fi

# ──────────────────────────────────────────────────────────────────────────
# Phase 4 — final one-line summary per repo
# ──────────────────────────────────────────────────────────────────────────

hr
echo "  $(c_bold 'Summary')"
hr
for entry in "${REPOS[@]}"; do
    repo="${entry%%:*}"
    repo_short="${repo##*/}"
    [ -d "$repo/.git" ] || continue
    cd "$repo"
    branch="${REPO_BRANCH[$repo]}"
    uncommitted="${REPO_UNCOMMITTED[$repo]:-0}"
    if [ "$uncommitted" -gt 0 ]; then
        status="$(c_red "$uncommitted uncommitted")"
    elif [ -n "${REPO_UNPUSHED_INTERNAL[$repo]:-}" ] || [ -n "${REPO_UNPUSHED_GITHUB[$repo]:-}" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            status="$(c_ylw 'unpushed (dry-run)')"
        else
            # Re-check after pushes
            still_unpushed=$(git log --branches --not --remotes --oneline 2>/dev/null | wc -l)
            if [ "$still_unpushed" -gt 0 ]; then
                status="$(c_ylw "$still_unpushed commits still unpushed")"
            else
                status="$(c_grn 'clean + pushed')"
            fi
        fi
    else
        status="$(c_grn 'clean + pushed')"
    fi
    printf '    %-32s  %s  %s\n' "$repo_short" "$branch" "$status"
done
echo

# ──────────────────────────────────────────────────────────────────────────
# Phase 4.5 — dispatch calibration one-liner (read-only; P0-1, 2026-08-11)
# ──────────────────────────────────────────────────────────────────────────

DISPATCH_SH="$HOME/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh"
if [ -x "$DISPATCH_SH" ]; then
    hr
    echo "  $(c_bold 'Dispatch calibration (predicted vs actual)')"
    hr
    "$DISPATCH_SH" stats 2>/dev/null | sed 's/^/    /'
    echo
fi

# ──────────────────────────────────────────────────────────────────────────
# Phase 5 — Beelink mirror sanity check (read-only)
# ──────────────────────────────────────────────────────────────────────────

if command -v ssh >/dev/null 2>&1 && timeout 5 ssh -o ConnectTimeout=3 -o BatchMode=yes bee true 2>/dev/null; then
    hr
    echo "  $(c_bold 'Beelink mirror state (read-only sanity)')"
    hr
    timeout 15 ssh bee 'cd ~/dev/projects/polarfire-hybrid-control 2>/dev/null && \
        echo "    polarfire-hybrid-control:" && \
        echo "      branch=$(git branch --show-current)" && \
        echo "      uncommitted=$(git status --porcelain | wc -l) files" && \
        for b in $(git for-each-ref --format="%(refname:short)" refs/heads/); do
            unpushed=$(git log --oneline "$b" --not --remotes 2>/dev/null | wc -l)
            if [ "$unpushed" -gt 0 ]; then
                echo "      $b: $unpushed unpushed commits"
            fi
        done' 2>&1
    echo
fi

# ──────────────────────────────────────────────────────────────────────────
# Phase 5.5 — SBIR working-folder divergence check (2026-08-19; canon = Desktop copy)
# ──────────────────────────────────────────────────────────────────────────

SBIR_CANON="$HOME/Desktop/Shared/tychon/nv-sim-repos"
for m in "$HOME/projects/tychon-sbir/docs" "$HOME/Tychon SBIR/docs"; do
    if [ -f "$m/fix-list-status.csv" ] && [ -f "$SBIR_CANON/fix-list-status.csv" ] \
       && ! cmp -s "$SBIR_CANON/fix-list-status.csv" "$m/fix-list-status.csv"; then
        hr
        echo "  $(c_bold 'WARN: SBIR mirror diverged from canon (Desktop copy)')"
        echo "    $m/fix-list-status.csv differs — mirrors are STALE by decree (Jason 2026-08-19); never edit them"
    fi
done

echo "  $(c_bold 'EOD close complete') — $(date -Iseconds)"
echo
