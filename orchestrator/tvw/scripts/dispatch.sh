#!/usr/bin/env bash
# dispatch.sh — file-based cross-lane dispatch queue (MANUAL + VISIBLE by design).
#
# Kills the paste-truncation failure mode: dispatch bodies travel as files end to
# end and every dispatch carries a sha256 of its body, so any loss is detectable.
#
# Design constraints (Jason, fleet-audit override #3, 2026-07-10):
#   - NO SessionStart hooks, NO auto-consumption, NO background automation.
#   - Every dispatch is a plain markdown file a human can read, list, and grep.
#   - Nothing is consumed invisibly: a worker lane reads a dispatch with `show`
#     and closes it with `ack`; acked dispatches are KEPT in done/ as a record.
#
# Queue layout (per-target-lane inboxes, per QW12 spec):
#   ~/projects/<lane>/.dispatch/inbox/<id>.md   pending dispatches for that lane
#   ~/projects/<lane>/.dispatch/done/<id>.md    acked dispatches (permanent record)
# .dispatch/ is kept out of each repo's git status via .git/info/exclude
# (local-only config — no tracked files in worker repos are ever touched).
#
# Dispatch file format:
#   ---
#   id: 2026-07-10-1432-<slug>
#   date: <ISO8601>
#   from-lane: <lane>
#   to-lane: <lane>
#   title: <title>
#   predicted-hours: <float>      (optional, from send --predict; P0-1 calibration 2026-08-11)
#   predicted-sessions: <int>     (optional, from send --predict)
#   p-success: <0..1>             (optional, from send --predict; elicited answer-free, pre-execution)
#   status: pending|done
#   sha256: <sha256 of body>
#   actual-hours: <float>         (optional, from ack --actual)
#   actual-sessions: <int>        (optional, from ack --actual)
#   outcome: success|partial|fail (optional, from ack --actual)
#   ---
#   <blank line>
#   <body, verbatim>
#
# Plain bash + coreutils/POSIX tools only (awk, sed, sha256sum, find, date).

set -uo pipefail

LANES_ROOT="${DISPATCH_LANES_ROOT:-$HOME/projects}"
SELF_LANE_DEFAULT="tychon-verification-workbench"

usage() {
cat <<EOF
dispatch.sh — lossless, file-based dispatch between Claude lanes (manual by design)

  send <to-lane> <title> [--file <path>] [--from <lane>]  queue a dispatch; body from --file or stdin
       [--predict <hours>,<sessions>,<p_success>]         effort prediction (P0-1 calibration; elicit
                                                          BEFORE writing the body — answer-free)
  list [--all] [--lane <lane>]                            one line per dispatch (default: pending only)
  show <id>                                               print a dispatch and verify its sha256
  ack <id> [--actual <hours>,<sessions>,<outcome>] [note] mark done: restamps + moves inbox/ -> done/
                                                          outcome: success|partial|fail
  stats [--lane <lane>] [--full]                          predicted-vs-actual calibration report

Workflow: TVW runs 'send' -> file lands in ~/projects/<to-lane>/.dispatch/inbox/ ->
Jason tells the worker session "check your dispatch inbox" (a one-liner, nothing to
truncate) -> worker runs 'show <id>' (sha256-verified, so truncation is impossible to
miss), does the work, then 'ack <id> [note]'. Acked files are kept in .dispatch/done/
as the permanent cross-lane record. Nothing is auto-consumed; every flow is visible.
EOF
}

die() { echo "dispatch: error: $*" >&2; exit 1; }

# ── helpers ────────────────────────────────────────────────────────────────

slugify() {
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9]\{1,\}/-/g' -e 's/^-\{1,\}//' \
        | cut -c1-40 | sed 's/-\{1,\}$//'
}

valid_lane_name() {
    [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]
}

