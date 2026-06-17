// pid_subsystem.v
//
// Self-contained clean two-slot PID subsystem. Presents ONE full-AXI4 slave port
// (matching the free FIC0_INITIATOR crossbar slot SLAVE3 @ 0x60040000, 4 KiB) and
// internally splits it into two cleanly-decoded sub-slaves via axi4_demux2:
//
//   0x60040000-0x600407ff -> nv_pid_top.axi4target  (gains Kp/Ki/Kd/out_min/out_max/inner_clamp)
//   0x60040800-0x60040fff -> pid_csr (pid_csr_axi4_wrap):
//        +0x800 axi_write_count  +0x804 csr_version(=0x00010000)
//        +0x810 error_low  +0x814 error_high  +0x818 u_ai     (host injects PID stimulus)
//        +0x820..834 gain shadows   +0x844 post_clamp (actuator readback, LIVE)
//        +0x854 watchdog_csr (bit0 timeout, LIVE) ; other taps tied 0 (disclosed)
//
// Datapath (defeats Synplify constant-folding: real drivers + real consumer):
//   pid_csr.error_shadow_out -> nv_pid_top.error
//   pid_csr.u_ai_shadow_out  -> nv_pid_top.u_AI_in
//   nv_pid_top.actuator_out_write_data -> pid_csr.tap_post_clamp_in
// Safety:
//   vbx_output_valid -> vbx_pulse_gen -> watchdog_timer -> nv_pid_top.ai_watchdog_timeout
//                                                       + pid_csr watchdog tap
//
// Replaces the seed_7 eavesdropper: every PID register is in a real, decoded
// crossbar sub-slot with an independent read path (no severed reads, no
// collisions, no U54 read-wedge).

