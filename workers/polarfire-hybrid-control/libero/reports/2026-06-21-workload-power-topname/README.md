# 2026-06-21 SmartPower Explicit-Top Attempt

Status: ATTEMPTED, NOT CLOSURE.

The SmartPower Tcl flow was patched to import the workload VCD with an explicit top-level name:

```tcl
smartpower_import_vcd \
    -file $WORKLOAD_VCD \
    -opmode {Active} \
    -auto_detect_top_level_name {FALSE} \
    -top_level_name {nv_pid_top_top} \
    -glitch_filtering {auto}
```

The bee headless run's streamed outer log froze during project source loading. SmartPower still left a small `2026-06-21-workload-power` report directory on bee, which is copied here. The report summary matches the previous default/vectorless result exactly: Total `2622.855 mW`, Static `445.612 mW`, Dynamic `2177.243 mW`. No `verifypower.log` or `Annotated Pins` result was produced for this attempt, so no nonzero VCD annotation evidence was obtained.

Artifact:

- `smartpower_topname.log` - partial Libero run log from the stopped attempt.
- `smartpower_workload.rpt` - SmartPower summary report left by the attempt.
- `rptstyle.xsl` - stylesheet emitted with the SmartPower report.

Current SmartPower truth remains: no completed run has nonzero VCD annotation, so the power estimate is still vectorless/default activity rather than workload-driven.
