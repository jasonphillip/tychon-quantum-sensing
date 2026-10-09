`timescale 1ns/1ps
// tb_actuator.v — full PID datapath sim for the two-slot pid_subsystem WITH the
// actuator-latch fix. Sets gains via M0 (nv_pid_top.axi4target), error via M1
// (pid_csr), pulses start (M0 0x08 = START_STATUS_ADDR), waits for the pipeline,
// then reads the LATCHED actuator at M1 0x844. Expect actuator ~= Kp*error
// (Ki=Kd=0, watchdog timed-out => pure PID, output clamped to [out_min,out_max]).
//
// 64-bit-bus lane rule: byte offset bit[2]=0 -> low lane, bit[2]=1 -> high lane.
module tb_actuator;
  reg clk = 1'b0; reg resetn = 1'b0;
  always #4 clk = ~clk;

  reg  [8:0]  s_awid;  reg [37:0] s_awaddr; reg [7:0] s_awlen; reg [2:0] s_awsize;
  reg  [1:0]  s_awburst; reg [1:0] s_awlock; reg [3:0] s_awcache; reg [2:0] s_awprot;
  reg  [3:0]  s_awqos; reg [3:0] s_awregion; reg [0:0] s_awuser; reg s_awvalid; wire s_awready;
  reg  [63:0] s_wdata; reg [7:0] s_wstrb; reg s_wlast; reg [0:0] s_wuser; reg s_wvalid; wire s_wready;
  wire [8:0]  s_bid; wire [1:0] s_bresp; wire [0:0] s_buser; wire s_bvalid; reg s_bready;
  reg  [8:0]  s_arid;  reg [37:0] s_araddr; reg [7:0] s_arlen; reg [2:0] s_arsize;
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
  integer errors = 0;
  integer delta;
  reg [31:0] rcap;

  task step(input integer n); begin repeat (n) @(posedge clk); end endtask

  task do_write32(input [37:0] addr, input [31:0] d32, input [8:0] id);
    begin
      @(posedge clk);
      s_awaddr <= addr; s_awid <= id; s_awlen <= 8'd0; s_awsize <= 3'd2; s_awburst <= 2'b01; s_awvalid <= 1'b1;
      if (addr[2]) begin s_wdata <= {d32, 32'h0}; s_wstrb <= 8'hF0; end
      else         begin s_wdata <= {32'h0, d32}; s_wstrb <= 8'h0F; end
      s_wlast <= 1'b1; s_wvalid <= 1'b1; s_bready <= 1'b1;
      k=0; @(posedge clk); while (!s_awready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_awready) $fatal(1, "WRITE 0x%03h AW-HANG", addr);
      s_awvalid <= 1'b0;
      k=0; while (!s_wready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_wready) $fatal(1, "WRITE 0x%03h W-HANG", addr);
      s_wvalid <= 1'b0;
      k=0; while (!s_bvalid && k<300) begin @(posedge clk); k=k+1; end
      @(posedge clk); s_bready <= 1'b0;
    end
  endtask

  task do_read32(input [37:0] addr, input [8:0] id);
    begin
      @(posedge clk);
      s_araddr <= addr; s_arid <= id; s_arlen <= 8'd0; s_arsize <= 3'd2; s_arburst <= 2'b01; s_arvalid <= 1'b1; s_rready <= 1'b1;
      k=0; @(posedge clk); while (!s_arready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_arready) $fatal(1, "READ 0x%03h AR-HANG", addr);
      s_arvalid <= 1'b0;
      k=0; while (!s_rvalid && k<300) begin @(posedge clk); k=k+1; end
      if (!s_rvalid) $fatal(1, "READ 0x%03h R-HANG", addr);
      rcap = addr[2] ? s_rdata[63:32] : s_rdata[31:0];
      @(posedge clk); s_rready <= 1'b0;
    end
  endtask

  task run_err(input [31:0] elo, input [31:0] ehi,
               input [31:0] expected, input [127:0] label);
    begin
      do_write32(38'h810, elo, 9'd1);   // error_low  (M1)
      do_write32(38'h814, ehi, 9'd1);   // error_high (M1)
      do_write32(38'h008, 32'h1, 9'd1); // pulse start (M0 START_STATUS_ADDR)
      step(20);                          // pipeline latency
      do_read32(38'h844, 9'd1);          // read latched actuator (M1 post_clamp)
      delta = $signed(rcap) - $signed(expected);
      $display("%0s actuator=0x%08h expected=0x%08h delta=%0d LSB", label, rcap, expected, delta);
      // SmartHLS fixed-point rounding can differ by one Q16.16 LSB.
      if ($isunknown(rcap) || delta < -1 || delta > 1) begin
        errors = errors + 1;
        $display("FAIL: %0s actuator mismatch", label);
      end
    end
  endtask

  initial begin
    s_awid=0;s_awaddr=0;s_awlen=0;s_awsize=0;s_awburst=0;s_awlock=0;s_awcache=0;s_awprot=0;s_awqos=0;s_awregion=0;s_awuser=0;s_awvalid=0;
    s_wdata=0;s_wstrb=0;s_wlast=0;s_wuser=0;s_wvalid=0;s_bready=0;
    s_arid=0;s_araddr=0;s_arlen=0;s_arsize=0;s_arburst=0;s_arlock=0;s_arcache=0;s_arprot=0;s_arqos=0;s_arregion=0;s_aruser=0;s_arvalid=0;s_rready=0;
    resetn=0; step(20); resetn=1; step(10);

    $display("================ TWO-SLOT ACTUATOR DATAPATH SIM ================");
    // gains/limits via M0 (axi4target)
    do_write32(38'h018, 32'hFFFF0000, 9'd1); // out_min = -1.0
    do_write32(38'h01C, 32'h00010000, 9'd1); // out_max = +1.0
    do_write32(38'h00C, 32'h0000CCCD, 9'd1); // Kp = 0.8
    do_write32(38'h010, 32'h00000000, 9'd1); // Ki = 0
    do_write32(38'h014, 32'h00000000, 9'd1); // Kd = 0
    do_read32(38'h00C, 9'd1);
    $display("Kp readback = 0x%08h (expect 0000cccd)", rcap);
    if (rcap !== 32'h0000CCCD) begin errors = errors + 1; $display("FAIL: Kp readback"); end
    do_write32(38'h818, 32'h00000000, 9'd1); // u_ai = 0 (M1)

    // sweep error (Q34.30), read latched actuator (expect ~Kp*error in Q16.16)
    run_err(32'h20000000, 32'h00000000, 32'h00006666, "err= 0.50 ->");  // expect ~0.4
    run_err(32'hE0000000, 32'hFFFFFFFF, 32'hFFFF999A, "err=-0.50 ->");  // expect ~-0.4
    run_err(32'h10000000, 32'h00000000, 32'h00003333, "err= 0.25 ->");  // expect ~0.2
    run_err(32'h80000000, 32'h00000000, 32'h00010000, "err= 2.00 ->");  // clamp to 1.0
    if (errors == 0) $display("PASS: actuator datapath (0 errors)");
    else begin
      $display("FAIL: actuator datapath (%0d errors)", errors);
      $fatal(1, "actuator datapath mismatch");
    end
    $finish;
  end

  initial begin #500000; $fatal(1, "GLOBAL TIMEOUT"); end
endmodule
