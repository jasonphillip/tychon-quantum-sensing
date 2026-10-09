# Dispatch: polarfire items 2 + 3 (MSS-paced loop, daytime soak) — 2026-07-02

**To:** a fresh polarfire-hybrid-control session (no prior context assumed).
**Hardware window:** the Icicle Kit is powered and available ALL DAY today. Plan for an
evening harvest, not an overnight one.

## Read first (in order)

1. `~/projects/tychon-verification-workbench/tvw/outreach/briefing-deck/NEXT_48H_PLAN.md`
   — the ranked item list, deck-update templates per item, velocity-claim rule.
2. `~/projects/tychon-sbir/docs/01_deliverables/tvw_logs/DAILY_LOG_2026-07-01.md` — esp.
   the Phase-C watchdog entry and the final "Open after tonight" bullet (it defines
   exactly what remains for items 2 and 3).
3. `~/projects/polarfire-hybrid-control/docs/watchdog_trip_measured_2026-07-01.md` — the
   evidence-pattern exemplar you are expected to match (raw log + exact commands +
   distinct-event proof + tail attribution).

State as of this morning: item 1 (watchdog trip-time) is banked — measured on silicon,
median 2.000 ms over N=120, commit `7661322`, EV-WDT-TRIP closed, deck rev applied
(TVW `a45d7d4`). Item 4 (board power) is DROPPED — PAC1934 electrically absent on all
I²C buses. **Items 2 and 3 have NOT started** (verify anyway, below). The resident 2 ms
two-slot image is the golden image under test — it must not be modified or reprogrammed
today.

## Step 0 — state discovery (do not assume)

- Repo at `7661322`, clean tree; kit reachable; resident image responds (repeat the
  V250 stimulus one-shot and confirm bit-identical `nn_out0=-2.538894653` before
  anything else, same as item 1 did).
- Confirm NO daemon/pidfile already running from a prior session (`/root/bringup/` on
  the kit; `ps` for `v250_pid_loop`). The 07-01 session ended before starting the soak,
  but verify rather than trust this dispatch.

## Item 2 — MSS-paced loop: sustained-rate number + laptop-disconnected proof

`v250_pid_loop --daemon` already IS the MSS-paced closed loop; what's missing is
evidence. Mind the `0x60040020` inner-clamp setup gotcha (documented in the repo — grep
for the address; the 07-01 log calls it out as the known setup step).

Deliver:
a. **Sustained-rate number**: loop iterations/sec sustained over a stated duration
   (≥10 min), proven by distinct-iteration counters (not wall-clock inference), with
   jitter/tail characterization in the item-1 style.
b. **Laptop-disconnected continuity**: start the daemon, disconnect the host link, let
   it run standalone (≥10 min), reconnect, and prove continuity from monotonic counters
   + on-kit telemetry (logs under `/root/bringup/`, NOT tmpfs `/tmp`).

Evidence discipline (mirror item 1): raw log + exact-command run notes in
`libero/reports/2026-07-02-mss-paced/`, write-up in `docs/`, commit with a dated
technical message + push to nas; propagate to fix-list-status.csv, INVENTORY addendum,
and today's TVW daily log; apply the plan's **item-2 deck template** via the claims_map
gate (note: the boundary box and cover subtitle STAY — the loop is MSS-paced, still not
fabric-resident; do not overclaim). Tag [HW].

## Item 3 — daytime soak (start it as soon as item 2's config is measured)

Leave item 2's exact measured daemon configuration running as the soak — the soak then
validates the same configuration the rate number describes.

- Start by late morning so ≥8 h lands before the evening harvest.
- `nohup` + pidfile + heartbeat log under `/root/bringup/` (must survive host
  disconnect and session exit).
- Write the success criteria INTO the log header up front: target duration ≥8 h,
  watchdog trip counter stable (zero unexpected trips), no stall (heartbeat cadence),
  sustained rate within a stated % of item 2's number, memory/error counters stable.
- If it fails mid-soak: capture state, stop, report — no reflashing, no debugging into
  the golden image.
- Before ending your session: report the pidfile + log paths and the ONE command an
  evening session (or you, if still alive) runs to summarize the soak into evidence.
  The plan's **item-3 deck template** is applied only at harvest, from the summarized
  stats.

## Guardrails

- Golden image untouched; no bitstream programming today (the on-silicon fabric-latency
  item needs a new rdcycle/latched-counter image from the Beelink — that is a separate
  future session, and programming would kill the soak).
- No GitHub pushes (nas is fine and expected). No email/deck SENDING — content updates
  via the claims_map gate only; the send decision is parked with Jason.
- The retracted odmr-vector Increment-1 numbers (16/16, 0.811, DR≈5 mT) remain
  banned-listed on all outward surfaces (the gate enforces this; don't hand-edit around
  it).
- Velocity-claim rule from the plan: dated commits, never "in 72 hours"-style language.

## Report back (end of your session)

Item 2: the sustained-rate number + disconnected-run proof summary, commit hashes,
which surfaces were propagated. Item 3: soak start time, criteria, pidfile/log paths,
harvest one-liner. Any deviation from this dispatch: state it explicitly rather than
silently adapting (the 07-01 sessions set the standard on this).
