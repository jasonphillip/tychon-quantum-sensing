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
# Bash 3.2 + standard GNU/BSD tools (awk, sed, sha256sum or shasum, date).

set -uo pipefail

LANES_ROOT="${DISPATCH_ROOT:-${DISPATCH_LANES_ROOT:-$HOME/projects}}"
LANES_ROOT="${LANES_ROOT%/}"
SELF_LANE_DEFAULT="tychon-verification-workbench"
TMP_FILE="" ENVELOPE_TMP="" LOCK_DIR=""

cleanup() {
    [ -z "$TMP_FILE" ] || rm -f "$TMP_FILE"
    [ -z "$ENVELOPE_TMP" ] || rm -f "$ENVELOPE_TMP"
    [ -z "$LOCK_DIR" ] || rmdir "$LOCK_DIR" 2>/dev/null
    return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

usage() {
cat <<EOF
dispatch.sh — lossless, file-based dispatch between Claude lanes (manual by design)

  send <to-lane> <title> [--file <path>] [--from <lane>]  queue a dispatch; body from --file or stdin
       [--predict <hours>,<sessions>,<p_success>]         effort prediction (P0-1 calibration; elicit
                                                          BEFORE writing the body — answer-free)
  list [--all] [--lane <lane>]                            one line per dispatch (default: pending only)
  show <id>                                               print a dispatch and verify its sha256
  claim <id> [--by <name>] [--lease <hours>]               check out an inbox item (default: 24 hours)
  release <id> [--by <name>] [--force]                    remove a claim (holder only unless forced)
  ack <id> [--actual <hours>,<sessions>,<outcome>] [note] mark done: restamps + moves inbox/ -> done/
       [--by <name>] [--force]                           respect live claims unless forced
                                                          outcome: success|partial|fail
  stats [--lane <lane>] [--full]                          predicted-vs-actual calibration report

Workflow: TVW runs 'send' -> file lands in ~/projects/<to-lane>/.dispatch/inbox/ ->
Jason tells the worker session "check your dispatch inbox" (a one-liner, nothing to
truncate) -> worker runs 'show <id>' (sha256-verified, so truncation is impossible to
miss), does the work, then 'ack <id> [note]'. Acked files are kept in .dispatch/done/
as the permanent cross-lane record. Nothing is auto-consumed; every flow is visible.
Claims are optional. --by defaults to the enclosing lane, else USER@hostname.
DISPATCH_ROOT overrides ~/projects (DISPATCH_LANES_ROOT remains supported).
EOF
}

die() { echo "dispatch: error: $*" >&2; exit 1; }
conflict() { echo "dispatch: $*" >&2; exit 3; }

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

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum
    else shasum -a 256; fi
}

iso_now() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
iso_epoch() {
    date -u -d "@$1" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null ||
        date -u -r "$1" '+%Y-%m-%dT%H:%M:%SZ'
}

