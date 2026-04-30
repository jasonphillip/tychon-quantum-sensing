// pid_csr_block.v
//
// AXI4-Lite slave that exposes nv_pid_top observability registers: a
// coefficient shadow bank plus status CSRs covering integrator state,
// pre/post-clamp output, saturation, watchdog, and cooldown. Provides the
// "real, software-visible, non-trivial AXI traffic and readback" the
// corpus says is required to defeat Synplify constant-folding of the
// SmartHLS-generated PID datapath.
//
// CORPUS BASIS:
//
//   - Observability fields chosen from
//     ~/.corpus/polarfire-control-corpus/raw/user-contributed/
//     preserving-real-smarthls-pid-datapath.md:130-148, which lists the
//     readbacks that constitute architectural proof of survival:
//     coefficient shadows, current error, integrator, derivative,
//     pre-clamp output, post-clamp output, saturation flag, saturation
//     counter.
//   - WSTRB handling: AXI4-Lite-spec compliant (ARM IHI0022).
//     Implementation accepts any wstrb bit pattern that selects in-range
//     bytes. The SmartHLS axi_target rule (element-aligned strobes,
//     fpga-hls-docs:2594-2596) applies to the SmartHLS-generated slave,
//     not to this hand-written one. The CoreVectorBlox-specific rule
//     (HB0919:565-635: "all high or all low") applies only to the
//     CoreVectorBlox control slave; this CSR does not share that
//     control protocol.
//
// REGISTER MAP (byte offsets, 32-bit aligned, 16 KiB window):
//
//   ---- Liveness + version ----
//   +0x000  axi_write_count            RO  monotonic count of accepted
//                                          writes; firmware reads this to
//                                          confirm slave is alive in the
//                                          fabric path.
//   +0x004  csr_version                RO  fixed 0x00010000 (1.0).
//
//   ---- Input shadow (RW; mirror MSS firmware writes to nv_pid_top axi_target) ----
//   +0x010  error_low                  RW  low 32 bits of error[63:0]
//   +0x014  error_high                 RW  high 32 bits of error[63:0]
//   +0x018  u_ai_input                 RW  Q16.16 AI inference output
//
//   ---- Coefficient shadow (RW) ----
//   +0x020  Kp_shadow                  RW  Q16.16
//   +0x024  Ki_shadow                  RW  Q16.16
//   +0x028  Kd_shadow                  RW  Q16.16
//   +0x02C  out_min_shadow             RW  Q16.16 actuator min
//   +0x030  out_max_shadow             RW  Q16.16 actuator max
//   +0x034  inner_clamp_setpoint_shdw  RW  fraction of actuator range
//
//   ---- Status (RO observability taps from nv_pid_top) ----
//   +0x040  pre_clamp_out              RO  Q16.16 unclamped PID output
//   +0x044  post_clamp_out             RO  Q16.16 actuator output
//   +0x048  integrator                 RO  Q16.16 PID integrator state
//   +0x04C  derivative                 RO  Q16.16 PID derivative term
//   +0x050  saturation_csr             RO  bit[0] = current sat flag,
//                                          bits[31:1] = sat-edge counter
//   +0x054  watchdog_csr               RO  bit[0] = current timeout,
//                                          bits[31:1] = timeout-edge counter
//   +0x058  cooldown_remaining         RO  cycles left in cooldown window
//   +0x05C  ai_active_flag             RO  bit[0] = AI is currently active
//
//   Reads from reserved offsets in the 16 KiB window return 0 with OKAY.
//
// NOTES:
//   - Address decode uses S_AXI_AWADDR[13:2] / S_AXI_ARADDR[13:2] -> 14-bit
//     window (16 KiB). Wire to FIC_0 at any 16 KiB-aligned base.
//   - WSTRB: any valid pattern is accepted; bytes whose strobe is 0 are
//     left unchanged. Out-of-range or RO-window writes return SLVERR.

