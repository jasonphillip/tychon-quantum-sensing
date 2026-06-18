`timescale 1ns/1ps
// tb_m0.v — reproduce + isolate the M0 (nv_pid_top.axi4target) AXI hang in the
// two-slot pid_subsystem. Drives single-beat AXI4 reads/writes at the S port and
// reports OK / HANG, varying the transaction ID. M1 (pid_csr) is the control.
//
// Hypothesis under test: the demux truncates the 9-bit AXI ID to nv_pid_top's
// 1-bit port and pads the reply (m0_rid = {8'b0, rid}); a non-zero master ID then
// never matches on the response -> M0 hangs. M1 passes the full ID, so M1 works.
module tb_m0;
  reg clk = 1'b0; reg resetn = 1'b0;
  always #4 clk = ~clk;              // 125 MHz (8 ns)

  reg  [8:0]  s_awid;  reg [37:0] s_awaddr; reg [7:0] s_awlen; reg [2:0] s_awsize;
  reg  [1:0]  s_awburst; reg [1:0] s_awlock; reg [3:0] s_awcache; reg [2:0] s_awprot;
  reg  [3:0]  s_awqos; reg [3:0] s_awregion; reg [0:0] s_awuser; reg s_awvalid; wire s_awready;
  reg  [63:0] s_wdata; reg [7:0] s_wstrb; reg s_wlast; reg [0:0] s_wuser; reg s_wvalid; wire s_wready;
  wire [8:0]  s_bid; wire [1:0] s_bresp; wire [0:0] s_buser; wire s_bvalid; reg s_bready;
  reg  [8:0]  s_arid; reg [37:0] s_araddr; reg [7:0] s_arlen; reg [2:0] s_arsize;
  reg  [1:0]  s_arburst; reg [1:0] s_arlock; reg [3:0] s_arcache; reg [2:0] s_arprot;
  reg  [3:0]  s_arqos; reg [3:0] s_arregion; reg [0:0] s_aruser; reg s_arvalid; wire s_arready;
  wire [8:0]  s_rid; wire [63:0] s_rdata; wire [1:0] s_rresp; wire s_rlast; wire [0:0] s_ruser; wire s_rvalid; reg s_rready;

  pid_subsystem #(.WATCHDOG_TIMEOUT_CYCLES(62500000)) dut (
    .clk(clk), .resetn(resetn), .vbx_output_valid(1'b0),
    .s_awid(s_awid), .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awsize(s_awsize),
    .s_awburst(s_awburst), .s_awlock(s_awlock), .s_awcache(s_awcache), .s_awprot(s_awprot),
    .s_awqos(s_awqos), .s_awregion(s_awregion), .s_awuser(s_awuser), .s_awvalid(s_awvalid), .s_awready(s_awready),
    .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast), .s_wuser(s_wuser), .s_wvalid(s_wvalid), .s_wready(s_wready),
    .s_bid(s_bid), .s_bresp(s_bresp), .s_buser(s_buser), .s_bvalid(s_bvalid), .s_bready(s_bready),
    .s_arid(s_arid), .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arsize(s_arsize),
    .s_arburst(s_arburst), .s_arlock(s_arlock), .s_arcache(s_arcache), .s_arprot(s_arprot),
    .s_arqos(s_arqos), .s_arregion(s_arregion), .s_aruser(s_aruser), .s_arvalid(s_arvalid), .s_arready(s_arready),
    .s_rid(s_rid), .s_rdata(s_rdata), .s_rresp(s_rresp), .s_rlast(s_rlast), .s_ruser(s_ruser), .s_rvalid(s_rvalid), .s_rready(s_rready)
  );

  integer k;

  task do_read(input [37:0] addr, input [8:0] id);
    begin
      @(posedge clk);
      s_araddr <= addr; s_arid <= id; s_arlen <= 8'd0; s_arsize <= 3'd2; s_arburst <= 2'b01;
      s_arvalid <= 1'b1; s_rready <= 1'b1;
      // wait for AR handshake (arready)
      k = 0;
      @(posedge clk);
      while (!s_arready && k < 300) begin @(posedge clk); k = k + 1; end
      if (!s_arready) begin
        $display("READ  addr=0x%03h id=%0d -> AR-HANG (no arready in 300 cyc)", addr, id);
        s_arvalid <= 1'b0; s_rready <= 1'b0; disable do_read;
      end
      s_arvalid <= 1'b0;
      // wait for R data (rvalid)
      k = 0;
      while (!s_rvalid && k < 300) begin @(posedge clk); k = k + 1; end
      if (!s_rvalid) begin
        $display("READ  addr=0x%03h id=%0d -> R-HANG (arready ok, no rvalid in 300 cyc)", addr, id);
        s_rready <= 1'b0; disable do_read;
      end
      $display("READ  addr=0x%03h id=%0d -> OK  rdata=0x%016h rid=%0d rresp=%0d rlast=%b", addr, id, s_rdata, s_rid, s_rresp, s_rlast);
      @(posedge clk); s_rready <= 1'b0;
    end
  endtask

  task do_write(input [37:0] addr, input [63:0] data, input [8:0] id);
    begin
      @(posedge clk);
      s_awaddr <= addr; s_awid <= id; s_awlen <= 8'd0; s_awsize <= 3'd2; s_awburst <= 2'b01; s_awvalid <= 1'b1;
      s_wdata <= data; s_wstrb <= 8'hFF; s_wlast <= 1'b1; s_wvalid <= 1'b1; s_bready <= 1'b1;
      k = 0;
      @(posedge clk);
      while (!s_awready && k < 300) begin @(posedge clk); k = k + 1; end
      if (!s_awready) begin $display("WRITE addr=0x%03h id=%0d -> AW-HANG (no awready)", addr, id); s_awvalid<=0; s_wvalid<=0; s_bready<=0; disable do_write; end
      s_awvalid <= 1'b0;
      k = 0;
      while (!s_wready && k < 300) begin @(posedge clk); k = k + 1; end
      if (!s_wready) begin $display("WRITE addr=0x%03h id=%0d -> W-HANG (no wready)", addr, id); s_wvalid<=0; s_bready<=0; disable do_write; end
      s_wvalid <= 1'b0;
      k = 0;
      while (!s_bvalid && k < 300) begin @(posedge clk); k = k + 1; end
      if (!s_bvalid) begin $display("WRITE addr=0x%03h id=%0d -> B-HANG (no bvalid)", addr, id); s_bready<=0; disable do_write; end
      $display("WRITE addr=0x%03h id=%0d -> OK  bid=%0d bresp=%0d", addr, id, s_bid, s_bresp);
      @(posedge clk); s_bready <= 1'b0;
    end
  endtask

  initial begin
    s_awid=0;s_awaddr=0;s_awlen=0;s_awsize=0;s_awburst=0;s_awlock=0;s_awcache=0;s_awprot=0;s_awqos=0;s_awregion=0;s_awuser=0;s_awvalid=0;
    s_wdata=0;s_wstrb=0;s_wlast=0;s_wuser=0;s_wvalid=0;s_bready=0;
    s_arid=0;s_araddr=0;s_arlen=0;s_arsize=0;s_arburst=0;s_arlock=0;s_arcache=0;s_arprot=0;s_arqos=0;s_arregion=0;s_aruser=0;s_arvalid=0;s_rready=0;
    resetn = 1'b0; repeat (20) @(posedge clk); resetn = 1'b1; repeat (10) @(posedge clk);

    $display("================ TWO-SLOT M0/M1 AXI SIM ================");
    $display("--- M1 (pid_csr) read csr region, id=5 (control: expect OK) ---");
    do_read(38'h804, 9'd5);
    $display("--- M0 (nv_pid_top gains) read Kp@0x0C, id=5 (expect HANG if ID-trunc) ---");
    do_read(38'h00C, 9'd5);
    $display("--- M0 read Kp@0x0C, id=0 (completes => ID truncation is the cause) ---");
    do_read(38'h00C, 9'd0);
    $display("--- M0 write out_max@0x1C=0x10000, id=5 (write path) ---");
    do_write(38'h01C, 64'h0001_0000, 9'd5);
    $display("--- M0 write out_max@0x1C=0x10000, id=0 ---");
    do_write(38'h01C, 64'h0001_0000, 9'd0);
    $display("================ DONE ================");
    $finish;
  end

  initial begin
    #200000;
    $display("GLOBAL TIMEOUT — sim ran too long, forcing finish");
    $finish;
  end
endmodule