default_holder() {
    local lane
    case "$PWD/" in
        "$LANES_ROOT"/*) lane="${PWD#"$LANES_ROOT"/}"; printf '%s\n' "${lane%%/*}" ;;
        *) printf '%s@%s\n' "${USER:-$(id -un)}" "$(hostname -s)" ;;
    esac
}

validate_holder() {
    [ -n "$1" ] && [[ "$1" != *$'\n'* && "$1" != *$'\r'* ]] || die "--by needs a nonempty, single-line name"
}

# Serialize claim transitions with ack. A committed done record is terminal.
# Locks are short lived; EXIT/HUP/INT/TERM remove them. No unsafe stale-lock stealing.
lock_dispatch() {
    local dir="${1%.md}.lock" tries=0
    while ! mkdir "$dir" 2>/dev/null; do
        # The previous writer may remove its lock just after mkdir fails.
        [ -d "${1%/*}" ] && [ -w "${1%/*}" ] || die "cannot create lock: $dir"
        [ ! -e "$dir" ] || [ -d "$dir" ] || die "lock path is not a directory: $dir"
        tries=$((tries + 1))
        [ "$tries" -lt 10 ] || conflict "busy: $dir (remove only after confirming its writer stopped)"
        sleep 1
    done
    LOCK_DIR="$dir"
}

require_inbox() {
    case "$1" in */.dispatch/inbox/*.md) : ;; *) die "dispatch is already acked" ;; esac
    [ -f "$1" ] && [ ! -e "$(dirname "$(dirname "$1")")/done/$(basename "$1")" ] || die "dispatch is already acked"
}

read_claim() {
    CLAIM_BY="$(fm_get "$1" by)"
    CLAIM_AT="$(fm_get "$1" claimed_at)"
    CLAIM_UNTIL="$(fm_get "$1" lease_until)"
    CLAIM_EPOCH="$(fm_get "$1" lease_until_epoch)"
    [ -n "$CLAIM_BY" ] && [ -n "$CLAIM_AT" ] && [ -n "$CLAIM_UNTIL" ] &&
        [[ "$CLAIM_EPOCH" =~ ^[0-9]{1,12}$ ]] || die "invalid claim: $1"
}

claim_live() { [ "$CLAIM_EPOCH" -gt "$(date +%s)" ]; }
claim_conflict() { conflict "claimed by $CLAIM_BY until $CLAIM_UNTIL"; }

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
            local f
            for f in "$lane_dir.dispatch/$sub/"*.md; do
                [ ! -f "$f" ] || printf '%s\n' "$f"
            done
        done
    done
}

# Locate an id across lanes. Only a same-lane inbox/done recovery pair is allowed.
find_dispatch_file() {
    local id="$1" matches f inbox="" done="" queue="" next_queue
    valid_lane_name "$id" || die "invalid dispatch id: '$id'"
    matches="$(all_dispatch_files all "" | while IFS= read -r f; do
        [ "${f##*/}" != "$id.md" ] || printf '%s\n' "$f"
    done)"
    [ -n "$matches" ] || die "no dispatch found with id '$id' (try: dispatch.sh list --all)"
    while IFS= read -r f; do
        next_queue="$(dirname "$(dirname "$f")")"
        [ -z "$queue" ] || [ "$queue" = "$next_queue" ] || die "id '$id' is ambiguous across lanes"
        queue="$next_queue"
        case "$f" in */.dispatch/inbox/*) inbox="$f" ;; */.dispatch/done/*) done="$f" ;; esac
    done <<< "$matches"
    # An interrupted ack may leave both copies in one lane.
    printf '%s' "${inbox:-$done}"
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
    local tmp; tmp="$(mktemp)" || die "cannot create body temporary file"; TMP_FILE="$tmp"
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

    local sha bytes; sha="$(sha256 < "$tmp" | awk '{print $1}')" || die "cannot hash body"
    bytes="$(wc -c < "$tmp" | tr -d ' ')"

    # Unique id: YYYY-MM-DD-HHMM-<slug>, suffixed -2, -3... on collision (any lane).
    local slug id base n=1
    slug="$(slugify "$title")"; [ -n "$slug" ] || slug="dispatch"
    base="$(date +%Y-%m-%d-%H%M)-$slug"; id="$base"

    local qdir="$LANES_ROOT/$to_lane/.dispatch"
    mkdir -p "$qdir/inbox" "$qdir/done" "$LANES_ROOT/.dispatch-ids" || die "cannot create queue directories"
    ensure_git_exclude "$LANES_ROOT/$to_lane"

    # Permanent mkdir reservations preserve global uniqueness across lanes and
    # inbox -> done moves. Existing queues need no migration. Gaps are harmless.
    local out
    while :; do
        if mkdir "$LANES_ROOT/.dispatch-ids/$id" 2>/dev/null; then
            if [ -z "$(all_dispatch_files all "" | grep -F "/$id.md" || true)" ]; then
                out="$qdir/inbox/$id.md"
                break
            fi
        else
            [ -d "$LANES_ROOT/.dispatch-ids/$id" ] || die "cannot reserve dispatch id: $id"
        fi
        n=$((n + 1)); id="$base-$n"
    done
    local envelope_tmp
    envelope_tmp="$(mktemp "$qdir/inbox/.$id.md.tmp.XXXXXX")" || die "cannot create envelope temporary file"
    ENVELOPE_TMP="$envelope_tmp"
    if ! {
        echo '---'
        echo "id: $id"
        echo "date: $(iso_now)"
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
        # Test-only: leave a partial body before the EXIT trap removes this temp file.
        if [ "${DISPATCH_TEST_ABORT_AT:-}" = body ]; then
            dd if="$tmp" bs=1 count=4 2>/dev/null
            false
        else
            cat "$tmp"
        fi
    } > "$envelope_tmp"; then
        die "cannot create envelope: $envelope_tmp"
    fi

    # Verify the frontmatter hash and body before the only visible publish step.
    if [ "$(fm_get "$envelope_tmp" sha256)" != "$(extract_body "$envelope_tmp" | sha256 | awk '{print $1}')" ] ||
       ! extract_body "$envelope_tmp" | cmp -s - "$tmp"; then
        die "INTEGRITY FAILURE: envelope body or sha256 differs from input — dispatch NOT queued"
    fi
    # Test-only: simulate interruption after verification, immediately before rename.
    [ "${DISPATCH_TEST_ABORT_AT:-}" != publish ] || die "test abort before envelope publish"
    mv "$envelope_tmp" "$out" || die "cannot publish envelope: $out"
    ENVELOPE_TMP=""

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
    local f status claim
    while IFS= read -r f; do
        status="$(fm_get "$f" status)"
        claim="${f%.md}.claim"
        case "$f" in
            */.dispatch/inbox/*)
                if [ -f "$claim" ]; then
                    read_claim "$claim"
                    if claim_live; then status="claimed($CLAIM_BY, $CLAIM_UNTIL)"
                    else status="claim-expired"; fi
                fi ;;
        esac
        printf '%-46s %-8s %-45s %s\n' \
            "$(fm_get "$f" id)" \
            "$status" \
            "$(fm_get "$f" from-lane) -> $(fm_get "$f" to-lane)" \
            "$(fm_get "$f" title)"
    done <<< "$files"
}

# ── show ───────────────────────────────────────────────────────────────────

cmd_show() {
    [ $# -eq 1 ] || die "usage: dispatch.sh show <id>"
    local f; f="$(find_dispatch_file "$1")" || return 1
    cat "$f"
    echo "──────────────────────────────────────────────────────────────────"
    echo "file: $f"
    local stored actual bytes
    stored="$(fm_get "$f" sha256)"
    actual="$(extract_body "$f" | sha256 | awk '{print $1}')"
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

# ── claim / release ────────────────────────────────────────────────────────

cmd_claim() {
    [ $# -ge 1 ] || die "usage: dispatch.sh claim <id> [--by <name>] [--lease <hours>]"
    local id="$1" by lease=24; shift
    by="$(default_holder)"
    while [ $# -gt 0 ]; do
        case "$1" in
            --by) [ $# -ge 2 ] || die "--by needs a name"; by="$2"; shift 2 ;;
            --lease) [ $# -ge 2 ] || die "--lease needs hours"; lease="$2"; shift 2 ;;
            *) die "unknown argument for claim: $1" ;;
        esac
    done
    validate_holder "$by"
    [[ "$lease" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "--lease must be positive hours"
    local f claim archive suffix=1 action="claimed" renew=0
    f="$(find_dispatch_file "$id")" || return 1
    require_inbox "$f"
    lock_dispatch "$f"
    require_inbox "$f"
    # Measure the lease after checkout, not before waiting for another writer.
    local now until_epoch until
    now="$(date +%s)"
    until_epoch="$(awk -v now="$now" -v hours="$lease" 'BEGIN {
        seconds = hours * 3600
        if (seconds <= 0 || seconds > 253402300799 - now) exit 1
        whole = int(seconds); if (whole < seconds) whole++
        printf "%.0f\n", now + whole
    }')" || die "--lease must be positive and end before year 10000"
    until="$(iso_epoch "$until_epoch")" || die "cannot format lease expiry"
    claim="${f%.md}.claim"
    if [ -e "$claim" ]; then
        read_claim "$claim"
        if claim_live; then
            [ "$CLAIM_BY" = "$by" ] || claim_conflict
            renew=1; action="renewed"
        else
            archive="$claim.expired-$now"
            while [ -e "$archive" ]; do
                suffix=$((suffix + 1)); archive="$claim.expired-$now-$suffix"
            done
            mv "$claim" "$archive" || die "cannot archive expired claim"
            action="takeover"
        fi
    fi
    TMP_FILE="$(mktemp "$claim.tmp.XXXXXX")" || die "cannot create claim temporary file"
    {
        printf '%s\n' '---' "by: $by" "claimed_at: $(iso_now)" \
            "lease_until: $until" "lease_until_epoch: $until_epoch" '---'
    } > "$TMP_FILE" || die "cannot write claim"
    if [ "$renew" -eq 1 ]; then
        mv "$TMP_FILE" "$claim" || die "cannot renew claim"
    else
        ( set -C; cat "$TMP_FILE" > "$claim" ) || die "cannot create claim"
    fi
    echo "$action: $id by $by until $until"
}

cmd_release() {
    [ $# -ge 1 ] || die "usage: dispatch.sh release <id> [--by <name>] [--force]"
    local id="$1" by force=0 f claim; shift
    by="$(default_holder)"
    while [ $# -gt 0 ]; do
        case "$1" in
            --by) [ $# -ge 2 ] || die "--by needs a name"; by="$2"; shift 2 ;;
            --force) force=1; shift ;;
            *) die "unknown argument for release: $1" ;;
        esac
    done
    validate_holder "$by"
    f="$(find_dispatch_file "$id")" || return 1
    require_inbox "$f"
    lock_dispatch "$f"
    require_inbox "$f"
    claim="${f%.md}.claim"
    if [ ! -e "$claim" ]; then echo "not claimed: $id"; return 0; fi
    read_claim "$claim"
    [ "$force" -eq 1 ] || [ "$CLAIM_BY" = "$by" ] || claim_conflict
    rm "$claim" || die "cannot remove claim"
    echo "released: $id"
}

# ── ack ────────────────────────────────────────────────────────────────────

check_ack_claim() {
    local claim="$1" by="$2" force="$3"
    CLAIM_BY="" CLAIM_AT="" CLAIM_UNTIL="" CLAIM_EPOCH=""
    if [ -f "$claim" ]; then
        read_claim "$claim"
        if claim_live && [ "$CLAIM_BY" != "$by" ] && [ "$force" -ne 1 ]; then
            claim_conflict
        fi
    fi
}

# The done file commits the ack. Recovery never restamps or replaces it.
# This also works after SIGKILL leaves the old transaction's mkdir lock behind.
finish_ack() {
    local f="$1" dest="$2" by="$3" force="$4"
    [ "$(fm_get "$dest" status)" = done ] &&
        [ "$(fm_get "$dest" id)" = "$(fm_get "$f" id)" ] &&
        [ "$(fm_get "$dest" sha256)" = "$(fm_get "$f" sha256)" ] &&
        cmp -s <(extract_body "$dest") <(extract_body "$f") ||
        die "done record conflicts with inbox; both preserved: $dest"
    check_ack_claim "${f%.md}.claim" "$by" "$force"
    rm -f "${f%.md}.claim" && rm -f "$f" || die "ack committed; cleanup failed (rerun ack)"
    # Terminal records cannot be claimed or restamped, so removing this lock is safe.
    rmdir "${f%.md}.lock" 2>/dev/null || :
    echo "acked: ${f##*/} (cleanup complete)"
    echo "  record kept at: $dest"
}

