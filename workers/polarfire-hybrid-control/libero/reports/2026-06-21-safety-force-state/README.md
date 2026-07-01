# Safety Force-State Probe - 2026-06-21

Remote clone:

```text
~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055
```

Result: attempted, not closure. This was a short clone-only probe after the
successful clean-handoff Synplify/map output. The script tried to use Libero's
`set_tool_state` command to mark `SYNTHESIZE` successful and then run
`PLACEROUTE`.

Libero opened the project and reported:

```text
SYNTHESIZE = Tool inputs are out of date
PLACEROUTE = Tool inputs are out of date
VERIFYTIMING = Tool inputs are out of date
GENERATEPROGRAMMINGDATA = Tool inputs are out of date
```

The command `set_tool_state -name {SYNTHESIZE} -state {StateSuccess}` failed
immediately with `Unkown state StateSuccess`. No P&R stage ran, no safety `.job`
was exported, and no programming was performed.

Key evidence:

- `libero_force_state.log`: full Libero wrapper log for the probe.
- `build_two_slot_force_state_pnr.tcl`: exact probe script.
- `final_capture.txt`: process check, script hash, state/error markers, and
  export job state.
