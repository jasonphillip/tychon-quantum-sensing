// axi4_demux2.v
//
// AXI4 (full, 64-bit data, 38-bit address, 9-bit ID) 1-master -> 2-slave address
// demux. Hand-written equivalent of the runbook's CoreAXI4Interconnect 1M x 2S:
// splits the one free FIC0_INITIATOR crossbar slot (SLAVE3 @ 0x60040000, 4 KiB)
// into two sub-slaves so both nv_pid_top.axi4target (gains) AND pid_csr (CSR) get
// a clean, separately-decoded AXI surface from the single available slot.
//
//   addr[SEL_BIT]==0  -> M0  (low half,  0x60040000-0x600407ff : nv_pid_top)
//   addr[SEL_BIT]==1  -> M1  (high half, 0x60040800-0x60040fff : pid_csr)
//
// DESIGN: AW/W/AR payload is BROADCAST to both masters; the per-channel selection
// is registered at the AW/AR handshake (w_sel/r_sel) and held until the B/R
// handshake, so W-data and the response route to the same master for the whole
// transaction. Handshakes are pure combinational gating/muxing of the sub-slaves'
// own ready/valid — the demux adds NO new sequential gating on the data path.
// Write and read are independent, single-outstanding each (the MSS issues
// single-beat register accesses).
//
// SAFETY (no bus hang / no U54 wedge): every SLAVE3 address maps to exactly one
// sub-slave (no decode gap), the selected sub-slave always completes (its FSM
// always responds), and this demux only forwards/mux'es that completion. AXI rule
// respected: VALID never depends combinationally on READY (the sub-slaves drive
// registered *READY/*VALID).