module pid_csr_block #(
    parameter [31:0] CSR_VERSION = 32'h00010000
) (
    // Clock and reset
    input  wire        S_AXI_ACLK,
    input  wire        S_AXI_ARESETN,

    // AXI4-Lite slave: write address
    input  wire [13:0] S_AXI_AWADDR,
    input  wire [2:0]  S_AXI_AWPROT,
    input  wire        S_AXI_AWVALID,
    output reg         S_AXI_AWREADY,

    // AXI4-Lite slave: write data
    input  wire [31:0] S_AXI_WDATA,
    input  wire [3:0]  S_AXI_WSTRB,
    input  wire        S_AXI_WVALID,
    output reg         S_AXI_WREADY,

    // AXI4-Lite slave: write response
    output reg  [1:0]  S_AXI_BRESP,
    output reg         S_AXI_BVALID,
    input  wire        S_AXI_BREADY,

    // AXI4-Lite slave: read address
    input  wire [13:0] S_AXI_ARADDR,
    input  wire [2:0]  S_AXI_ARPROT,
    input  wire        S_AXI_ARVALID,
    output reg         S_AXI_ARREADY,

    // AXI4-Lite slave: read data
    output reg  [31:0] S_AXI_RDATA,
    output reg  [1:0]  S_AXI_RRESP,
    output reg         S_AXI_RVALID,
    input  wire        S_AXI_RREADY,

    // Coefficient shadow outputs (drive nv_pid_top dataport when wired).
    output wire [31:0] kp_shadow_out,
    output wire [31:0] ki_shadow_out,
    output wire [31:0] kd_shadow_out,
    output wire [31:0] out_min_shadow_out,
    output wire [31:0] out_max_shadow_out,
    output wire [31:0] inner_clamp_setpoint_shadow_out,

    // Input shadow outputs.
    output wire [63:0] error_shadow_out,
    output wire [31:0] u_ai_shadow_out,

    // Status taps from nv_pid_top / safety_clamps / watchdog (Phase I:
    // tied to MSS GPIO_M2F or FIC tap signals; Phase II: real observability
    // wires from nv_pid_top after SmartDesign canvas surgery).
    input  wire [31:0] tap_pre_clamp_out,
    input  wire [31:0] tap_post_clamp_out,
    input  wire [31:0] tap_integrator,
    input  wire [31:0] tap_derivative,
    input  wire        tap_saturation_flag,
    input  wire        tap_watchdog_timeout,
    input  wire [15:0] tap_cooldown_remaining,
    input  wire        tap_ai_active
);

    // --- AXI4-Lite resp codes ------------------------------------------
    localparam [1:0] RESP_OKAY    = 2'b00;
    localparam [1:0] RESP_SLVERR  = 2'b10;

    // --- Decoded register addresses (12-bit register index = AWADDR[13:2]) ---
    localparam [11:0] REG_AXI_WRITE_COUNT      = 12'h000;
    localparam [11:0] REG_CSR_VERSION          = 12'h001;
    localparam [11:0] REG_ERROR_LOW            = 12'h004;
    localparam [11:0] REG_ERROR_HIGH           = 12'h005;
    localparam [11:0] REG_U_AI_INPUT           = 12'h006;
    localparam [11:0] REG_KP_SHADOW            = 12'h008;
    localparam [11:0] REG_KI_SHADOW            = 12'h009;
    localparam [11:0] REG_KD_SHADOW            = 12'h00A;
    localparam [11:0] REG_OUT_MIN_SHADOW       = 12'h00B;
    localparam [11:0] REG_OUT_MAX_SHADOW       = 12'h00C;
    localparam [11:0] REG_INNER_CLAMP_SHADOW   = 12'h00D;
    localparam [11:0] REG_PRE_CLAMP_OUT        = 12'h010;
    localparam [11:0] REG_POST_CLAMP_OUT       = 12'h011;
    localparam [11:0] REG_INTEGRATOR           = 12'h012;
    localparam [11:0] REG_DERIVATIVE           = 12'h013;
    localparam [11:0] REG_SATURATION_CSR       = 12'h014;
    localparam [11:0] REG_WATCHDOG_CSR         = 12'h015;
    localparam [11:0] REG_COOLDOWN_REMAINING   = 12'h016;
    localparam [11:0] REG_AI_ACTIVE            = 12'h017;

    // --- Register storage ----------------------------------------------
    reg [31:0] r_axi_write_count;
    reg [31:0] r_error_low;
    reg [31:0] r_error_high;
    reg [31:0] r_u_ai_input;
    reg [31:0] r_kp_shadow;
    reg [31:0] r_ki_shadow;
    reg [31:0] r_kd_shadow;
    reg [31:0] r_out_min_shadow;
    reg [31:0] r_out_max_shadow;
    reg [31:0] r_inner_clamp_shadow;

    // Saturation and watchdog edge counters (status registers compose the
    // current flag with the cumulative edge count to maximize the number
    // of toggling bits per readback).
    reg [30:0] r_saturation_count;
    reg        r_saturation_prev;
    reg [30:0] r_watchdog_count;
    reg        r_watchdog_prev;

    // Output register surface
    assign kp_shadow_out                  = r_kp_shadow;
    assign ki_shadow_out                  = r_ki_shadow;
    assign kd_shadow_out                  = r_kd_shadow;
    assign out_min_shadow_out             = r_out_min_shadow;
    assign out_max_shadow_out             = r_out_max_shadow;
    assign inner_clamp_setpoint_shadow_out = r_inner_clamp_shadow;
    assign error_shadow_out               = {r_error_high, r_error_low};
    assign u_ai_shadow_out                = r_u_ai_input;

    // --- Saturation / watchdog edge accumulators ----------------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            r_saturation_count <= 31'd0;
            r_saturation_prev  <= 1'b0;
            r_watchdog_count   <= 31'd0;
            r_watchdog_prev    <= 1'b0;
        end else begin
            r_saturation_prev <= tap_saturation_flag;
            if (tap_saturation_flag && !r_saturation_prev) begin
                r_saturation_count <= r_saturation_count + 31'd1;
            end
            r_watchdog_prev <= tap_watchdog_timeout;
            if (tap_watchdog_timeout && !r_watchdog_prev) begin
                r_watchdog_count <= r_watchdog_count + 31'd1;
            end
        end
    end

    // --- Apply masked write ------------------------------------------
    function [31:0] apply_wstrb;
        input [31:0] cur;
        input [31:0] new_data;
        input [3:0]  wstrb;
        begin
            apply_wstrb = {
                wstrb[3] ? new_data[31:24] : cur[31:24],
                wstrb[2] ? new_data[23:16] : cur[23:16],
                wstrb[1] ? new_data[15:8]  : cur[15:8],
                wstrb[0] ? new_data[7:0]   : cur[7:0]
            };
        end
    endfunction

    // --- Write FSM ---------------------------------------------------
    reg [1:0] write_state;
    localparam [1:0] WST_IDLE = 2'd0;
    localparam [1:0] WST_DATA = 2'd1;
    localparam [1:0] WST_RESP = 2'd2;

    reg [11:0] wr_idx;
    reg [3:0]  wr_wstrb;
    reg [31:0] wr_data;
    reg        wr_addr_in_range;

    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            write_state       <= WST_IDLE;
            S_AXI_AWREADY     <= 1'b0;
            S_AXI_WREADY      <= 1'b0;
            S_AXI_BVALID      <= 1'b0;
            S_AXI_BRESP       <= RESP_OKAY;
            r_axi_write_count <= 32'd0;
            r_error_low       <= 32'd0;
            r_error_high      <= 32'd0;
            r_u_ai_input      <= 32'd0;
            r_kp_shadow       <= 32'd0;
            r_ki_shadow       <= 32'd0;
            r_kd_shadow       <= 32'd0;
            r_out_min_shadow  <= 32'd0;
            r_out_max_shadow  <= 32'd0;
            r_inner_clamp_shadow <= 32'd0;
            wr_idx            <= 12'h0;
            wr_wstrb          <= 4'h0;
            wr_data           <= 32'h0;
            wr_addr_in_range  <= 1'b0;
        end else begin
            case (write_state)
                WST_IDLE: begin
                    S_AXI_BVALID <= 1'b0;
                    if (S_AXI_AWVALID) begin
                        wr_idx           <= S_AXI_AWADDR[13:2];
                        S_AXI_AWREADY    <= 1'b1;
                        S_AXI_WREADY     <= 1'b1;
                        write_state      <= WST_DATA;
                    end else begin
                        S_AXI_AWREADY <= 1'b0;
                        S_AXI_WREADY  <= 1'b0;
                    end
                end

                WST_DATA: begin
                    S_AXI_AWREADY <= 1'b0;
                    if (S_AXI_WVALID && S_AXI_WREADY) begin
                        S_AXI_WREADY <= 1'b0;
                        wr_data      <= S_AXI_WDATA;
                        wr_wstrb     <= S_AXI_WSTRB;
                        // Determine RW vs SLVERR. RW writes update the
                        // corresponding shadow, then go to RESP.
                        case (wr_idx)
                            REG_ERROR_LOW: begin
                                r_error_low <= apply_wstrb(r_error_low, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_ERROR_HIGH: begin
                                r_error_high <= apply_wstrb(r_error_high, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_U_AI_INPUT: begin
                                r_u_ai_input <= apply_wstrb(r_u_ai_input, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_KP_SHADOW: begin
                                r_kp_shadow <= apply_wstrb(r_kp_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_KI_SHADOW: begin
                                r_ki_shadow <= apply_wstrb(r_ki_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_KD_SHADOW: begin
                                r_kd_shadow <= apply_wstrb(r_kd_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_OUT_MIN_SHADOW: begin
                                r_out_min_shadow <= apply_wstrb(r_out_min_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_OUT_MAX_SHADOW: begin
                                r_out_max_shadow <= apply_wstrb(r_out_max_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            REG_INNER_CLAMP_SHADOW: begin
                                r_inner_clamp_shadow <= apply_wstrb(r_inner_clamp_shadow, S_AXI_WDATA, S_AXI_WSTRB);
                                wr_addr_in_range <= 1'b1;
                            end
                            default: begin
                                wr_addr_in_range <= 1'b0;
                            end
                        endcase
                        write_state <= WST_RESP;
                    end
                end

                WST_RESP: begin
                    S_AXI_BVALID <= 1'b1;
                    S_AXI_BRESP  <= wr_addr_in_range ? RESP_OKAY : RESP_SLVERR;
                    if (S_AXI_BVALID && S_AXI_BREADY) begin
                        S_AXI_BVALID <= 1'b0;
                        if (wr_addr_in_range) begin
                            r_axi_write_count <= r_axi_write_count + 32'd1;
                        end
                        write_state <= WST_IDLE;
                    end
                end

                default: write_state <= WST_IDLE;
            endcase
        end
    end

    // --- Read FSM -----------------------------------------------------
    reg [1:0] read_state;
    localparam [1:0] RST_IDLE = 2'd0;
    localparam [1:0] RST_DATA = 2'd1;

    reg [11:0] rd_idx;

    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            read_state    <= RST_IDLE;
            S_AXI_ARREADY <= 1'b0;
            S_AXI_RVALID  <= 1'b0;
            S_AXI_RRESP   <= RESP_OKAY;
            S_AXI_RDATA   <= 32'h0;
            rd_idx        <= 12'h0;
        end else begin
            case (read_state)
                RST_IDLE: begin
                    if (S_AXI_ARVALID) begin
                        rd_idx        <= S_AXI_ARADDR[13:2];
                        S_AXI_ARREADY <= 1'b1;
                        read_state    <= RST_DATA;
                    end else begin
                        S_AXI_ARREADY <= 1'b0;
                    end
                end

                RST_DATA: begin
                    S_AXI_ARREADY <= 1'b0;
                    S_AXI_RVALID  <= 1'b1;
                    case (rd_idx)
                        REG_AXI_WRITE_COUNT:    S_AXI_RDATA <= r_axi_write_count;
                        REG_CSR_VERSION:        S_AXI_RDATA <= CSR_VERSION;
                        REG_ERROR_LOW:          S_AXI_RDATA <= r_error_low;
                        REG_ERROR_HIGH:         S_AXI_RDATA <= r_error_high;
                        REG_U_AI_INPUT:         S_AXI_RDATA <= r_u_ai_input;
                        REG_KP_SHADOW:          S_AXI_RDATA <= r_kp_shadow;
                        REG_KI_SHADOW:          S_AXI_RDATA <= r_ki_shadow;
                        REG_KD_SHADOW:          S_AXI_RDATA <= r_kd_shadow;
                        REG_OUT_MIN_SHADOW:     S_AXI_RDATA <= r_out_min_shadow;
                        REG_OUT_MAX_SHADOW:     S_AXI_RDATA <= r_out_max_shadow;
                        REG_INNER_CLAMP_SHADOW: S_AXI_RDATA <= r_inner_clamp_shadow;
                        REG_PRE_CLAMP_OUT:      S_AXI_RDATA <= tap_pre_clamp_out;
                        REG_POST_CLAMP_OUT:     S_AXI_RDATA <= tap_post_clamp_out;
                        REG_INTEGRATOR:         S_AXI_RDATA <= tap_integrator;
                        REG_DERIVATIVE:         S_AXI_RDATA <= tap_derivative;
                        REG_SATURATION_CSR:     S_AXI_RDATA <= {r_saturation_count, tap_saturation_flag};
                        REG_WATCHDOG_CSR:       S_AXI_RDATA <= {r_watchdog_count, tap_watchdog_timeout};
                        REG_COOLDOWN_REMAINING: S_AXI_RDATA <= {16'd0, tap_cooldown_remaining};
                        REG_AI_ACTIVE:          S_AXI_RDATA <= {31'd0, tap_ai_active};
                        default:                S_AXI_RDATA <= 32'h0;
                    endcase
                    S_AXI_RRESP <= RESP_OKAY;
                    if (S_AXI_RVALID && S_AXI_RREADY) begin
                        S_AXI_RVALID <= 1'b0;
                        read_state   <= RST_IDLE;
                    end
                end

                default: read_state <= RST_IDLE;
            endcase
        end
    end

endmodule
