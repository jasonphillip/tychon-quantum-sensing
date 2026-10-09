// pid_io_block.v
//
// AXI4-Lite slave that exposes the nv_pid_top I/O registers needed to
// (a) defeat Synplify constant-folding of the PID datapath at synthesis
// time and (b) provide an MSS-writable test-input + actuator-readback
// register block for Phase II HITL firmware.
//
// REGISTER MAP (byte offsets, all 32-bit aligned):
//   +0x00  actuator_out_capture   RO   captured actuator_out_write_data
//                                       on rising edge of actuator_out_write_en
//                                       (Q16.16 fixed-point, sign-extended to 32b)
//   +0x04  actuator_out_status    RO   bit[0] = capture_valid (sticky, cleared
//                                       by reading +0x00; bits[31:1] reserved)
//   +0x08  error_input_low        RW   low  32 bits of nv_pid_top.error[63:0]
//   +0x0C  error_input_high       RW   high 32 bits of nv_pid_top.error[63:0]
//   +0x10  u_ai_input             RW   nv_pid_top.u_AI_in[31:0] (Q16.16)
//
// NOTES:
//   - Address decode uses S_AXI_AWADDR[4:2] / S_AXI_ARADDR[4:2]; bits above
//     [4] are ignored, so the slave occupies a 0x20-byte window. Wire it
//     into the FIC_0 AXI interconnect at any 0x20-byte-aligned base.
//   - Reset is active-low (S_AXI_ARESETN), per AXI4-Lite spec.
//   - Writes to RO addresses (0x00, 0x04) return SLVERR. Reads from
//     reserved offsets return zero with OKAY.
//   - The actuator_capture register's "valid" bit is sticky-set on each
//     strobe; reading +0x00 clears it. This gives firmware a poll-and-ack
//     pattern for catching every actuator update.
//
// PHASE II TODO:
//   - Wire S_AXI_* into the FIC_0 AXI interconnect via SmartDesign at a
//     dedicated address slot. For Phase I this slave is instantiated at
//     the toplevel and its master-side AXI signals are tapped from
//     non-constant MSS GPIO_M2F bits (test stimulus only) — sufficient to
//     defeat Synplify constant-folding so the PID datapath survives
//     synthesis at full bit-width and full functionality.

