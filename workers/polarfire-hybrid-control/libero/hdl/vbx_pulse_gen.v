// vbx_pulse_gen.v
//
// 2-FF synchronizer + rising-edge detector for the CoreVectorBlox
// `output_valid` interrupt. Emits exactly one one-cycle `pulse_o` per
// rising edge of `vbx_output_valid_i`, suitable for refreshing the
// hardware watchdog via `watchdog_timer.v`.
//
// CORPUS BASIS:
//   - HB0919 v2.0 §4.1: the Output Valid bit in the CoreVectorBlox
//     control register is "Write 1 to clear" (R/WC), set when network
//     processing completes. The signal stays high until firmware clears
//     it. Citation: HB0919:361 ("3 Output Valid Write 1 to clear ... R/WC"),
//     HB0919:499 ("network processing completes, the 'Output Valid' bit
//     of the control register is set"), HB0919:784 ("output_valid
//     Interrupt Output ... Mirrors the Output Valid bit in the Control
//     Register").
//   - User-contributed analysis preserving:121-125: "output_valid is a
//     completion indication, not a raw 'the datapath toggled' pulse.
//     Because the underlying control bit remains asserted until software
//     clears it, the signal is level-like from the watchdog's point of
//     view. ... Convert it to a pulse with edge detection, and synchronize
//     it if the watchdog is in a different clock domain."
//
//   This module implements both halves: synchronization (output_valid
//   crosses CoreVectorBlox.clk -> watchdog clock) and edge detection
//   (level -> single-cycle pulse on rising edge). One pulse fires per
//   completion, regardless of how long firmware takes to clear the bit.
//   If firmware fails to clear, no further pulses are produced and the
//   watchdog will time out, which is the corpus-described safe-by-design
//   behavior for the stuck-high failure mode.

module vbx_pulse_gen (
    input  wire clk_i,
    input  wire resetn_i,
    input  wire vbx_output_valid_i,
    output wire pulse_o
);

    reg sync_meta;
    reg sync_stable;
    reg sync_prev;

    always @(posedge clk_i) begin
        if (!resetn_i) begin
            sync_meta   <= 1'b0;
            sync_stable <= 1'b0;
            sync_prev   <= 1'b0;
        end else begin
            sync_meta   <= vbx_output_valid_i;
            sync_stable <= sync_meta;
            sync_prev   <= sync_stable;
        end
    end

    assign pulse_o = sync_stable & ~sync_prev;

endmodule
