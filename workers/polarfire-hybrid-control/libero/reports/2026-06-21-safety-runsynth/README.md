# Safety Run-Synthesis Probe - 2026-06-21

Purpose: clone-only probe to see whether `run_synthesis -target` can replace
the headless `run_tool SYNTHESIZE` path that previously generated a `.vm` but
did not return cleanly to Libero Tcl.

Remote clone:
`~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118`

Command:

```sh
ssh bee 'cd ~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/libero.exe "SCRIPT:~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118/build_two_slot_runsynth_pnr.tcl"'
```

Result:

- `run_synthesis -target .../synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm` started
  Synplify Pro ME and failed quickly.
- The synthesis log reports encrypted VectorBlox VHDL compiler failures such as
  `No identifier "width_a" in scope`, followed by `VHDL compiler failed`.
- Because synthesis failed, P&R, timing, programming-data generation, and job
  export did not run in this probe.

Conclusion: `run_synthesis -target` is not a safe handoff workaround for this
project. The normal `run_tool SYNTHESIZE` path remains the only observed path
that reaches Synplify/map success for the safety edit, but its headless handoff
still needs a reliable completion path.
