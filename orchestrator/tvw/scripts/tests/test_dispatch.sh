#!/usr/bin/env bash
# Self-contained acceptance tests. Every queue mutation stays under mktemp.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$SCRIPT_DIR/dispatch.sh"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/test-dispatch.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
export DISPATCH_ROOT="$TEST_DIR/lanes with spaces"
mkdir -p "$DISPATCH_ROOT/alpha/subdir" "$DISPATCH_ROOT/beta" "$TEST_DIR/bin"
BODY="$TEST_DIR/body.txt"
printf 'First line.\n\nLiteral $HOME and \\ escapes.\n---\nLast line.\n' > "$BODY"
PASSES=0

dispatch() { "$BASH" "$SCRIPT" "$@"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { PASSES=$((PASSES + 1)); echo "PASS: $*"; }
contains() { grep -qF -- "$2" "$1" || fail "missing '$2' in $1"; }
absent() { [ ! -e "$1" ] || fail "unexpected path: $1"; }
status() {
    local want="$1" got; shift
    if dispatch "$@" > "$TEST_DIR/output" 2>&1; then got=0; else got=$?; fi
    [ "$got" -eq "$want" ] || { cat "$TEST_DIR/output"; fail "exit $got, wanted $want: $*"; }
}
send() {
    dispatch send alpha "$1" --file "$BODY" --from beta --predict 1,1,0.8 > "$TEST_DIR/send"
    ID="$(sed -n 's/^queued: //p' "$TEST_DIR/send")"
    [ -n "$ID" ] || fail 'send returned no id'
    INBOX="$DISPATCH_ROOT/alpha/.dispatch/inbox/$ID.md"
    CLAIM="${INBOX%.md}.claim"
    DONE="$DISPATCH_ROOT/alpha/.dispatch/done/$ID.md"
}
expire() {
    awk '/^lease_until: / { print "lease_until: 2000-01-01T00:00:00Z"; next }
         /^lease_until_epoch: / { print "lease_until_epoch: 946684800"; next }
         { print }' "$CLAIM" > "$TEST_DIR/expired"
    mv "$TEST_DIR/expired" "$CLAIM"
}

# Freeze just the ID minute so the race remains deterministic across minute rollover.
export DISPATCH_TEST_DATE="$(command -v date)"
cat > "$TEST_DIR/bin/date" <<'EOF'
#!/usr/bin/env bash
if [ "$#" -eq 1 ] && [ "$1" = '+%Y-%m-%d-%H%M' ]; then
    echo 2026-09-27-1200
else
    exec "$DISPATCH_TEST_DATE" "$@"
fi
EOF
chmod +x "$TEST_DIR/bin/date"
export PATH="$TEST_DIR/bin:$PATH"

pids=()
for n in 1 2 3 4 5 6 7 8; do
    dispatch send alpha 'Concurrent title' --file "$BODY" --predict 1,1,0.8 > "$TEST_DIR/send-$n" 2>&1 &
    pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || fail 'concurrent send'; done
set -- "$DISPATCH_ROOT/alpha/.dispatch/inbox/"*.md
[ "$#" -eq 8 ] || fail "expected 8 envelopes, got $#"
for f in "$@"; do
    id="${f##*/}"; status 0 show "${id%.md}"; contains "$TEST_DIR/output" 'sha256 verified'
done
for suffix in '' -2 -3 -4 -5 -6 -7 -8; do
    [ -f "$DISPATCH_ROOT/alpha/.dispatch/inbox/2026-09-27-1200-concurrent-title$suffix.md" ] || fail "missing suffix $suffix"
done
pass '8 concurrent same-title sends produce distinct, intact envelopes'

# Global ID namespace also covers other lanes and historical, unreserved files.
dispatch send beta 'Concurrent title' --file "$BODY" > "$TEST_DIR/send" 2>&1
contains "$TEST_DIR/send" 'queued: 2026-09-27-1200-concurrent-title-9'
send 'Historical collision'
dispatch ack "$ID" > /dev/null
rmdir "$DISPATCH_ROOT/.dispatch-ids/$ID"
send 'Historical collision'
case "$ID" in *-2) : ;; *) fail 'historical done collision';; esac
pass 'global IDs avoid other lanes and historical done records'