module axi4_demux2 #(
    parameter integer SEL_BIT = 11
) (
    input  wire        clk,
    input  wire        resetn,

    // ---- S : slave port (from crossbar SLAVE3 master) ----
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
    input  wire        s_rready,

    // ---- M0 ----
    output wire [8:0]  m0_awid,  output wire [37:0] m0_awaddr, output wire [7:0] m0_awlen,
    output wire [2:0]  m0_awsize, output wire [1:0] m0_awburst, output wire [1:0] m0_awlock,
    output wire [3:0]  m0_awcache, output wire [2:0] m0_awprot, output wire [3:0] m0_awqos,
    output wire [3:0]  m0_awregion, output wire [0:0] m0_awuser, output wire m0_awvalid,
    input  wire        m0_awready,
    output wire [63:0] m0_wdata, output wire [7:0] m0_wstrb, output wire m0_wlast,
    output wire [0:0]  m0_wuser, output wire m0_wvalid, input wire m0_wready,
    input  wire [8:0]  m0_bid, input wire [1:0] m0_bresp, input wire [0:0] m0_buser,
    input  wire        m0_bvalid, output wire m0_bready,
    output wire [8:0]  m0_arid, output wire [37:0] m0_araddr, output wire [7:0] m0_arlen,
    output wire [2:0]  m0_arsize, output wire [1:0] m0_arburst, output wire [1:0] m0_arlock,
    output wire [3:0]  m0_arcache, output wire [2:0] m0_arprot, output wire [3:0] m0_arqos,
    output wire [3:0]  m0_arregion, output wire [0:0] m0_aruser, output wire m0_arvalid,
    input  wire        m0_arready,
    input  wire [8:0]  m0_rid, input wire [63:0] m0_rdata, input wire [1:0] m0_rresp,
    input  wire        m0_rlast, input wire [0:0] m0_ruser, input wire m0_rvalid,
    output wire        m0_rready,

    // ---- M1 ----
    output wire [8:0]  m1_awid,  output wire [37:0] m1_awaddr, output wire [7:0] m1_awlen,
    output wire [2:0]  m1_awsize, output wire [1:0] m1_awburst, output wire [1:0] m1_awlock,
    output wire [3:0]  m1_awcache, output wire [2:0] m1_awprot, output wire [3:0] m1_awqos,
    output wire [3:0]  m1_awregion, output wire [0:0] m1_awuser, output wire m1_awvalid,
    input  wire        m1_awready,
    output wire [63:0] m1_wdata, output wire [7:0] m1_wstrb, output wire m1_wlast,
    output wire [0:0]  m1_wuser, output wire m1_wvalid, input wire m1_wready,
    input  wire [8:0]  m1_bid, input wire [1:0] m1_bresp, input wire [0:0] m1_buser,
    input  wire        m1_bvalid, output wire m1_bready,
    output wire [8:0]  m1_arid, output wire [37:0] m1_araddr, output wire [7:0] m1_arlen,
    output wire [2:0]  m1_arsize, output wire [1:0] m1_arburst, output wire [1:0] m1_arlock,
    output wire [3:0]  m1_arcache, output wire [2:0] m1_arprot, output wire [3:0] m1_arqos,
    output wire [3:0]  m1_arregion, output wire [0:0] m1_aruser, output wire m1_arvalid,
    input  wire        m1_arready,
    input  wire [8:0]  m1_rid, input wire [63:0] m1_rdata, input wire [1:0] m1_rresp,
    input  wire        m1_rlast, input wire [0:0] m1_ruser, input wire m1_rvalid,
    output wire        m1_rready
);

    // --- Broadcast AW/W/AR payload to both masters ---
    assign {m0_awid,m0_awaddr,m0_awlen,m0_awsize,m0_awburst,m0_awlock,m0_awcache,m0_awprot,m0_awqos,m0_awregion,m0_awuser}
         = {s_awid,s_awaddr,s_awlen,s_awsize,s_awburst,s_awlock,s_awcache,s_awprot,s_awqos,s_awregion,s_awuser};
    assign {m1_awid,m1_awaddr,m1_awlen,m1_awsize,m1_awburst,m1_awlock,m1_awcache,m1_awprot,m1_awqos,m1_awregion,m1_awuser}
         = {s_awid,s_awaddr,s_awlen,s_awsize,s_awburst,s_awlock,s_awcache,s_awprot,s_awqos,s_awregion,s_awuser};
    assign {m0_wdata,m0_wstrb,m0_wlast,m0_wuser} = {s_wdata,s_wstrb,s_wlast,s_wuser};
    assign {m1_wdata,m1_wstrb,m1_wlast,m1_wuser} = {s_wdata,s_wstrb,s_wlast,s_wuser};
    assign {m0_arid,m0_araddr,m0_arlen,m0_arsize,m0_arburst,m0_arlock,m0_arcache,m0_arprot,m0_arqos,m0_arregion,m0_aruser}
         = {s_arid,s_araddr,s_arlen,s_arsize,s_arburst,s_arlock,s_arcache,s_arprot,s_arqos,s_arregion,s_aruser};
    assign {m1_arid,m1_araddr,m1_arlen,m1_arsize,m1_arburst,m1_arlock,m1_arcache,m1_arprot,m1_arqos,m1_arregion,m1_aruser}
         = {s_arid,s_araddr,s_arlen,s_arsize,s_arburst,s_arlock,s_arcache,s_arprot,s_arqos,s_arregion,s_aruser};

    // ===== Write path (single-outstanding) =====
    reg w_busy, w_sel;
    wire aw_sel = w_busy ? w_sel : s_awaddr[SEL_BIT];
    assign m0_awvalid = s_awvalid & ~w_busy & ~aw_sel;
    assign m1_awvalid = s_awvalid & ~w_busy &  aw_sel;
    assign s_awready  = ~w_busy & (aw_sel ? m1_awready : m0_awready);
    wire aw_fire = s_awvalid & s_awready;

    assign m0_wvalid = s_wvalid & w_busy & ~w_sel;
    assign m1_wvalid = s_wvalid & w_busy &  w_sel;
    assign s_wready  = w_busy & (w_sel ? m1_wready : m0_wready);

    assign s_bvalid  = w_busy & (w_sel ? m1_bvalid : m0_bvalid);
    assign s_bid     = w_sel ? m1_bid   : m0_bid;
    assign s_bresp   = w_sel ? m1_bresp : m0_bresp;
    assign s_buser   = w_sel ? m1_buser : m0_buser;
    assign m0_bready = s_bready & w_busy & ~w_sel;
    assign m1_bready = s_bready & w_busy &  w_sel;
    wire b_fire = s_bvalid & s_bready;

    always @(posedge clk) begin
        if (!resetn) begin w_busy <= 1'b0; w_sel <= 1'b0; end
        else if (aw_fire) begin w_busy <= 1'b1; w_sel <= s_awaddr[SEL_BIT]; end
        else if (b_fire)  begin w_busy <= 1'b0; end
    end

    // ===== Read path (single-outstanding) =====
    reg r_busy, r_sel;
    wire ar_sel = r_busy ? r_sel : s_araddr[SEL_BIT];
    assign m0_arvalid = s_arvalid & ~r_busy & ~ar_sel;
    assign m1_arvalid = s_arvalid & ~r_busy &  ar_sel;
    assign s_arready  = ~r_busy & (ar_sel ? m1_arready : m0_arready);
    wire ar_fire = s_arvalid & s_arready;

    assign s_rvalid  = r_busy & (r_sel ? m1_rvalid : m0_rvalid);
    assign s_rid     = r_sel ? m1_rid   : m0_rid;
    assign s_rdata   = r_sel ? m1_rdata : m0_rdata;
    assign s_rresp   = r_sel ? m1_rresp : m0_rresp;
    assign s_rlast   = r_busy & (r_sel ? m1_rlast : m0_rlast);
    assign s_ruser   = r_sel ? m1_ruser : m0_ruser;
    assign m0_rready = s_rready & r_busy & ~r_sel;
    assign m1_rready = s_rready & r_busy &  r_sel;
    wire r_fire = s_rvalid & s_rready & s_rlast;

    always @(posedge clk) begin
        if (!resetn) begin r_busy <= 1'b0; r_sel <= 1'b0; end
        else if (ar_fire) begin r_busy <= 1'b1; r_sel <= s_araddr[SEL_BIT]; end
        else if (r_fire)  begin r_busy <= 1'b0; end
    end

endmodule
