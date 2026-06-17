// pid_csr_axi4_wrap.v
//
// Thin AXI4 (full, 64-bit data, 38-bit address, 9-bit ID) front-end around
// the AXI4-Lite (32-bit) `pid_csr_block`. Lets the hand-written CSR slave
// attach directly to a CoreAXI4Interconnect 2.9.100 slave master-port — in
// this design, FIC0_INITIATOR slave slot SLAVE3 at base 0x60040000 inside the
// FIC_0_PERIPHERALS subsystem.
//
// WHY A WRAP, NOT A REWRITE:
//   `pid_csr_block` is testbench-validated as-is (D.1/D.2/D.3). The crossbar
//   presents a full AXI4 interface (AWID/AWLEN/WLAST/burst/9-bit ID, 64-bit
//   data); the MSS only ever issues single-beat register accesses. This wrap
//   does the minimal, single-beat-only adaptation:
//     - address:  pass S_AXI_AWADDR/ARADDR[13:0] (the 16 KiB-aligned slot is
//                 16 KiB-aligned so [13:0] is the in-slot offset).
//     - data:     steer the 32-bit lane by address bit [2] (AXI4-Lite on a
//                 64-bit bus). Reads duplicate the 32-bit word into both lanes
//                 so the master picks the correct half regardless.
//     - ID:       capture AWID->BID and ARID->RID (single outstanding).
//     - LAST:     RLAST asserted with RVALID (single beat).
//     - LEN/SIZE/BURST/LOCK/CACHE/QOS/REGION/USER: ignored (single-beat).
//
// SAFETY (no bus hang / no U54 wedge):
//   Every handshake is a straight pass-through of `pid_csr_block`'s
//   always-completing AXI4-Lite FSM. This wrap adds NO new ready/valid gating,
//   so it cannot introduce a non-completing transaction. The worst failure
//   mode of a lane-steering bug is wrong DATA on an unusual access, never a
//   hung response — the opposite of the severed-read-path eavesdropper.
//
// DATAPATH PASSTHROUGH:
//   error_shadow_out / u_ai_shadow_out are surfaced for the parent to drive
//   nv_pid_top.error / .u_AI_in. tap_post_clamp_out / tap_watchdog_timeout are
//   driven from the parent (real nv_pid_top actuator output + fabric watchdog).
//   The remaining pid_csr_block status taps have no exposed source on the
//   current nv_pid_top and are tied to 0 here — DISCLOSED, not hidden.

