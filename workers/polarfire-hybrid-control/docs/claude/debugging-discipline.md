# Debugging Discipline

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

When chasing a bug, build failure, or toolchain stall, follow these rules. They exist because previous sessions burned hours by skipping them.

1. **Evidence inventory before hypothesis.** Before forming a theory, list every artifact (log file, error message, file mtime, prior commit, prior session log) that has data about the problem and read each in full. Cross-reference between them. *Especially*: if a failure is byte-deterministic or output-truncated, find the matching successful run of the same operation and identify exactly what's at the divergence boundary.

2. **Cheap diagnostics before surgical fixes.** GUI tests, log reads, hash compares, byte diffs, file mtime surveys. Recovery operations (edit prjx, rename dirs, restore backups) only after these are exhausted. Hard rule.

3. **Time-box "no new evidence" stretches.** 30 min of fix attempts without learning anything new = step back, re-read evidence, change category of approach. Not "try a slightly different fix."

4. **Forensics before the first failed run.** WerFault local dumps, ProcMon traces, verbose Tcl/synth flags, captured stderr — these are 5 min of setup per session and pay back across every subsequent run. Set them up before any toolchain operation that has shown silent failures.

5. **Backups demand immediate diffs.** A `.bak` file you make and then ignore is overhead, not insurance. Hash and diff it against current state in the same minute you create it.

6. **Conclusion gate.** Before declaring a root cause in a commit message or a notes file, write the evidence→cause chain explicitly. If you can't articulate it, you don't have it. A claimed root cause must explain *all* the symptoms, including why the system worked previously.

7. **Surface silent / byte-deterministic failures to the user early.** That class of bug is rarely solvable from a CLI shell. Ask for hands-on access (GUI, fresh terminal, second machine) within 30 min of identifying the pattern, not after hours of pushing.

8. **For Tcl / batch-mode tools: explicit `flush stdout` before every potentially-blocking call**, and capture stderr to a separate file. Batch-mode buffering quirks burn diagnostic time silently.

9. **Get a second opinion when stuck.** Use the `second-opinion` skill to produce an assumption-free Codex briefing when 30+ min have passed without new evidence, when multiple hypotheses have been tested unsuccessfully, or before committing to a heavy fix path. Fresh eyes catch what momentum-anchored eyes miss.
