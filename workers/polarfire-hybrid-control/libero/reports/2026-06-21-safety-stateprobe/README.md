# Safety State Probe - 2026-06-21

Purpose: clone-only probe to learn whether Libero Tcl can mark `SYNTHESIZE`
successful after the clean-handoff run generated a valid `.vm` but did not
return from `run_tool SYNTHESIZE`.

Remote clone:
`~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117`

Command:

```sh
ssh bee 'cd ~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/libero.exe "SCRIPT:~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117/probe_set_tool_state_values.tcl"'
```

Result:

- Initial `SYNTHESIZE`, `PLACEROUTE`, `VERIFYTIMING`, `GENERATEPROGRAMMINGDATA`,
  and `EXPORTPROGRAMMINGJOB` states were all `Tool inputs are out of date`.
- `set_tool_state` rejected numeric states `0..6` and obvious success names
  including `Success`, `Passed`, `StateSuccess`, and `Tool inputs are up to date`.
- The only accepted candidate was the existing `Tool inputs are out of date`.

Conclusion: there is no confirmed Tcl `set_tool_state` success string from this
probe. Do not use XML state edits as evidence for a valid safety build.
