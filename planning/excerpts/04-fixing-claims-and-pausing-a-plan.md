# 04 — Critique of audit findings, fix prompts, and a repo session that pauses the plan

- Date: 2026-04-29
- Context: Jason uses the project chat to review reports from the FPGA workstation session, turn findings into prompts, and handle a session that stops to question the prompt.
- Shows: result -> review, then review -> follow-up prompt, then a repo session reply that changes the plan.

### Result -> review -> follow-up prompt: a tied-off signal found by the repo session

> **Jason:**
>
> im geting yuo that repo 3 info however that llm said this: ● ★ Insight ─────────────────────────────────────
> […]
>
> go with option a. do what any to do items you can now
>
> **Claude (project chat):**
>
> ## That's a real find — and Repo 3 LLM is right to flag it
> […]
>
> - In the current MPFS_ICICLE_KIT_BASE_DESIGN.v overlay (line 1889), the watchdog input pin `nv_pid_top.ai_watchdog_timeout` is tied to `GND_net` — i.e., a constant logic 0.
> […]
>
> **The reconciliation, honestly:** the safety claim splits into two pieces that the report currently conflates:
> 1. **The transfer mechanism is hardware-enforced** — true. RTL synthesizes, testbench verifies, no software dependency.
> 2. **The trigger source (the deadline counter monitoring VectorBlox AXI) is hardware-enforced** — *not in this build.* The trigger is currently tied off; the FPGA counter referenced in the prose either isn't instantiated in the overlay or isn't connected to the bumpless-transfer input.
>
> The clean fix: the report should say the **transfer mechanism is hardware-verified** (true, with testbench evidence) and the **deadline-counter integration is staged for the [later stage] HITL build** (honest about the current overlay state). That's a true statement that doesn't weaken the Simplex RTA argument — IFCS and Auto-GCAS precedents both went through staged integration. It just keeps the report defensible against a sharp reviewer who pulls up the overlay netlist.
> […]
>
> **Add to the Repo 3 prompt** — extension to §1 of the writeup, since they've already started it:
>
> ```
> ADDITIONAL REQUEST for §1 of the writeup (Safety Triad RTL evidence):
>
> For the Execution Watchdog specifically, document the COMPLETE signal chain
> end-to-end, not just the bumpless-transfer mechanism:
>
>   (a) The deadline-counter logic that's supposed to monitor VectorBlox AXI
> […]
> ```

### Spec -> prompt: audit gate first, then fixes

> **Jason:**
>
> lets do path 1 and also can you put in the prompt for cluade to do tis first: Adopt the CI-style synthesis audit gate immediately. Before the next P&R run on FPGA workstation (Path 1) or before any future [later stage] run, add to the Repo 3 wrapper:
>
> **Claude (project chat):**
>
> Path 1 it is. Here's the prompt — the CI gate goes in first as Task 0 so it's in place before the prune-fix run, and it will literally prevent us from declaring closure on a pruned netlist again.
>
> ````
> GOAL
> Three sequential tasks. Task 0 builds a CI-style synthesis audit gate that must pass before any future P&R run is considered closed. Task 1 fixes the CL168 prune of nv_pid_top_0 by binding actuator_out_write_* outputs to a real consumer. Task 2 wires the watchdog hardware driver using the documented Microchip path (HB0919 Output Valid). After all three land, re-run the full synth + P&R + VERIFYTIMING + VERIFYPOWER pipeline and report the real PID-in-loop numbers.
> […]
> ````

### The repo session pauses; the chat accepts its five concerns and sends a revised order

> **Jason:**
>
> so that propt was for claude in repo 3 and im not having codex do the acutal work. Here is what claude said in repsonse:
>
> **Claude (project chat):**
>
> All five concerns are legitimate and Repo 3 Claude did the right thing by stopping. The "executing-plans" pause was correct — pushing forward on a misspecified plan would have wasted the budget. Let me address each.
> […]
>
> **1. Audit gate glob — accept the fix.** The path I wrote was a guess based on the post-recovery writeup's references; Repo 3 Claude actually checked the filesystem. Their proposed fix (glob both FPGA workstation live and GPU workstation report-copy paths, plus fail on empty match) is correct.
> […]
>
> **2. Project load check first — accept and elevate to Task 0.0.** This is the most important catch. If `open_project` doesn't succeed today, none of Tasks 1, 2, or closure can run regardless of how good the plans are. The 2-min `decision-2-c-load-only.tcl` check is the right first move. I should have included it. If it crashes, we have a different problem entirely (project recovery, not integration work).
> […]
>
> ## Reply to Repo 3 Claude
>
> Send this back:
>
> ````
> Proceed with your revised order. All five concerns accepted:
> […]
>
> 3. Watchdog: hand-code the Verilog. ~12 lines, 200 MHz × 200,000 cycle counter, ai_heartbeat input rising-edge resets the counter, timeout output asserts when the counter saturates. Single always_ff block. Drop it in libero/hdl/watchdog_timer.v (or wherever the repo's hand-coded HDL lives — match existing convention). No separate SmartHLS target. Document in the commit message that the SmartHLS source at hls/src/watchdog.cpp is the design reference but the deployed module is hand-coded for SmartDesign-instantiation simplicity.
> […]
> ````

Result in the repos: the revised order was sent back to the repo session with the project-load check promoted to the first task; the chat also planned a report change to separate the verified watchdog mechanism from the unwired trigger.