module pid_io_block (
    // AXI4-Lite slave interface ---------------------------------------------
    input  wire        S_AXI_ACLK,
    input  wire        S_AXI_ARESETN,

    // Write address channel
    input  wire [11:0] S_AXI_AWADDR,
    input  wire [2:0]  S_AXI_AWPROT,
    input  wire        S_AXI_AWVALID,
    output reg         S_AXI_AWREADY,

    // Write data channel
    input  wire [31:0] S_AXI_WDATA,
    input  wire [3:0]  S_AXI_WSTRB,
    input  wire        S_AXI_WVALID,
    output reg         S_AXI_WREADY,

    // Write response channel
    output reg  [1:0]  S_AXI_BRESP,
    output reg         S_AXI_BVALID,
    input  wire        S_AXI_BREADY,

    // Read address channel
    input  wire [11:0] S_AXI_ARADDR,
    input  wire [2:0]  S_AXI_ARPROT,
    input  wire        S_AXI_ARVALID,
    output reg         S_AXI_ARREADY,

    // Read data channel
    output reg  [31:0] S_AXI_RDATA,
    output reg  [1:0]  S_AXI_RRESP,
    output reg         S_AXI_RVALID,
    input  wire        S_AXI_RREADY,

    // Connections to nv_pid_top ---------------------------------------------
    output wire [63:0] error_out,                  // -> nv_pid_top.error
    output wire [31:0] u_ai_out,                   // -> nv_pid_top.u_AI_in
    input  wire [31:0] actuator_capture_in,        // <- nv_pid_top.actuator_out_write_data
    input  wire        actuator_capture_strobe     // <- nv_pid_top.actuator_out_write_en
);

    // -- AXI response codes (AXI4 Specification Table A3.4) -----------------
    localparam [1:0] RESP_OKAY   = 2'b00;
    localparam [1:0] RESP_SLVERR = 2'b10;

    // -- Register storage ---------------------------------------------------
    reg [31:0] error_low_reg;
    reg [31:0] error_high_reg;
    reg [31:0] u_ai_in_reg;
    reg [31:0] actuator_capture_reg;
    reg        capture_valid;

    assign error_out = {error_high_reg, error_low_reg};
    assign u_ai_out  = u_ai_in_reg;

    // -- Latched address / data for split-channel handling ------------------
    reg [11:0] awaddr_latched;
    reg [31:0] wdata_latched;
    reg [3:0]  wstrb_latched;
    reg        aw_latched;
    reg        w_latched;
    wire       aw_done = aw_latched | (S_AXI_AWVALID & S_AXI_AWREADY);
    wire       w_done  = w_latched  | (S_AXI_WVALID  & S_AXI_WREADY);

    // -- Actuator capture (always-on, independent of AXI traffic) -----------
    // Strobe-driven sample of actuator_out_write_data. Sticky valid bit;
    // reading +0x00 over AXI clears it (see read FSM below).
    reg actuator_capture_clear;
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            actuator_capture_reg <= 32'h0;
            capture_valid        <= 1'b0;
        end else begin
            if (actuator_capture_strobe) begin
                actuator_capture_reg <= actuator_capture_in;
                capture_valid        <= 1'b1;
            end else if (actuator_capture_clear) begin
                capture_valid        <= 1'b0;
            end
        end
    end

    // -- Write FSM ----------------------------------------------------------
    // Accept AW + W (in either order), apply on next cycle when both done.
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_AWREADY  <= 1'b0;
            S_AXI_WREADY   <= 1'b0;
            S_AXI_BVALID   <= 1'b0;
            S_AXI_BRESP    <= RESP_OKAY;
            aw_latched     <= 1'b0;
            w_latched      <= 1'b0;
            awaddr_latched <= 12'h0;
            wdata_latched  <= 32'h0;
            wstrb_latched  <= 4'h0;
            error_low_reg  <= 32'h0;
            error_high_reg <= 32'h0;
            u_ai_in_reg    <= 32'h0;
        end else begin
            // Default ready strobes: assert when not yet latched.
            S_AXI_AWREADY <= ~aw_latched & ~S_AXI_BVALID;
            S_AXI_WREADY  <= ~w_latched  & ~S_AXI_BVALID;

            // Latch AW
            if (S_AXI_AWVALID & S_AXI_AWREADY) begin
                awaddr_latched <= S_AXI_AWADDR;
                aw_latched     <= 1'b1;
            end
            // Latch W
            if (S_AXI_WVALID & S_AXI_WREADY) begin
                wdata_latched <= S_AXI_WDATA;
                wstrb_latched <= S_AXI_WSTRB;
                w_latched     <= 1'b1;
            end

            // Apply when both channels have been seen
            if (aw_done & w_done & ~S_AXI_BVALID) begin
                case (awaddr_latched[4:2])
                    3'd0, 3'd1: begin
                        // Writes to RO regs return SLVERR
                        S_AXI_BRESP <= RESP_SLVERR;
                    end
                    3'd2: begin // 0x08 error_low
                        if (wstrb_latched[0]) error_low_reg[7:0]   <= wdata_latched[7:0];
                        if (wstrb_latched[1]) error_low_reg[15:8]  <= wdata_latched[15:8];
                        if (wstrb_latched[2]) error_low_reg[23:16] <= wdata_latched[23:16];
                        if (wstrb_latched[3]) error_low_reg[31:24] <= wdata_latched[31:24];
                        S_AXI_BRESP <= RESP_OKAY;
                    end
                    3'd3: begin // 0x0C error_high
                        if (wstrb_latched[0]) error_high_reg[7:0]   <= wdata_latched[7:0];
                        if (wstrb_latched[1]) error_high_reg[15:8]  <= wdata_latched[15:8];
                        if (wstrb_latched[2]) error_high_reg[23:16] <= wdata_latched[23:16];
                        if (wstrb_latched[3]) error_high_reg[31:24] <= wdata_latched[31:24];
                        S_AXI_BRESP <= RESP_OKAY;
                    end
                    3'd4: begin // 0x10 u_ai_input
                        if (wstrb_latched[0]) u_ai_in_reg[7:0]   <= wdata_latched[7:0];
                        if (wstrb_latched[1]) u_ai_in_reg[15:8]  <= wdata_latched[15:8];
                        if (wstrb_latched[2]) u_ai_in_reg[23:16] <= wdata_latched[23:16];
                        if (wstrb_latched[3]) u_ai_in_reg[31:24] <= wdata_latched[31:24];
                        S_AXI_BRESP <= RESP_OKAY;
                    end
                    default: S_AXI_BRESP <= RESP_OKAY; // reserved offsets: tolerate
                endcase
                S_AXI_BVALID  <= 1'b1;
                aw_latched    <= 1'b0;
                w_latched     <= 1'b0;
                S_AXI_AWREADY <= 1'b0;
                S_AXI_WREADY  <= 1'b0;
            end

            // Complete the write response handshake
            if (S_AXI_BVALID & S_AXI_BREADY) begin
                S_AXI_BVALID <= 1'b0;
            end
        end
    end

    // -- Read FSM -----------------------------------------------------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_ARREADY          <= 1'b0;
            S_AXI_RVALID           <= 1'b0;
            S_AXI_RDATA            <= 32'h0;
            S_AXI_RRESP            <= RESP_OKAY;
            actuator_capture_clear <= 1'b0;
        end else begin
            actuator_capture_clear <= 1'b0;

            // Default: ready when no read in flight
            S_AXI_ARREADY <= ~S_AXI_RVALID;

            if (S_AXI_ARVALID & S_AXI_ARREADY) begin
                case (S_AXI_ARADDR[4:2])
                    3'd0: begin // 0x00 actuator_out_capture
                        S_AXI_RDATA            <= actuator_capture_reg;
                        actuator_capture_clear <= 1'b1; // clear sticky valid
                    end
                    3'd1: begin // 0x04 actuator_out_status
                        S_AXI_RDATA <= {31'h0, capture_valid};
                    end
                    3'd2: begin // 0x08 error_low
                        S_AXI_RDATA <= error_low_reg;
                    end
                    3'd3: begin // 0x0C error_high
                        S_AXI_RDATA <= error_high_reg;
                    end
                    3'd4: begin // 0x10 u_ai_input
                        S_AXI_RDATA <= u_ai_in_reg;
                    end
                    default: begin
                        S_AXI_RDATA <= 32'h0;
                    end
                endcase
                S_AXI_RRESP   <= RESP_OKAY;
                S_AXI_RVALID  <= 1'b1;
                S_AXI_ARREADY <= 1'b0;
            end

            if (S_AXI_RVALID & S_AXI_RREADY) begin
                S_AXI_RVALID <= 1'b0;
            end
        end
    end

endmodule