module pid_subsystem #(
    parameter integer WATCHDOG_TIMEOUT_CYCLES = 62_500_000  // 500 ms @125 MHz (host-paced demo);
                                                            // 125_000 = 1 ms safety-spec build
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire        vbx_output_valid,

    // Full AXI4 slave (connect to FIC0_INITIATOR SLAVE3 master port)
    input  wire [8:0]  s_awid,   input wire [37:0] s_awaddr, input wire [7:0] s_awlen,
    input  wire [2:0]  s_awsize, input wire [1:0] s_awburst, input wire [1:0] s_awlock,
    input  wire [3:0]  s_awcache, input wire [2:0] s_awprot, input wire [3:0] s_awqos,
    input  wire [3:0]  s_awregion, input wire [0:0] s_awuser, input wire s_awvalid,
    output wire        s_awready,
    input  wire [63:0] s_wdata,  input wire [7:0] s_wstrb, input wire s_wlast,
    input  wire [0:0]  s_wuser,  input wire s_wvalid, output wire s_wready,
    output wire [8:0]  s_bid,    output wire [1:0] s_bresp, output wire [0:0] s_buser,
    output wire        s_bvalid, input wire s_bready,
    input  wire [8:0]  s_arid,   input wire [37:0] s_araddr, input wire [7:0] s_arlen,
    input  wire [2:0]  s_arsize, input wire [1:0] s_arburst, input wire [1:0] s_arlock,
    input  wire [3:0]  s_arcache, input wire [2:0] s_arprot, input wire [3:0] s_arqos,
    input  wire [3:0]  s_arregion, input wire [0:0] s_aruser, input wire s_arvalid,
    output wire        s_arready,
    output wire [8:0]  s_rid,    output wire [63:0] s_rdata, output wire [1:0] s_rresp,
    output wire        s_rlast,  output wire [0:0] s_ruser, output wire s_rvalid,
    input  wire        s_rready
);

    // ---- demux master-side buses (M0 -> nv_pid_top, M1 -> pid_csr) ----
    wire [8:0]  m0_awid;  wire [37:0] m0_awaddr; wire [7:0] m0_awlen; wire [2:0] m0_awsize;
    wire [1:0]  m0_awburst; wire [1:0] m0_awlock; wire [3:0] m0_awcache; wire [2:0] m0_awprot;
    wire [3:0]  m0_awqos; wire [3:0] m0_awregion; wire [0:0] m0_awuser; wire m0_awvalid, m0_awready;
    wire [63:0] m0_wdata; wire [7:0] m0_wstrb; wire m0_wlast; wire [0:0] m0_wuser; wire m0_wvalid, m0_wready;
    wire [8:0]  m0_bid; wire [1:0] m0_bresp; wire [0:0] m0_buser; wire m0_bvalid, m0_bready;
    wire [8:0]  m0_arid; wire [37:0] m0_araddr; wire [7:0] m0_arlen; wire [2:0] m0_arsize;
    wire [1:0]  m0_arburst; wire [1:0] m0_arlock; wire [3:0] m0_arcache; wire [2:0] m0_arprot;
    wire [3:0]  m0_arqos; wire [3:0] m0_arregion; wire [0:0] m0_aruser; wire m0_arvalid, m0_arready;
    wire [8:0]  m0_rid; wire [63:0] m0_rdata; wire [1:0] m0_rresp; wire m0_rlast; wire [0:0] m0_ruser;
    wire        m0_rvalid, m0_rready;

    wire [8:0]  m1_awid;  wire [37:0] m1_awaddr; wire [7:0] m1_awlen; wire [2:0] m1_awsize;
    wire [1:0]  m1_awburst; wire [1:0] m1_awlock; wire [3:0] m1_awcache; wire [2:0] m1_awprot;
    wire [3:0]  m1_awqos; wire [3:0] m1_awregion; wire [0:0] m1_awuser; wire m1_awvalid, m1_awready;
    wire [63:0] m1_wdata; wire [7:0] m1_wstrb; wire m1_wlast; wire [0:0] m1_wuser; wire m1_wvalid, m1_wready;
    wire [8:0]  m1_bid; wire [1:0] m1_bresp; wire [0:0] m1_buser; wire m1_bvalid, m1_bready;
    wire [8:0]  m1_arid; wire [37:0] m1_araddr; wire [7:0] m1_arlen; wire [2:0] m1_arsize;
    wire [1:0]  m1_arburst; wire [1:0] m1_arlock; wire [3:0] m1_arcache; wire [2:0] m1_arprot;
    wire [3:0]  m1_arqos; wire [3:0] m1_arregion; wire [0:0] m1_aruser; wire m1_arvalid, m1_arready;
    wire [8:0]  m1_rid; wire [63:0] m1_rdata; wire [1:0] m1_rresp; wire m1_rlast; wire [0:0] m1_ruser;
    wire        m1_rvalid, m1_rready;

    // ---- datapath + safety nets ----
    wire [63:0] pid_error;
    wire [31:0] pid_u_ai;
    wire [31:0] pid_actuator;
    wire        wd_timeout;
    wire        vbx_pulse;
    wire        nvpid_bid, nvpid_rid;  // nv_pid_top 1-bit ID -> 9-bit pad

    // ---- 1->2 AXI4 address demux on SLAVE3 ----
    axi4_demux2 #(.SEL_BIT(11)) u_demux (
        .clk(clk), .resetn(resetn),
        .s_awid(s_awid), .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awsize(s_awsize),
        .s_awburst(s_awburst), .s_awlock(s_awlock), .s_awcache(s_awcache), .s_awprot(s_awprot),
        .s_awqos(s_awqos), .s_awregion(s_awregion), .s_awuser(s_awuser), .s_awvalid(s_awvalid),
        .s_awready(s_awready), .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast),
        .s_wuser(s_wuser), .s_wvalid(s_wvalid), .s_wready(s_wready), .s_bid(s_bid),
        .s_bresp(s_bresp), .s_buser(s_buser), .s_bvalid(s_bvalid), .s_bready(s_bready),
        .s_arid(s_arid), .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arsize(s_arsize),
        .s_arburst(s_arburst), .s_arlock(s_arlock), .s_arcache(s_arcache), .s_arprot(s_arprot),
        .s_arqos(s_arqos), .s_arregion(s_arregion), .s_aruser(s_aruser), .s_arvalid(s_arvalid),
        .s_arready(s_arready), .s_rid(s_rid), .s_rdata(s_rdata), .s_rresp(s_rresp),
        .s_rlast(s_rlast), .s_ruser(s_ruser), .s_rvalid(s_rvalid), .s_rready(s_rready),
        .m0_awid(m0_awid), .m0_awaddr(m0_awaddr), .m0_awlen(m0_awlen), .m0_awsize(m0_awsize),
        .m0_awburst(m0_awburst), .m0_awlock(m0_awlock), .m0_awcache(m0_awcache), .m0_awprot(m0_awprot),
        .m0_awqos(m0_awqos), .m0_awregion(m0_awregion), .m0_awuser(m0_awuser), .m0_awvalid(m0_awvalid),
        .m0_awready(m0_awready), .m0_wdata(m0_wdata), .m0_wstrb(m0_wstrb), .m0_wlast(m0_wlast),
        .m0_wuser(m0_wuser), .m0_wvalid(m0_wvalid), .m0_wready(m0_wready), .m0_bid(m0_bid),
        .m0_bresp(m0_bresp), .m0_buser(m0_buser), .m0_bvalid(m0_bvalid), .m0_bready(m0_bready),
        .m0_arid(m0_arid), .m0_araddr(m0_araddr), .m0_arlen(m0_arlen), .m0_arsize(m0_arsize),
        .m0_arburst(m0_arburst), .m0_arlock(m0_arlock), .m0_arcache(m0_arcache), .m0_arprot(m0_arprot),
        .m0_arqos(m0_arqos), .m0_arregion(m0_arregion), .m0_aruser(m0_aruser), .m0_arvalid(m0_arvalid),
        .m0_arready(m0_arready), .m0_rid(m0_rid), .m0_rdata(m0_rdata), .m0_rresp(m0_rresp),
        .m0_rlast(m0_rlast), .m0_ruser(m0_ruser), .m0_rvalid(m0_rvalid), .m0_rready(m0_rready),
        .m1_awid(m1_awid), .m1_awaddr(m1_awaddr), .m1_awlen(m1_awlen), .m1_awsize(m1_awsize),
        .m1_awburst(m1_awburst), .m1_awlock(m1_awlock), .m1_awcache(m1_awcache), .m1_awprot(m1_awprot),
        .m1_awqos(m1_awqos), .m1_awregion(m1_awregion), .m1_awuser(m1_awuser), .m1_awvalid(m1_awvalid),
        .m1_awready(m1_awready), .m1_wdata(m1_wdata), .m1_wstrb(m1_wstrb), .m1_wlast(m1_wlast),
        .m1_wuser(m1_wuser), .m1_wvalid(m1_wvalid), .m1_wready(m1_wready), .m1_bid(m1_bid),
        .m1_bresp(m1_bresp), .m1_buser(m1_buser), .m1_bvalid(m1_bvalid), .m1_bready(m1_bready),
        .m1_arid(m1_arid), .m1_araddr(m1_araddr), .m1_arlen(m1_arlen), .m1_arsize(m1_arsize),
        .m1_arburst(m1_arburst), .m1_arlock(m1_arlock), .m1_arcache(m1_arcache), .m1_arprot(m1_arprot),
        .m1_arqos(m1_arqos), .m1_arregion(m1_arregion), .m1_aruser(m1_aruser), .m1_arvalid(m1_arvalid),
        .m1_arready(m1_arready), .m1_rid(m1_rid), .m1_rdata(m1_rdata), .m1_rresp(m1_rresp),
        .m1_rlast(m1_rlast), .m1_ruser(m1_ruser), .m1_rvalid(m1_rvalid), .m1_rready(m1_rready)
    );

    // ---- M0 -> nv_pid_top.axi4target (64-bit data; 6-bit addr, 1-bit ID adapt) ----
    // 1-bit ID echo padded to the 9-bit demux ID; unused master outputs tied.
    assign m0_bid   = {8'b0, nvpid_bid};
    assign m0_rid   = {8'b0, nvpid_rid};
    assign m0_buser = 1'b0;
    assign m0_ruser = 1'b0;

    nv_pid_top_top u_nv_pid_top (
        .clk                     (clk),
        .reset                   (1'b0),
        .axi4target_awvalid      (m0_awvalid), .axi4target_awready (m0_awready),
        .axi4target_awaddr       (m0_awaddr[5:0]), .axi4target_awid (m0_awid[0]),
        .axi4target_awlen        (m0_awlen), .axi4target_awsize (m0_awsize),
        .axi4target_awburst      (m0_awburst), .axi4target_awlock (m0_awlock),
        .axi4target_awcache      (m0_awcache), .axi4target_awprot (m0_awprot),
        .axi4target_awqos        (m0_awqos), .axi4target_awregion (m0_awregion),
        .axi4target_awuser       (1'b0),
        .axi4target_wvalid       (m0_wvalid), .axi4target_wready (m0_wready),
        .axi4target_wdata        (m0_wdata), .axi4target_wstrb (m0_wstrb),
        .axi4target_wlast        (m0_wlast), .axi4target_wuser (1'b0),
        .axi4target_bvalid       (m0_bvalid), .axi4target_bready (m0_bready),
        .axi4target_bid          (nvpid_bid), .axi4target_bresp (m0_bresp), .axi4target_buser (),
        .axi4target_arvalid      (m0_arvalid), .axi4target_arready (m0_arready),
        .axi4target_araddr       (m0_araddr[5:0]), .axi4target_arid (m0_arid[0]),
        .axi4target_arlen        (m0_arlen), .axi4target_arsize (m0_arsize),
        .axi4target_arburst      (m0_arburst), .axi4target_arlock (m0_arlock),
        .axi4target_arcache      (m0_arcache), .axi4target_arprot (m0_arprot),
        .axi4target_arqos        (m0_arqos), .axi4target_arregion (m0_arregion),
        .axi4target_aruser       (1'b0),
        .axi4target_rvalid       (m0_rvalid), .axi4target_rready (m0_rready),
        .axi4target_rdata        (m0_rdata), .axi4target_rid (nvpid_rid),
        .axi4target_rresp        (m0_rresp), .axi4target_rlast (m0_rlast), .axi4target_ruser (),
        // real-time datapath
        .error                   (pid_error),
        .u_AI_in                 (pid_u_ai),
        .ai_watchdog_timeout     (wd_timeout),
        .actuator_out_write_en   (),
        .actuator_out_write_data (pid_actuator)
    );

    // ---- M1 -> pid_csr (clean CSR slave; bridges AXI4-64 to AXI4-Lite-32) ----
    pid_csr_axi4_wrap u_pid_csr (
        .s_axi_aclk(clk), .s_axi_aresetn(resetn),
        .s_axi_awid(m1_awid), .s_axi_awaddr(m1_awaddr), .s_axi_awlen(m1_awlen),
        .s_axi_awsize(m1_awsize), .s_axi_awburst(m1_awburst), .s_axi_awlock(m1_awlock),
        .s_axi_awcache(m1_awcache), .s_axi_awprot(m1_awprot), .s_axi_awqos(m1_awqos),
        .s_axi_awregion(m1_awregion), .s_axi_awuser(m1_awuser), .s_axi_awvalid(m1_awvalid),
        .s_axi_awready(m1_awready), .s_axi_wdata(m1_wdata), .s_axi_wstrb(m1_wstrb),
        .s_axi_wlast(m1_wlast), .s_axi_wuser(m1_wuser), .s_axi_wvalid(m1_wvalid),
        .s_axi_wready(m1_wready), .s_axi_bid(m1_bid), .s_axi_bresp(m1_bresp),
        .s_axi_buser(m1_buser), .s_axi_bvalid(m1_bvalid), .s_axi_bready(m1_bready),
        .s_axi_arid(m1_arid), .s_axi_araddr(m1_araddr), .s_axi_arlen(m1_arlen),
        .s_axi_arsize(m1_arsize), .s_axi_arburst(m1_arburst), .s_axi_arlock(m1_arlock),
        .s_axi_arcache(m1_arcache), .s_axi_arprot(m1_arprot), .s_axi_arqos(m1_arqos),
        .s_axi_arregion(m1_arregion), .s_axi_aruser(m1_aruser), .s_axi_arvalid(m1_arvalid),
        .s_axi_arready(m1_arready), .s_axi_rid(m1_rid), .s_axi_rdata(m1_rdata),
        .s_axi_rresp(m1_rresp), .s_axi_rlast(m1_rlast), .s_axi_ruser(m1_ruser),
        .s_axi_rvalid(m1_rvalid), .s_axi_rready(m1_rready),
        .error_shadow_out(pid_error), .u_ai_shadow_out(pid_u_ai),
        .tap_post_clamp_in(pid_actuator), .tap_watchdog_in(wd_timeout)
    );

    // ---- safety: V250 output_valid -> pulse -> watchdog ----
    vbx_pulse_gen u_pulse (
        .clk_i(clk), .resetn_i(resetn),
        .vbx_output_valid_i(vbx_output_valid), .pulse_o(vbx_pulse)
    );
    watchdog_timer #(.WATCHDOG_TIMEOUT_CYCLES(WATCHDOG_TIMEOUT_CYCLES)) u_wdog (
        .clk(clk), .resetn(resetn), .ai_heartbeat(vbx_pulse), .timeout(wd_timeout)
    );

endmodule