cmd_ack() {
    [ $# -ge 1 ] || die "usage: dispatch.sh ack <id> [--by <name>] [--force] [--actual h,s,outcome] [note]"
    local id="$1"; shift
    local actual="" a_hours="" a_sessions="" a_outcome="" note="" by force=0
    by="$(default_holder)"
    while [ $# -gt 0 ]; do
        case "$1" in
            --by) [ $# -ge 2 ] || die "--by needs a name"; by="$2"; shift 2 ;;
            --force) force=1; shift ;;
            --actual) [ $# -ge 2 ] || die "--actual needs <hours>,<sessions>,<outcome>"; actual="$2"; shift 2 ;;
            --) shift; note="${*:-}"; break ;;
            *) note="${note:+$note }$1"; shift ;;
        esac
    done
    validate_holder "$by"
    if [ -n "$actual" ]; then
        IFS=',' read -r a_hours a_sessions a_outcome <<< "$actual"
        [[ "$a_hours"    =~ ^[0-9]+([.][0-9]+)?$ ]]     || die "--actual hours must be numeric (got '$a_hours')"
        [[ "$a_sessions" =~ ^[0-9]+$ ]]                 || die "--actual sessions must be an integer (got '$a_sessions')"
        [[ "$a_outcome"  =~ ^(success|partial|fail)$ ]] || die "--actual outcome must be success|partial|fail (got '$a_outcome')"
    fi
    local f; f="$(find_dispatch_file "$id")" || return 1
    case "$f" in
        */.dispatch/done/*) echo "already acked: $f"; return 0 ;;
        */.dispatch/inbox/*) : ;;
        *) die "unexpected dispatch location: $f" ;;
    esac
    local dest_dir dest tmp claim
    dest_dir="$(dirname "$(dirname "$f")")/done"
    dest="$dest_dir/$id.md"
    # Do this before locking so an interrupted, committed ack can recover.
    if [ -f "$dest" ]; then finish_ack "$f" "$dest" "$by" "$force"; return; fi
    lock_dispatch "$f"
    if [ -f "$dest" ]; then
        if [ -f "$f" ]; then finish_ack "$f" "$dest" "$by" "$force"
        else echo "already acked: $dest"; fi
        return
    fi
    require_inbox "$f"
    claim="${f%.md}.claim"
    check_ack_claim "$claim" "$by" "$force"
    if [ -z "$actual" ] && [ -n "$(fm_get "$f" predicted-hours)" ]; then
        echo "note: dispatch has predictions but no --actual given — calibration row will be incomplete" >&2
    fi
    mkdir -p "$dest_dir" || die "cannot create done directory"
    tmp="$(mktemp "$dest_dir/.ack.XXXXXX")" || die "cannot create ack temporary file"
    TMP_FILE="$tmp"
    ACK_CLAIM_BY="$CLAIM_BY" ACK_CLAIM_AT="$CLAIM_AT" \
    ACK_CLAIM_UNTIL="$CLAIM_UNTIL" ACK_CLAIM_EPOCH="$CLAIM_EPOCH" \
    awk -v acked="$(iso_now)" -v note="$note" \
        -v ah="$a_hours" -v as="$a_sessions" -v ao="$a_outcome" '
        fm < 2 && /^status: / { print "status: done"
                                print "acked: " acked
                                if (note != "") print "ack-note: " note
                                if (ENVIRON["ACK_CLAIM_BY"] != "") {
                                    print "claimed-by: " ENVIRON["ACK_CLAIM_BY"]
                                    print "claimed-at: " ENVIRON["ACK_CLAIM_AT"]
                                    print "claim-lease-until: " ENVIRON["ACK_CLAIM_UNTIL"]
                                    print "claim-lease-until-epoch: " ENVIRON["ACK_CLAIM_EPOCH"]
                                }
                                if (ah != "") { print "actual-hours: " ah
                                                print "actual-sessions: " as
                                                print "outcome: " ao }
                                next }
        /^---$/ { fm++ }
        { print }
    ' "$f" > "$tmp" || die "cannot stamp ack"
    if ! extract_body "$tmp" | cmp -s - <(extract_body "$f"); then
        die "INTEGRITY FAILURE: ack would alter the body — aborted, file unchanged"
    fi
    mv "$tmp" "$dest" || die "cannot publish done record"
    rm -f "$claim" && rm -f "$f" || die "ack committed; cleanup failed (rerun ack)"
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
    claim) cmd_claim "$@" ;;
    release) cmd_release "$@" ;;
    ack)   cmd_ack   "$@" ;;
    stats) cmd_stats "$@" ;;
    -h|--help|help|"") usage ;;
    *) usage >&2; die "unknown command: $cmd" ;;
esac