module pid_csr_axi4_wrap #(
    parameter [31:0] CSR_VERSION = 32'h00010000
) (
    input  wire        s_axi_aclk,
    input  wire        s_axi_aresetn,

    // ---- Full AXI4 slave (matches FIC0_INITIATOR SLAVE3 master port) ----
    // Write address
    input  wire [8:0]  s_axi_awid,
    input  wire [37:0] s_axi_awaddr,
    input  wire [7:0]  s_axi_awlen,
    input  wire [2:0]  s_axi_awsize,
    input  wire [1:0]  s_axi_awburst,
    input  wire [1:0]  s_axi_awlock,
    input  wire [3:0]  s_axi_awcache,
    input  wire [2:0]  s_axi_awprot,
    input  wire [3:0]  s_axi_awqos,
    input  wire [3:0]  s_axi_awregion,
    input  wire [0:0]  s_axi_awuser,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    // Write data
    input  wire [63:0] s_axi_wdata,
    input  wire [7:0]  s_axi_wstrb,
    input  wire        s_axi_wlast,
    input  wire [0:0]  s_axi_wuser,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    // Write response
    output wire [8:0]  s_axi_bid,
    output wire [1:0]  s_axi_bresp,
    output wire [0:0]  s_axi_buser,
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    // Read address
    input  wire [8:0]  s_axi_arid,
    input  wire [37:0] s_axi_araddr,
    input  wire [7:0]  s_axi_arlen,
    input  wire [2:0]  s_axi_arsize,
    input  wire [1:0]  s_axi_arburst,
    input  wire [1:0]  s_axi_arlock,
    input  wire [3:0]  s_axi_arcache,
    input  wire [2:0]  s_axi_arprot,
    input  wire [3:0]  s_axi_arqos,
    input  wire [3:0]  s_axi_arregion,
    input  wire [0:0]  s_axi_aruser,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    // Read data
    output wire [8:0]  s_axi_rid,
    output wire [63:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rlast,
    output wire [0:0]  s_axi_ruser,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,

    // ---- Datapath surface to the parent (FIC_0_PERIPHERALS) ----
    output wire [63:0] error_shadow_out,   // -> nv_pid_top.error
    output wire [31:0] u_ai_shadow_out,    // -> nv_pid_top.u_AI_in
    input  wire [31:0] tap_post_clamp_in,  // <- nv_pid_top.actuator_out_write_data
    input  wire        tap_watchdog_in     // <- watchdog_timer.timeout
);

    // --- Lite-side wires to the inner pid_csr_block ---------------------
    wire        l_awready, l_wready, l_bvalid, l_arready, l_rvalid;
    wire [1:0]  l_bresp, l_rresp;
    wire [31:0] l_rdata;
    wire [31:0] l_wdata;
    wire [3:0]  l_wstrb;

    // --- Single-outstanding ID + lane-select capture -------------------
    reg [8:0] awid_q;
    reg       awlane_q;   // captured AWADDR[2] for write-data steering
    reg [8:0] arid_q;
    reg       arlane_q;   // captured ARADDR[2] for read-data placement

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            awid_q   <= 9'h0;
            awlane_q <= 1'b0;
            arid_q   <= 9'h0;
            arlane_q <= 1'b0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin
                awid_q   <= s_axi_awid;
                awlane_q <= s_axi_awaddr[2];
            end
            if (s_axi_arvalid && s_axi_arready) begin
                arid_q   <= s_axi_arid;
                arlane_q <= s_axi_araddr[2];
            end
        end
    end

    // --- Write-data lane steering (32-bit Lite on a 64-bit AXI4 bus) ----
    // Use the latched AWADDR[2]; the inner FSM accepts AW before W.
    assign l_wdata = awlane_q ? s_axi_wdata[63:32] : s_axi_wdata[31:0];
    assign l_wstrb = awlane_q ? s_axi_wstrb[7:4]   : s_axi_wstrb[3:0];

    // --- AXI4 -> Lite handshake pass-through ---------------------------
    assign s_axi_awready = l_awready;
    assign s_axi_wready  = l_wready;
    assign s_axi_bvalid  = l_bvalid;
    assign s_axi_bresp   = l_bresp;
    assign s_axi_bid     = awid_q;
    assign s_axi_buser   = 1'b0;

    assign s_axi_arready  = l_arready;
    assign s_axi_rvalid   = l_rvalid;
    assign s_axi_rresp    = l_rresp;
    assign s_axi_rid      = arid_q;
    assign s_axi_rlast    = l_rvalid;     // single beat
    assign s_axi_ruser    = 1'b0;
    // Duplicate the 32-bit word into both 64-bit lanes; master selects by addr.
    assign s_axi_rdata    = {l_rdata, l_rdata};

    // --- Inner AXI4-Lite CSR block (unchanged, validated D.1/D.2/D.3) ---
    pid_csr_block #(
        .CSR_VERSION (CSR_VERSION)
    ) u_pid_csr_block (
        .S_AXI_ACLK    (s_axi_aclk),
        .S_AXI_ARESETN (s_axi_aresetn),

        .S_AXI_AWADDR  (s_axi_awaddr[13:0]),
        .S_AXI_AWPROT  (s_axi_awprot),
        .S_AXI_AWVALID (s_axi_awvalid),
        .S_AXI_AWREADY (l_awready),

        .S_AXI_WDATA   (l_wdata),
        .S_AXI_WSTRB   (l_wstrb),
        .S_AXI_WVALID  (s_axi_wvalid),
        .S_AXI_WREADY  (l_wready),

        .S_AXI_BRESP   (l_bresp),
        .S_AXI_BVALID  (l_bvalid),
        .S_AXI_BREADY  (s_axi_bready),

        .S_AXI_ARADDR  (s_axi_araddr[13:0]),
        .S_AXI_ARPROT  (s_axi_arprot),
        .S_AXI_ARVALID (s_axi_arvalid),
        .S_AXI_ARREADY (l_arready),

        .S_AXI_RDATA   (l_rdata),
        .S_AXI_RRESP   (l_rresp),
        .S_AXI_RVALID  (l_rvalid),
        .S_AXI_RREADY  (s_axi_rready),

        // Shadow outputs: error/u_ai drive the real PID datapath.
        .kp_shadow_out                   (),
        .ki_shadow_out                   (),
        .kd_shadow_out                   (),
        .out_min_shadow_out              (),
        .out_max_shadow_out              (),
        .inner_clamp_setpoint_shadow_out (),
        .error_shadow_out                (error_shadow_out),
        .u_ai_shadow_out                 (u_ai_shadow_out),

        // Status taps: only the two with a real source on the current
        // nv_pid_top are live; the rest are tied off (disclosed).
        .tap_pre_clamp_out      (32'h0),
        .tap_post_clamp_out     (tap_post_clamp_in),
        .tap_integrator         (32'h0),
        .tap_derivative         (32'h0),
        .tap_saturation_flag    (1'b0),
        .tap_watchdog_timeout   (tap_watchdog_in),
        .tap_cooldown_remaining (16'h0),
        .tap_ai_active          (1'b0)
    );

endmodule