# Print body bytes exactly as stored: everything after the frontmatter's closing
# '---' line, minus the single blank separator line.
extract_body() {
    awk '
        body == 1 {
            if (sep_skipped == 0 && $0 == "") { sep_skipped = 1; next }
            sep_skipped = 1; print; next
        }
        /^---$/ { fm++; if (fm == 2) body = 1 }
    ' "$1"
}

# Read one frontmatter value: fm_get <file> <key>
fm_get() {
    awk -v k="$2" '
        NR == 1 && $0 != "---" { exit }
        /^---$/ { fm++; if (fm == 2) exit; next }
        fm == 1 && index($0, k ": ") == 1 { print substr($0, length(k) + 3); exit }
    ' "$1"
}

# Echo every dispatch file, inbox first then done, sorted by filename (= by date).
all_dispatch_files() {  # $1 = "pending"|"all"   $2 = lane filter or ""
    local lane_dir subdirs="inbox"
    [ "$1" = "all" ] && subdirs="inbox done"
    for lane_dir in "$LANES_ROOT"/*/; do
        [ -d "$lane_dir" ] || continue
        local lane; lane="$(basename "$lane_dir")"
        [ -n "$2" ] && [ "$lane" != "$2" ] && continue
        local sub
        for sub in $subdirs; do
            [ -d "$lane_dir.dispatch/$sub" ] || continue
            find "$lane_dir.dispatch/$sub" -maxdepth 1 -type f -name '*.md' 2>/dev/null
        done
    done
}

# Locate a dispatch by id across all lanes; die if 0 or >1 matches.
find_dispatch_file() {
    local id="$1" matches
    matches="$(all_dispatch_files all "" | grep -F "/$id.md" || true)"
    [ -n "$matches" ] || die "no dispatch found with id '$id' (try: dispatch.sh list --all)"
    if [ "$(printf '%s\n' "$matches" | wc -l)" -gt 1 ]; then
        printf '%s\n' "$matches" >&2
        die "id '$id' is ambiguous (matches above)"
    fi
    printf '%s' "$matches"
}

# Keep .dispatch/ out of a lane repo's git status without touching tracked files.
ensure_git_exclude() {
    local lane_path="$1" exclude
    [ -d "$lane_path/.git" ] || return 0
    exclude="$lane_path/.git/info/exclude"
    mkdir -p "$lane_path/.git/info"
    if ! grep -qxF '.dispatch/' "$exclude" 2>/dev/null; then
        echo '.dispatch/' >> "$exclude"
        echo "note: added '.dispatch/' to $exclude (local-only, keeps git status clean)"
    fi
}

# ── send ───────────────────────────────────────────────────────────────────

cmd_send() {
    local to_lane="" title="" body_src="" from_lane="" predict=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --file) [ $# -ge 2 ] || die "--file needs a path"; body_src="$2"; shift 2 ;;
            --from) [ $# -ge 2 ] || die "--from needs a lane"; from_lane="$2"; shift 2 ;;
            --predict) [ $# -ge 2 ] || die "--predict needs <hours>,<sessions>,<p_success>"; predict="$2"; shift 2 ;;
            -*) die "unknown flag for send: $1" ;;
            *)  if   [ -z "$to_lane" ]; then to_lane="$1"
                elif [ -z "$title" ];   then title="$1"
                else die "unexpected extra argument: $1"; fi
                shift ;;
        esac
    done
    [ -n "$to_lane" ] && [ -n "$title" ] || { usage >&2; die "send needs <to-lane> and <title>"; }
    valid_lane_name "$to_lane" || die "invalid lane name: '$to_lane'"
    [ -d "$LANES_ROOT/$to_lane" ] || die "no such lane: $LANES_ROOT/$to_lane"

    # from-lane: --from > enclosing ~/projects/<lane> of cwd > TVW default
    if [ -z "$from_lane" ]; then
        case "$PWD/" in
            "$LANES_ROOT"/*) from_lane="${PWD#"$LANES_ROOT"/}"; from_lane="${from_lane%%/*}" ;;
            *) from_lane="$SELF_LANE_DEFAULT" ;;
        esac
    fi
    valid_lane_name "$from_lane" || die "invalid from-lane: '$from_lane'"

    # Body: from --file or stdin. Never passes through an argv/paste boundary.
    local tmp; tmp="$(mktemp)"; trap "rm -f '$tmp'" EXIT
    if [ -n "$body_src" ]; then
        [ -f "$body_src" ] || die "body file not found: $body_src"
        cat "$body_src" > "$tmp"
    else
        [ ! -t 0 ] || die "no body: pass --file <path> or pipe the body on stdin"
        cat > "$tmp"
    fi
    [ -s "$tmp" ] || die "dispatch body is empty"
    # Normalize: ensure exactly a trailing newline so storage is byte-faithful.
    [ -z "$(tail -c1 "$tmp")" ] || echo >> "$tmp"

    # Calibration prediction (P0-1, 2026-08-11): --predict <hours>,<sessions>,<p_success>
    local p_hours="" p_sessions="" p_succ=""
    if [ -n "$predict" ]; then
        IFS=',' read -r p_hours p_sessions p_succ <<< "$predict"
        [[ "$p_hours"    =~ ^[0-9]+([.][0-9]+)?$ ]] || die "--predict hours must be numeric (got '$p_hours')"
        [[ "$p_sessions" =~ ^[0-9]+$ ]]             || die "--predict sessions must be an integer (got '$p_sessions')"
        [[ "$p_succ"     =~ ^(0([.][0-9]+)?|1([.]0+)?)$ ]] || die "--predict p_success must be 0..1 (got '$p_succ')"
    else
        echo "note: no --predict given — this dispatch will not contribute to calibration stats" >&2
    fi

    local sha bytes; sha="$(sha256sum < "$tmp" | awk '{print $1}')"
    bytes="$(wc -c < "$tmp" | tr -d ' ')"

    # Unique id: YYYY-MM-DD-HHMM-<slug>, suffixed -2, -3... on collision (any lane).
    local slug id n=1
    slug="$(slugify "$title")"; [ -n "$slug" ] || slug="dispatch"
    id="$(date +%Y-%m-%d-%H%M)-$slug"
    while [ -n "$(all_dispatch_files all "" | grep -F "/$id.md" || true)" ]; do
        n=$((n + 1)); id="$(date +%Y-%m-%d-%H%M)-$slug-$n"
    done

    local qdir="$LANES_ROOT/$to_lane/.dispatch"
    mkdir -p "$qdir/inbox" "$qdir/done"
    ensure_git_exclude "$LANES_ROOT/$to_lane"

    local out="$qdir/inbox/$id.md"
    {
        echo '---'
        echo "id: $id"
        echo "date: $(date -Iseconds)"
        echo "from-lane: $from_lane"
        echo "to-lane: $to_lane"
        echo "title: $title"
        if [ -n "$p_hours" ]; then
            echo "predicted-hours: $p_hours"
            echo "predicted-sessions: $p_sessions"
            echo "p-success: $p_succ"
        fi
        echo "status: pending"
        echo "sha256: $sha"
        echo '---'
        echo
        cat "$tmp"
    } > "$out"

    # Prove no truncation: extracted body must be byte-identical to the input.
    if ! extract_body "$out" | cmp -s - "$tmp"; then
        rm -f "$out"
        die "INTEGRITY FAILURE: stored body differs from input — dispatch NOT queued"
    fi

    echo "queued: $id"
    echo "  file:      $out"
    echo "  body:      $bytes bytes, sha256 $sha"
    echo "  integrity: verified (stored body byte-identical to input)"
    echo "  consume:   $0 show $id   (then: $0 ack $id)"
}

# ── list ───────────────────────────────────────────────────────────────────

cmd_list() {
    local scope="pending" lane=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --all) scope="all"; shift ;;
            --lane) [ $# -ge 2 ] || die "--lane needs a lane"; lane="$2"; shift 2 ;;
            *) die "unknown flag for list: $1" ;;
        esac
    done
    local files; files="$(all_dispatch_files "$scope" "$lane" | sort)"
    if [ -z "$files" ]; then
        [ "$scope" = "pending" ] \
            && echo "no pending dispatches${lane:+ for lane '$lane'} (use --all to include acked)" \
            || echo "no dispatches${lane:+ for lane '$lane'}"
        return 0
    fi
    printf '%-46s %-8s %-45s %s\n' "ID" "STATUS" "FROM -> TO" "TITLE"
    local f
    while IFS= read -r f; do
        printf '%-46s %-8s %-45s %s\n' \
            "$(fm_get "$f" id)" \
            "$(fm_get "$f" status)" \
            "$(fm_get "$f" from-lane) -> $(fm_get "$f" to-lane)" \
            "$(fm_get "$f" title)"
    done <<< "$files"
}

# ── show ───────────────────────────────────────────────────────────────────

cmd_show() {
    [ $# -eq 1 ] || die "usage: dispatch.sh show <id>"
    local f; f="$(find_dispatch_file "$1")"
    cat "$f"
    echo "──────────────────────────────────────────────────────────────────"
    echo "file: $f"
    local stored actual bytes
    stored="$(fm_get "$f" sha256)"
    actual="$(extract_body "$f" | sha256sum | awk '{print $1}')"
    bytes="$(extract_body "$f" | wc -c | tr -d ' ')"
    if [ "$stored" = "$actual" ]; then
        echo "integrity: OK — sha256 verified, body $bytes bytes intact"
    else
        echo "integrity: MISMATCH — body may be TRUNCATED or edited!"
        echo "  expected: $stored"
        echo "  actual:   $actual"
        exit 1
    fi
}

# ── ack ────────────────────────────────────────────────────────────────────

cmd_ack() {
    [ $# -ge 1 ] || die "usage: dispatch.sh ack <id> [--actual <hours>,<sessions>,<outcome>] [note]"
    local id="$1"; shift
    # Calibration actuals (P0-1, 2026-08-11): --actual <hours>,<sessions>,<outcome>
    local actual="" a_hours="" a_sessions="" a_outcome=""
    if [ "${1:-}" = "--actual" ]; then
        [ $# -ge 2 ] || die "--actual needs <hours>,<sessions>,<outcome>"
        actual="$2"; shift 2
        IFS=',' read -r a_hours a_sessions a_outcome <<< "$actual"
        [[ "$a_hours"    =~ ^[0-9]+([.][0-9]+)?$ ]]     || die "--actual hours must be numeric (got '$a_hours')"
        [[ "$a_sessions" =~ ^[0-9]+$ ]]                 || die "--actual sessions must be an integer (got '$a_sessions')"
        [[ "$a_outcome"  =~ ^(success|partial|fail)$ ]] || die "--actual outcome must be success|partial|fail (got '$a_outcome')"
    fi
    local note="${*:-}"
    local f; f="$(find_dispatch_file "$id")"
    if [ -z "$actual" ] && [ -n "$(fm_get "$f" predicted-hours)" ]; then
        echo "note: dispatch has predictions but no --actual given — calibration row will be incomplete" >&2
    fi
    case "$f" in
        */.dispatch/done/*) echo "already acked: $f"; return 0 ;;
        */.dispatch/inbox/*) : ;;
        *) die "unexpected dispatch location: $f" ;;
    esac
    local dest_dir dest tmp
    dest_dir="$(dirname "$(dirname "$f")")/done"
    dest="$dest_dir/$id.md"
    mkdir -p "$dest_dir"
    tmp="$(mktemp)"; trap "rm -f '$tmp'" EXIT
    awk -v acked="$(date -Iseconds)" -v note="$note" \
        -v ah="$a_hours" -v as="$a_sessions" -v ao="$a_outcome" '
        fm < 2 && /^status: / { print "status: done"
                                print "acked: " acked
                                if (note != "") print "ack-note: " note
                                if (ah != "") { print "actual-hours: " ah
                                                print "actual-sessions: " as
                                                print "outcome: " ao }
                                next }
        /^---$/ { fm++ }
        { print }
    ' "$f" > "$tmp"
    # Body must be untouched by the restamp.
    if ! extract_body "$tmp" | cmp -s - <(extract_body "$f"); then
        die "INTEGRITY FAILURE: ack would alter the body — aborted, file unchanged"
    fi
    mv "$tmp" "$dest" && rm -f "$f"
    trap - EXIT
    echo "acked: $id"
    echo "  record kept at: $dest"
}

# ── stats ──────────────────────────────────────────────────────────────────
# Predicted-vs-actual calibration over acked dispatches (P0-1, 2026-08-11).
# One-liner by default; --full prints per-dispatch rows. Brier scored against
# outcome success=1 / partial=0.5 / fail=0; hours error as geometric mean of
# actual/predicted (log-symmetric, so x2 over and x0.5 under cancel).

cmd_stats() {
    local lane="" full=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --lane) [ $# -ge 2 ] || die "--lane needs a lane"; lane="$2"; shift 2 ;;
            --full) full=1; shift ;;
            *) die "unknown flag for stats: $1" ;;
        esac
    done
    local f rows=""
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        case "$f" in */.dispatch/done/*) : ;; *) continue ;; esac
        local ph ah ps oc did
        ph="$(fm_get "$f" predicted-hours)"; ah="$(fm_get "$f" actual-hours)"
        [ -n "$ph" ] && [ -n "$ah" ] || continue
        ps="$(fm_get "$f" p-success)"; oc="$(fm_get "$f" outcome)"
        did="$(fm_get "$f" id)"
        rows+="$did|$ph|$ah|${ps:--}|${oc:--}"$'\n'
    done <<< "$(all_dispatch_files all "$lane")"

    if [ -z "$rows" ]; then
        echo "calibration: n=0 — no acked dispatches with predicted+actual fields yet"
        return 0
    fi
    printf '%s' "$rows" | awk -F'|' -v full="$full" '
        BEGIN { n = 0; nb = 0; sumlog = 0; brier = 0; ok = 0; part = 0; bad = 0 }
        NF >= 5 {
            n++
            ratio = $3 / $2
            sumlog += log(ratio)
            if (full) printf "  %-46s pred %sh  actual %sh  (x%.2f)  p=%s  %s\n", $1, $2, $3, ratio, $4, $5
            if ($4 != "-" && $5 != "-") {
                o = ($5 == "success") ? 1 : ($5 == "partial") ? 0.5 : 0
                brier += ($4 - o) ^ 2; nb++
            }
            if ($5 == "success") ok++; else if ($5 == "partial") part++; else if ($5 == "fail") bad++
        }
        END {
            if (n == 0) { print "calibration: n=0"; exit }
            gm = exp(sumlog / n)
            line = sprintf("calibration: n=%d | hours actual/pred geo-mean x%.2f (%s)", n, gm,
                           gm > 1.15 ? "under-estimating" : gm < 0.87 ? "over-estimating" : "well calibrated")
            if (nb > 0) line = line sprintf(" | p_success Brier %.3f (n=%d)", brier / nb, nb)
            line = line sprintf(" | outcomes %d ok / %d partial / %d fail", ok, part, bad)
            if (n < 20) line = line " | collecting — report firms up at n>=20"
            print line
        }'
}

# ── main ───────────────────────────────────────────────────────────────────

cmd="${1:-}"
[ $# -gt 0 ] && shift
case "$cmd" in
    send)  cmd_send  "$@" ;;
    list)  cmd_list  "$@" ;;
    show)  cmd_show  "$@" ;;
    ack)   cmd_ack   "$@" ;;
    stats) cmd_stats "$@" ;;
    -h|--help|help|"") usage ;;
    *) usage >&2; die "unknown command: $cmd" ;;
esac