send 'Claims'
status 0 claim "$ID" --by alice
contains "$CLAIM" 'by: alice'
contains "$CLAIM" 'lease_until_epoch: '
cp "$CLAIM" "$TEST_DIR/original-claim"
status 3 claim "$ID" --by bob
contains "$TEST_DIR/output" 'alice until '
cmp -s "$CLAIM" "$TEST_DIR/original-claim" || fail 'refusal changed claim'
pass 'second claimer refused with holder and expiry, exit 3'

old_epoch="$(sed -n 's/^lease_until_epoch: //p' "$CLAIM")"
status 0 claim "$ID" --by alice --lease 48
new_epoch="$(sed -n 's/^lease_until_epoch: //p' "$CLAIM")"
[ "$new_epoch" -gt "$old_epoch" ] || fail 'renewal did not extend lease'
contains "$TEST_DIR/output" 'renewed:'
pass 'same holder renews lease'

status 0 list --lane alpha
contains "$TEST_DIR/output" 'claimed(alice, '
status 0 show "$ID"
contains "$TEST_DIR/output" 'sha256 verified'
status 1 show "$ID.claim"
pass 'list shows live claim; show verifies SHA and ignores sidecars'

expire
cp "$CLAIM" "$TEST_DIR/expired-claim"
status 0 list --lane alpha
contains "$TEST_DIR/output" 'claim-expired'
status 0 claim "$ID" --by bob
contains "$TEST_DIR/output" 'takeover:'
set -- "$CLAIM".expired-*
[ "$#" -eq 1 ] && cmp -s "$1" "$TEST_DIR/expired-claim" || fail 'expired claim not archived'
contains "$CLAIM" 'by: bob'
pass 'expired lease takeover preserves old claim and reports takeover'

status 3 release "$ID" --by alice
[ -f "$CLAIM" ] || fail 'non-holder released claim'
status 0 release "$ID" --by alice --force
absent "$CLAIM"
status 0 claim "$ID" --by alice
status 0 release "$ID" --by alice
absent "$CLAIM"
pass 'release rejects non-holder; force and holder release work'

status 0 claim "$ID" --by bob
cp "$CLAIM" "$TEST_DIR/ack-claim"
status 3 ack "$ID" --by alice
[ -f "$INBOX" ] || fail 'refused ack removed inbox'
absent "$DONE"
status 0 ack "$ID" --by alice --force --actual 2,1,success 'Completed work'
absent "$INBOX"; absent "$CLAIM"
contains "$DONE" 'claimed-by: bob'
contains "$DONE" "claimed-at: $(sed -n 's/^claimed_at: //p' "$TEST_DIR/ack-claim")"
contains "$DONE" "claim-lease-until: $(sed -n 's/^lease_until: //p' "$TEST_DIR/ack-claim")"
contains "$DONE" "claim-lease-until-epoch: $(sed -n 's/^lease_until_epoch: //p' "$TEST_DIR/ack-claim")"
contains "$DONE" 'actual-hours: 2'
contains "$DONE" 'ack-note: Completed work'
status 0 show "$ID"; contains "$TEST_DIR/output" 'sha256 verified'
pass 'ack rejects non-holder; forced ack stamps all claim fields and preserves SHA'

send 'Unclaimed'
status 0 ack "$ID" 'Original note'
contains "$DONE" 'ack-note: Original note'
if grep -q '^claimed-by:' "$DONE"; then fail 'unclaimed ack invented claim'; fi
cp "$DONE" "$TEST_DIR/done-before"
status 0 ack "$ID" 'Should not replace note'
cmp -s "$DONE" "$TEST_DIR/done-before" || fail 'second ack rewrote done record'
pass 'unclaimed ack and repeated ack preserve existing behavior'

send 'Interrupted ack'
status 0 claim "$ID" --by alice
cp "$INBOX" "$TEST_DIR/inbox-before"
cp "$CLAIM" "$TEST_DIR/claim-before"
status 0 ack "$ID" --by alice 'Original receipt'
cp "$DONE" "$TEST_DIR/done-before"
cp "$TEST_DIR/inbox-before" "$INBOX"
cp "$TEST_DIR/claim-before" "$CLAIM"
mkdir "${INBOX%.md}.lock"
status 3 ack "$ID" --by bob
status 0 ack "$ID" --by alice 'Do not replace receipt'
absent "$INBOX"; absent "$CLAIM"; absent "${INBOX%.md}.lock"
cmp -s "$DONE" "$TEST_DIR/done-before" || fail 'recovery rewrote done record'
pass 'interrupted ack recovers inbox, claim, and stale lock without restamping'

