// watchdog_timer.v
//
// 200 MHz x 200,000-cycle (1 ms) AI-inference watchdog.
//
// Counter free-runs and saturates at WATCHDOG_TIMEOUT_CYCLES. Any rising
// edge on `ai_heartbeat` resets the counter and clears the timeout flag.
// Once `timeout` asserts, it stays asserted until the next heartbeat,
// which propagates to nv_pid_top.ai_watchdog_timeout to trigger bumpless
// transfer from AI+PID to pure PID mode.
//
// Design reference: hls/src/watchdog.cpp (SmartHLS C++). The deployed
// module is hand-coded for SmartDesign-instantiation simplicity (the
// SmartHLS-generated component would require a separate `shls hw` target
// because nv_pid.cpp already declares the only `#pragma HLS function top`
// in the build).
//
// Heartbeat source: CoreVectorBlox IP `output_valid` interrupt output
// (HB0919 Table 5-4). Per HB0919, output_valid mirrors Control Register
// bit 3 at offset 0x00 — sets once per inference completion, cleared by
// MSS firmware writing 1 to it before the next inference.

module watchdog_timer #(
    parameter integer WATCHDOG_TIMEOUT_CYCLES = 200_000
) (
    input  wire clk,
    input  wire resetn,         // active-low fabric reset (FIC_0 domain)
    input  wire ai_heartbeat,   // CoreVectorBlox output_valid (IP-level)
    output reg  timeout         // -> nv_pid_top.ai_watchdog_timeout
);

    // counter width derived from the timeout constant (clog2 ceiling)
    localparam integer CW = $clog2(WATCHDOG_TIMEOUT_CYCLES + 1);

    reg [CW-1:0] counter;
    reg          heartbeat_d;

    wire heartbeat_rising = ai_heartbeat & ~heartbeat_d;

    always @(posedge clk) begin
        if (!resetn) begin
            counter     <= {CW{1'b0}};
            heartbeat_d <= 1'b0;
            timeout     <= 1'b0;
        end else begin
            heartbeat_d <= ai_heartbeat;
            if (heartbeat_rising) begin
                counter <= {CW{1'b0}};
                timeout <= 1'b0;
            end else if (counter < WATCHDOG_TIMEOUT_CYCLES[CW-1:0]) begin
                counter <= counter + 1'b1;
            end else begin
                timeout <= 1'b1;
            end
        end
    end

endmodule
