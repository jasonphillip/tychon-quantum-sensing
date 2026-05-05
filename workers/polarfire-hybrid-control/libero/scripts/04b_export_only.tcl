# 04b_export_only.tcl — Bitstream-only export from a pre-closed Libero project.
#
# Path purpose: get a programmable .job artifact onto disk WITHOUT re-running
# synthesis or place-and-route. Targets the audit-006 seed_7 project clone,
# which already holds a closed netlist (Apr-30 synth → r6_s25 P&R, +0.728 ns
# slack on the 125 MHz FIC CCC PLL OUT0 user clock at slow_lv_ht; package
# FCVG484 STD-grade Production silicon).
#
# This script:
#   1. open_project on the seed_7 prjx
#   2. run_tool GENERATEPROGRAMMINGDATA  (regenerates .pdb from cached PD/STA)
#   3. export_prog_job with -job_file_name overridden to the repo-native name
#      so the artifact handed to FlashPro reads as "polarfire_hybrid_control",
#      not the upstream reference-design name
#   4. copy + sha256 sidecar into libero/reports/<dated>/
#
# RUN ON BEELINK ONLY (the seed_7 prjx is at ~\libero_seedsweep\):
#   libero "SCRIPT:libero/scripts/04b_export_only.tcl"
#
# Wall time: ~5-10 min (no synth, no P&R).
#
# Each potentially-blocking call is followed by `flush stdout` per CLAUDE.md
# debugging discipline rule #8 (batch-mode buffering quirks).

# ──────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set REPORT_DIR  [file join $REPO_ROOT libero reports]

# Beelink-specific path to the seed_7 clone. If this script is ever run on
# a different host, override SEED7_PROJECT via -script-args or environment.
set SEED7_DIR     "~/libero_seedsweep/seed_7"
set SEED7_PROJECT "$SEED7_DIR/MPFS_ICICLE_Vectorblox.prjx"

# Dated subdir name. Override via TAG env var if a re-run needs a distinct dir.
if {[info exists env(TAG)] && [string length $env(TAG)] > 0} {
    set DATED_TAG $env(TAG)
} else {
    set DATED_TAG "[clock format [clock seconds] -format {%Y-%m-%d}]-bringup"
}
set CLOSURE_DIR [file join $REPORT_DIR $DATED_TAG]
file mkdir $CLOSURE_DIR

# Reviewer-facing artifact name — independent of the upstream prjx name.
set JOB_BASENAME "polarfire_hybrid_control"

puts "==> 04b_export_only: opening seed_7 project"
puts "    prjx       : $SEED7_PROJECT"
puts "    closure    : $CLOSURE_DIR"
puts "    job name   : ${JOB_BASENAME}.job"
flush stdout

# ──────────────────────────────────────────────────────
# Step 1 — open_project
# ──────────────────────────────────────────────────────
if {[catch {open_project -file $SEED7_PROJECT} err]} {
    puts "ERROR: open_project failed: $err"
    flush stdout
    error "open_project failed"
}
puts "==> open_project OK"
flush stdout

# ──────────────────────────────────────────────────────
# Step 2 — GENERATEPROGRAMMINGDATA
# ──────────────────────────────────────────────────────
puts "==> RUN_TOOL GENERATEPROGRAMMINGDATA"
flush stdout
if {[catch {run_tool -name {GENERATEPROGRAMMINGDATA}} err]} {
    puts "ERROR: GENERATEPROGRAMMINGDATA failed: $err"
    flush stdout
    save_project
    error "GENERATEPROGRAMMINGDATA failed"
}
puts "==> GENERATEPROGRAMMINGDATA OK"
flush stdout

# ──────────────────────────────────────────────────────
# Step 3 — export_prog_job
#
# -job_file_name controls the produced .job basename, not the location.
# -export_dir lands the .job at $CLOSURE_DIR directly (no second copy step
# needed if export_dir is honored, but keep the fallback search below).
# ──────────────────────────────────────────────────────
puts "==> export_prog_job → $CLOSURE_DIR"
flush stdout
if {[catch {
    export_prog_job \
        -job_file_name $JOB_BASENAME \
        -export_dir $CLOSURE_DIR
} err]} {
    puts "ERROR: export_prog_job failed: $err"
    flush stdout
    save_project
    error "export_prog_job failed"
}
puts "==> export_prog_job OK"
flush stdout

# ──────────────────────────────────────────────────────
# Step 4 — locate the .job, sha256 sidecar
#
# export_prog_job sometimes writes to a default project location even when
# -export_dir is provided. Search the closure dir first, then fall back to
# the prjx's designer/impl1/export tree.
# ──────────────────────────────────────────────────────
set _job_glob [glob -nocomplain [file join $CLOSURE_DIR ${JOB_BASENAME}.job]]
if {[llength $_job_glob] == 0} {
    puts "WARN: no .job at $CLOSURE_DIR/${JOB_BASENAME}.job; searching project tree"
    flush stdout
    set _job_glob [glob -nocomplain [file join $SEED7_DIR designer impl1 export "*.job"]]
    if {[llength $_job_glob] == 0} {
        # Last resort: scan whole project for any .job written today.
        set _job_glob [glob -nocomplain [file join $SEED7_DIR "**/*.job"]]
    }
    if {[llength $_job_glob] == 0} {
        puts "ERROR: no .job artifact found anywhere"
        flush stdout
        error "no_job_artifact"
    }

    # Copy fallback artifact into the closure dir under the canonical name.
    set _src [lindex $_job_glob 0]
    set _dest [file join $CLOSURE_DIR ${JOB_BASENAME}.job]
    file copy -force $_src $_dest
    puts "INFO: copied [file tail $_src] → $_dest"
    flush stdout
    set _job_glob [list $_dest]
}

foreach _job $_job_glob {
    set _basename [file tail $_job]
    set _sha_file [file join $CLOSURE_DIR "${_basename}.sha256"]
    if {![catch {exec sha256sum $_job} _sha_out]} {
        set _f [open $_sha_file w]
        puts $_f $_sha_out
        close $_f
        puts "INFO: sha256 → $_sha_file"
        puts "INFO:   $_sha_out"
    } else {
        puts "WARN: sha256sum unavailable; no checksum sidecar written"
    }
    flush stdout
}

# ──────────────────────────────────────────────────────
# Save and close
# ──────────────────────────────────────────────────────
save_project
close_project

puts ""
puts "========================================="
puts " 04b_export_only complete"
puts "   .job        : $CLOSURE_DIR/${JOB_BASENAME}.job"
puts "   .sha256     : $CLOSURE_DIR/${JOB_BASENAME}.job.sha256"
puts "   source prjx : $SEED7_PROJECT"
puts ""
puts " Next: program kit via FPExpress (demo-bringup plan Part 2)"
puts "========================================="
flush stdout