send 'Killed ack'
status 0 claim "$ID" --by alice
export DISPATCH_TEST_MV="$(command -v mv)"
export DISPATCH_TEST_KILL_DEST="$DONE"
cat > "$TEST_DIR/bin/mv" <<'EOF'
#!/usr/bin/env bash
"$DISPATCH_TEST_MV" "$@" || exit "$?"
if [ "$#" -eq 2 ] && [ "$2" = "$DISPATCH_TEST_KILL_DEST" ]; then
    kill -KILL "$PPID"
fi
EOF
chmod +x "$TEST_DIR/bin/mv"
status 137 ack "$ID" --by alice 'Receipt before SIGKILL'
rm "$TEST_DIR/bin/mv"
[ -f "$INBOX" ] && [ -f "$CLAIM" ] && [ -f "$DONE" ] && [ -d "${INBOX%.md}.lock" ] || fail 'kill missed commit window'
cp "$DONE" "$TEST_DIR/killed-done"
status 0 ack "$ID" --by alice 'Replacement receipt'
absent "$INBOX"; absent "$CLAIM"; absent "${INBOX%.md}.lock"
cmp -s "$DONE" "$TEST_DIR/killed-done" || fail 'SIGKILL recovery changed receipt'
pass 'actual SIGKILL after done publication recovers without replacing receipt'

send 'Expired ack'
status 0 claim "$ID" --by alice
expire
status 3 release "$ID" --by bob
status 0 ack "$ID" --by bob
contains "$DONE" 'claimed-by: alice'
absent "$CLAIM"
pass 'expired claim still restricts release but permits another holder to ack'

send 'Conflicting recovery'
cp "$INBOX" "$DONE"
status 1 ack "$ID"
[ -f "$INBOX" ] && [ -f "$DONE" ] || fail 'conflicting recovery deleted evidence'
contains "$TEST_DIR/output" 'done record conflicts'
pass 'recovery refuses conflicting done records'

send 'Default holder'
(cd "$DISPATCH_ROOT/alpha/subdir"; dispatch claim "$ID") > "$TEST_DIR/output"
contains "$CLAIM" 'by: alpha'
(cd "$DISPATCH_ROOT/alpha"; dispatch release "$ID") > /dev/null
(cd "$TEST_DIR"; dispatch claim "$ID") > /dev/null
contains "$CLAIM" "by: ${USER:-$(id -un)}@$(hostname -s)"
pass 'default holder uses enclosing lane or USER@hostname'

send 'Tiny lease'
status 0 claim "$ID" --by alice --lease 0.0001
contains "$CLAIM" 'lease_until: '
status 1 claim "$ID" --by alice --lease -1
status 1 claim "$ID" --by alice --lease 0
pass 'fractional leases work; nonpositive leases fail'

send 'Concurrent claim'
pids=()
for n in 1 2 3 4 5 6 7 8; do
    (
        if dispatch claim "$ID" --by "worker-$n" > "$TEST_DIR/claim-$n" 2>&1; then rc=0; else rc=$?; fi
        echo "$rc" > "$TEST_DIR/claim-status-$n"
    ) &
    pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
winners=0
for n in 1 2 3 4 5 6 7 8; do
    case "$(cat "$TEST_DIR/claim-status-$n")" in
        0) winners=$((winners + 1)) ;;
        3) contains "$TEST_DIR/claim-$n" 'claimed by worker-' ;;
        *) cat "$TEST_DIR/claim-$n"; fail 'unexpected concurrent claim result' ;;
    esac
done
[ "$winners" -eq 1 ] || fail "expected one claim winner, got $winners"
pass '8 concurrent claimers produce exactly one holder'

send 'Corrupt body'
printf 'Tampered.\n' >> "$INBOX"
status 1 show "$ID"
contains "$TEST_DIR/output" 'integrity: MISMATCH'
pass 'show still detects body tampering'

(unset DISPATCH_ROOT; export DISPATCH_LANES_ROOT="$TEST_DIR/legacy"; mkdir -p "$DISPATCH_LANES_ROOT/alpha";
 dispatch send alpha Legacy --file "$BODY") > "$TEST_DIR/legacy-output" 2>&1
contains "$TEST_DIR/legacy-output" "$TEST_DIR/legacy/alpha/.dispatch/inbox/"
pass 'legacy lane-root override remains supported'

echo "PASS: $PASSES acceptance groups (isolated temporary queues)"
