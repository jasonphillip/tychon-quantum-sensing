# PDC Fix Notes — decision-2-option-c overlay on Icicle baseline

## Symptom

April 28 P&R aborted across all 20 seeds with:

```
Error: [125960395]: PRPF_009: Dedicated XCVR reference clock port(s) for instance
'CLOCKS_AND_RESETS_inst_0/PCIE_REF_CLK_0/PCIE_REF_CLK_0/I_IO' must be placed and
locked before running Place and Route.
```

The April 2 baseline run on the same project had succeeded with no such error.

## Diagnosis

`MPFS_ICICLE_KIT_BASE_DESIGN.nmatinit.pdc` is a designer-scratch file emitted
*by* P&R, not an organized member of the project's active constraint set
(`MPFS_ICICLE_Vectorblox.prjx` lists `constraint/io/*.pdc` as the io_pdc set;
the nmatinit.pdc lives under `designer/` and is regenerated each pass).

On April 2 the placer ran from a clean state and chose an XCVR_REF_CLK
location implicitly (the nmatinit entry recorded `-fixed false` at
`x=2468, y=236`). On April 28 the SmartDesign top was regenerated to pick up
the new decision-2-option-c HLS overlay (`nv_pid_top` with the hardcoded outer
+ AXI inner sector clamp). That regeneration invalidated the implicit
placement carry-over from April 2's run, and the placer requires *dedicated*
XCVR_REF_CLK macros to be locked by user PDC before it will start P&R.

The instance path `CLOCKS_AND_RESETS_inst_0/PCIE_REF_CLK_0/PCIE_REF_CLK_0/I_IO`
is identical in the April 28 regenerated netlist and in the April 2 nmatinit,
so this is **not** an instance-path drift problem — it is a missing explicit
lock. ICICLE_PCIE.pdc already pins the top-level REF_CLK_PAD_P/N ports to
L19/L20 by `set_io -port_name`, but that does not satisfy the dedicated XCVR
macro's placement requirement.

## Fix

`libero/constraints/decision-2-option-c.pdc` adds:

```tcl
set_location \
    -inst_name CLOCKS_AND_RESETS_inst_0/PCIE_REF_CLK_0/PCIE_REF_CLK_0/I_IO \
    -fixed true \
    -x 2468 \
    -y 236
```

Coordinates are taken directly from the April 2 nmatinit — they correspond to
the XCVR reference clock pad pair (REF_CLK_PAD_P/N = L19/L20) on the Icicle
Kit board, which is the only valid PCIe reference clock landing for this
package and never changes for this hardware.

## Project membership

The PDC must be added to the Libero project as an **I/O PDC** (organize for
Place & Route). On Beelink this is done via:

```tcl
import_files -io_pdc {libero/constraints/decision-2-option-c.pdc}
organize_tool_files -tool {PLACEROUTE} \
    -file {libero/constraints/decision-2-option-c.pdc} \
    -input_type {constraint} \
    -module {MPFS_ICICLE_KIT_BASE_DESIGN::work}
```

(Path translated to the on-Beelink absolute path before invocation.)

## Durability

This fix is durable as long as:

1. The SmartDesign keeps `CLOCKS_AND_RESETS_inst_0` as the top-level
   subsystem instance name. (Confirmed in the April 28 regenerated
   `MPFS_ICICLE_KIT_BASE_DESIGN.v` line 1115.)
2. The PCIE_REF_CLK component is nested as
   `PCIE_REF_CLK_0/PCIE_REF_CLK_0/I_IO`. (Confirmed in
   `component/work/CLOCKS_AND_RESETS/CLOCKS_AND_RESETS.v` — the `PCIE_REF_CLK`
   IP is instantiated as `PCIE_REF_CLK_0`, and the IP itself wraps the
   `XCVR_REF_CLK` primitive as `PCIE_REF_CLK_0/I_IO`.)
3. The board hardware keeps REF_CLK_PAD on L19/L20 (Icicle Kit constant).

If item (1) or (2) ever changes (Clocks_And_Resets refactor, IP
re-instantiation), update the `-inst_name` path. The (x,y) is determined by
the package pinout for the dedicated XCVR REF CLK and is stable.

## Why not edit the nmatinit.pdc directly

The `.nmatinit.pdc` is rewritten on every P&R pass — any manual edit there
is lost on the next run. The supplementary user PDC under `constraints/`
is the canonical, source-controlled fix.

## Relation to April 2 baseline

This change does not affect the April 2 baseline reproducibility. The
April 2 baseline project state is unchanged on Beelink; the
decision-2-option-c.pdc only adds a constraint that April 2's run produced
implicitly.
