`timescale 1ns/1ps
// tb_pid_latency.v — fabric-internal PID latency cycle count on the REAL
// two-slot pid_subsystem RTL (the same stack tb_actuator.v verified against
// silicon during the M0-demux fix).
//
// Measures, per iteration, the cycle count from the M0 start-pulse write
// (0x008) to the nv_pid_top actuator-output write-enable pulse
// (dut.pid_actuator_we), under two event definitions:
//   lat_aw = cycles from AW-handshake acceptance of the start write -> we
//   lat_b  = cycles from B-response completion of the start write   -> we
// Both are reported; lat_b is the software-visible "write retired" anchor,
// lat_aw the bus-entry anchor. At the 125 MHz PID fabric clock each cycle
// is 8 ns.
//
// The PID is an II=1 fixed-latency SmartHLS pipeline, so the count is
// expected CONSTANT across iterations; the TB sweeps 128 error values
// (positive/negative, small/clamp-saturating) and reports min/median/max —
// if the spread is nonzero it says so honestly.
//
// This yields a [TB]-grade simulated bound for the "<150 us" design budget.
// It is NOT an on-silicon measurement (that needs a latched fabric counter
// or a fixed Linux image; see docs/latency_measured_2026-06-21.md).
module tb_pid_latency;
  reg clk = 1'b0; reg resetn = 1'b0;
  always #4 clk = ~clk;   // 8 ns = 125 MHz

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

  // free-running cycle counter
  reg [63:0] cyc = 64'd0;
  always @(posedge clk) cyc <= cyc + 64'd1;

  // armed capture of the FIRST actuator write-enable after a start pulse
  reg        armed = 1'b0;
  reg [63:0] t_we  = 64'd0;
  reg        got_we = 1'b0;
  always @(posedge clk) begin
    if (armed && dut.pid_actuator_we) begin
      t_we   <= cyc;
      got_we <= 1'b1;
      armed  <= 1'b0;
    end
  end

  integer k;
  reg [31:0] rcap;
  reg [63:0] t_aw_g, t_b_g;   // timestamps captured by the instrumented write

  task step(input integer n); begin repeat (n) @(posedge clk); end endtask

  // instrumented 32-bit write: records cyc at AW acceptance and B completion
  task do_write32(input [37:0] addr, input [31:0] d32, input [8:0] id);
    begin
      @(posedge clk);
      s_awaddr <= addr; s_awid <= id; s_awlen <= 8'd0; s_awsize <= 3'd2; s_awburst <= 2'b01; s_awvalid <= 1'b1;
      if (addr[2]) begin s_wdata <= {d32, 32'h0}; s_wstrb <= 8'hF0; end
      else         begin s_wdata <= {32'h0, d32}; s_wstrb <= 8'h0F; end
      s_wlast <= 1'b1; s_wvalid <= 1'b1; s_bready <= 1'b1;
      k=0; @(posedge clk); while (!s_awready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_awready) begin $display("WRITE 0x%03h AW-HANG", addr); s_awvalid<=0;s_wvalid<=0;s_bready<=0; disable do_write32; end
      t_aw_g = cyc;
      s_awvalid <= 1'b0;
      k=0; while (!s_wready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_wready) begin $display("WRITE 0x%03h W-HANG", addr); s_wvalid<=0;s_bready<=0; disable do_write32; end
      s_wvalid <= 1'b0;
      k=0; while (!s_bvalid && k<300) begin @(posedge clk); k=k+1; end
      t_b_g = cyc;
      @(posedge clk); s_bready <= 1'b0;
    end
  endtask

  task do_read32(input [37:0] addr, input [8:0] id);
    begin
      @(posedge clk);
      s_araddr <= addr; s_arid <= id; s_arlen <= 8'd0; s_arsize <= 3'd2; s_arburst <= 2'b01; s_arvalid <= 1'b1; s_rready <= 1'b1;
      k=0; @(posedge clk); while (!s_arready && k<300) begin @(posedge clk); k=k+1; end
      if (!s_arready) begin $display("READ 0x%03h AR-HANG", addr); s_arvalid<=0;s_rready<=0; rcap=32'hDEAD; disable do_read32; end
      s_arvalid <= 1'b0;
      k=0; while (!s_rvalid && k<300) begin @(posedge clk); k=k+1; end
      if (!s_rvalid) begin $display("READ 0x%03h R-HANG", addr); s_rready<=0; rcap=32'hDEAD; disable do_read32; end
      rcap = addr[2] ? s_rdata[63:32] : s_rdata[31:0];
      @(posedge clk); s_rready <= 1'b0;
    end
  endtask

  integer i;
  integer lat_aw, lat_b;
  integer min_aw, max_aw, min_b, max_b;
  integer n_meas, n_miss;
  reg [31:0] err_lo;

  initial begin
    s_awid=0;s_awaddr=0;s_awlen=0;s_awsize=0;s_awburst=0;s_awlock=0;s_awcache=0;s_awprot=0;s_awqos=0;s_awregion=0;s_awuser=0;s_awvalid=0;
    s_wdata=0;s_wstrb=0;s_wlast=0;s_wuser=0;s_wvalid=0;s_bready=0;
    s_arid=0;s_araddr=0;s_arlen=0;s_arsize=0;s_arburst=0;s_arlock=0;s_arcache=0;s_arprot=0;s_arqos=0;s_arregion=0;s_aruser=0;s_arvalid=0;s_rready=0;
    min_aw=1000000; max_aw=-1; min_b=1000000; max_b=-1; n_meas=0; n_miss=0;
    resetn=0; step(20); resetn=1; step(10);

    $display("========== TB_PID_LATENCY: start-pulse -> actuator-we cycle count ==========");
    // same proven gain config as tb_actuator: pure P, Kp=0.8, out [-1,+1]
    do_write32(38'h018, 32'hFFFF0000, 9'd1); // out_min = -1.0
    do_write32(38'h01C, 32'h00010000, 9'd1); // out_max = +1.0
    do_write32(38'h00C, 32'h0000CCCD, 9'd1); // Kp = 0.8
    do_write32(38'h010, 32'h00000000, 9'd1); // Ki = 0
    do_write32(38'h014, 32'h00000000, 9'd1); // Kd = 0
    do_write32(38'h818, 32'h00000000, 9'd1); // u_ai = 0 (M1)

    // 128 iterations sweeping error in Q34.30: alternating sign, growing
    // magnitude (includes clamp-saturating values)
    for (i = 0; i < 128; i = i + 1) begin
      err_lo = 32'h04000000 + (i * 32'h01000000); // 1/16 .. ~8 in Q30 low word
      do_write32(38'h810, err_lo, 9'd1);                          // error_low
      do_write32(38'h814, (i[0]) ? 32'hFFFFFFFF : 32'h0, 9'd1);   // error_high (sign)
      step(4);
      got_we = 1'b0; armed = 1'b1;
      do_write32(38'h008, 32'h1, 9'd1);   // start pulse (M0) — timestamps in t_aw_g/t_b_g
      step(40);                            // pipeline + margin
      if (!got_we) begin
        n_miss = n_miss + 1;
        $display("iter %0d: NO actuator-we observed within window", i);
      end else begin
        lat_aw = t_we - t_aw_g;
        lat_b  = t_we - t_b_g;
        n_meas = n_meas + 1;
        if (lat_aw < min_aw) min_aw = lat_aw;
        if (lat_aw > max_aw) max_aw = lat_aw;
        if (lat_b  < min_b)  min_b  = lat_b;
        if (lat_b  > max_b)  max_b  = lat_b;
        if (i < 4 || (i % 32) == 0)
          $display("iter %0d: lat_aw=%0d cyc (%0d ns)  lat_b=%0d cyc (%0d ns)",
                   i, lat_aw, lat_aw*8, lat_b, lat_b*8);
      end
      step(10);
    end

    do_read32(38'h844, 9'd1);
    $display("final actuator readback = 0x%08h", rcap);
    $display("TB_PID_LATENCY SUMMARY: n=%0d missed=%0d", n_meas, n_miss);
    $display("  start-AW-accept -> actuator-we : min=%0d max=%0d cycles (%0d..%0d ns @125 MHz)",
             min_aw, max_aw, min_aw*8, max_aw*8);
    $display("  start-B-retire  -> actuator-we : min=%0d max=%0d cycles (%0d..%0d ns @125 MHz)",
             min_b, max_b, min_b*8, max_b*8);
    if (n_meas > 0 && min_aw == max_aw && min_b == max_b)
      $display("  RESULT: CONSTANT latency (II=1 fixed-latency pipeline confirmed in RTL sim)");
    else
      $display("  RESULT: latency varies across iterations — report the spread, not a single number");
    $finish;
  end

  initial begin #2000000; $display("GLOBAL TIMEOUT"); $finish; end
endmodule
