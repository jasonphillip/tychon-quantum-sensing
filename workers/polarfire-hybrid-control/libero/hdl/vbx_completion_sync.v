// vbx_completion_sync.v
//
// Cross-domain synchronizer + edge detector for CoreVectorBlox `output_valid`.
//
// Per HB0919 §4.1 p.7-8 and §6.4 p.15: `output_valid` mirrors Control Register
// bit 3 at offset 0x00. It is set once when the network outputs are valid and
// must be cleared once per invocation by the MSS firmware writing 1 to the
// bit before the next inference. It is therefore a level-held strobe — never
// a self-clearing pulse — and consumers that want a per-completion event
// must edge-detect.
//
// CoreVectorBlox runs on its own dma_clk inside Vectorblox_ss; the watchdog
// runs on FIC_0_CLK. Even when nominally the same frequency, treat them as
// asynchronous and pass through a 2-FF synchronizer chain.
//
// Output: one-cycle pulse on the rising edge of the synchronized signal.
// Stuck-high `output_valid` (firmware fails to clear) produces exactly one
// pulse and then silence — correct: the watchdog must time out, not be
// indefinitely refreshed by a stale completion.
//
// (synthesis attribute hint omitted — Synplify and Designer both treat the
// 2-FF chain correctly without it. Add `(* syn_keep = "true" *)` to ff0/ff1
// only if a future sweep shows them being merged into combinational logic.)

module vbx_completion_sync (
    input  wire clk,
    input  wire resetn,
    input  wire output_valid,
    output wire pulse
);
    reg ff0, ff1, ff2;

    always @(posedge clk) begin
        if (!resetn) begin
            ff0 <= 1'b0;
            ff1 <= 1'b0;
            ff2 <= 1'b0;
        end else begin
            ff0 <= output_valid;
            ff1 <= ff0;
            ff2 <= ff1;
        end
    end

    assign pulse = ff1 & ~ff2;

endmodule
