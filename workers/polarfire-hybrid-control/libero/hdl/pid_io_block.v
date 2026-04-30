// pid_io_block.v
//
// AXI4-Lite slave that exposes the nv_pid_top I/O + observability registers
// needed to (a) defeat Synplify constant-folding of the PID datapath at
// synthesis time and (b) provide an MSS-writable test-input + actuator-readback
// + coefficient-shadow + status register block for HITL firmware.
//
// REGISTER MAP (byte offsets, all 32-bit aligned):
//   ---- I/O test stimulus (Phase I synthesis-defeat anchors) ----
//   +0x00  actuator_out_capture       RO  captured actuator_out_write_data on
//                                          rising edge of actuator_out_write_en
//                                          (Q16.16 fixed-point, sign-extended)
//   +0x04  actuator_out_status        RO  bit[0] = capture_valid (sticky,
//                                          cleared by reading +0x00)
//   +0x08  error_input_low            RW  low  32 bits of nv_pid_top.error[63:0]
//   +0x0C  error_input_high           RW  high 32 bits of nv_pid_top.error[63:0]
//   +0x10  u_ai_input                 RW  nv_pid_top.u_AI_in[31:0] (Q16.16)
//   +0x14  axi_write_count            RO  monotonic count of accepted writes;
//                                          proves slave is alive in audit
//   +0x18  reserved                   --  reads zero
//   +0x1C  reserved                   --  reads zero
//
//   ---- Coefficient shadow registers (P2 observability) ----
//   The MSS firmware mirrors writes to nv_pid_top's SmartHLS-generated
//   axi_target slave AND these shadow registers. The shadows give a
//   second readback authority and keep the audit surface non-pruned.
//   +0x20  Kp_shadow                  RW  Q16.16 fixed-point coefficient mirror
//   +0x24  Ki_shadow                  RW  Q16.16
//   +0x28  Kd_shadow                  RW  Q16.16
//   +0x2C  out_min_shadow             RW  Q16.16 actuator min
//   +0x30  out_max_shadow             RW  Q16.16 actuator max
//   +0x34  inner_clamp_setpoint_shdw  RW  fraction of actuator range
//   +0x38  reserved                   --  reads zero
//   +0x3C  reserved                   --  reads zero
//
//   ---- Status CSRs (P2 observability) ----
//   +0x40  watchdog_timeout_flag      RO  bit[0] = current timeout level;
//                                          bits[31:1] reserved
//   +0x44  watchdog_timeout_events    RO  cumulative count of timeout
//                                          rising edges (clears on reset only)
//   +0x48  saturation_status          RO  bit[0]=current sat flag (placeholder
//                                          until HLS exposes it; tied to a
//                                          structural witness so audit doesn't
//                                          prune the path), bits[31:1]=count
//   +0x4C  ai_active_flag             RO  bit[0]=ai_active_in (placeholder)
//   +0x50  cooldown_counter           RO  Phase I placeholder — driven by
//                                          cooldown_counter_in port
//   +0x54  pre_clamp_output_low       RO  Q16.16 [31:0] of pre-clamp PID output
//                                          (placeholder; tied to write_count
//                                          until HLS exposes it)
//   +0x58  post_clamp_output_low      RO  Q16.16 [31:0] of post-clamp output
//                                          (placeholder)
//   +0x5C  integrator_state_low       RO  Q16.16 [31:0] of integrator state
//                                          (placeholder)
//   +0x60-+0x7C reserved              --  reads zero
//
// CORPUS RULES ENFORCED:
//   - WSTRB partial-byte writes are undefined per CoreVectorBlox HB0919 p.12.
//     We reject any write whose wstrb != 4'hF with RESP_SLVERR (full-width
//     writes only). Audit gate `--require-wstrb-full` checks for this.
//   - Address window is 0x80 bytes, 7-bit decode (AWADDR/ARADDR[6:2]).
//
// PHASE II TODO:
//   - Wire S_AXI_* into the FIC_0 AXI interconnect via SmartDesign at a
//     dedicated address slot. See libero/scripts/patch_smartdesign_pid_axi.py.
//   - Replace placeholder ports (saturation_in, ai_active_in,
//     cooldown_counter_in, pre/post-clamp/integrator) with bare-wire outputs
//     from nv_pid_top once the HLS surface exposes them. The MSS driver
//     contract is already documented above.

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
    input  wire        actuator_capture_strobe,    // <- nv_pid_top.actuator_out_write_en

    // Coefficient shadows: drive nothing today (observability only); a Phase II
    // patch can route them to nv_pid_top inputs in parallel with the SmartHLS
    // slave so both are programmed atomically by firmware.
    output wire [31:0] kp_shadow_out,
    output wire [31:0] ki_shadow_out,
    output wire [31:0] kd_shadow_out,
    output wire [31:0] out_min_shadow_out,
    output wire [31:0] out_max_shadow_out,
    output wire [31:0] inner_clamp_shadow_out,

    // Watchdog / status inputs from nv_pid_top + watchdog_timer. Each input
    // line is a structural witness — audit `--require-status-csrs` confirms
    // these nets reach the slave readback path.
    input  wire        watchdog_timeout_in,        // <- watchdog_timer.timeout
    input  wire        saturation_in,              // <- nv_pid_top (placeholder)
    input  wire        ai_active_in,               // <- nv_pid_top (placeholder)
    input  wire [31:0] cooldown_counter_in,        // <- nv_pid_top (placeholder)
    input  wire [31:0] pre_clamp_output_in,        // <- nv_pid_top (placeholder)
    input  wire [31:0] post_clamp_output_in,       // <- nv_pid_top (placeholder)
    input  wire [31:0] integrator_state_in         // <- nv_pid_top (placeholder)
);

    // -- AXI response codes (AXI4 Specification Table A3.4) -----------------
    localparam [1:0] RESP_OKAY   = 2'b00;
    localparam [1:0] RESP_SLVERR = 2'b10;

    // -- Address decode helpers --------------------------------------------
    // 5-bit decode covers offsets 0x00..0x7C (32 word slots).
    localparam [4:0] OFF_ACTUATOR_CAP    = 5'h00;  // 0x00
    localparam [4:0] OFF_ACTUATOR_STAT   = 5'h01;  // 0x04
    localparam [4:0] OFF_ERROR_LOW       = 5'h02;  // 0x08
    localparam [4:0] OFF_ERROR_HIGH      = 5'h03;  // 0x0C
    localparam [4:0] OFF_U_AI_IN         = 5'h04;  // 0x10
    localparam [4:0] OFF_AXI_WRITE_COUNT = 5'h05;  // 0x14
    localparam [4:0] OFF_KP              = 5'h08;  // 0x20
    localparam [4:0] OFF_KI              = 5'h09;  // 0x24
    localparam [4:0] OFF_KD              = 5'h0A;  // 0x28
    localparam [4:0] OFF_OUT_MIN         = 5'h0B;  // 0x2C
    localparam [4:0] OFF_OUT_MAX         = 5'h0C;  // 0x30
    localparam [4:0] OFF_INNER_CLAMP     = 5'h0D;  // 0x34
    localparam [4:0] OFF_WD_FLAG         = 5'h10;  // 0x40
    localparam [4:0] OFF_WD_EVENTS       = 5'h11;  // 0x44
    localparam [4:0] OFF_SAT_STATUS      = 5'h12;  // 0x48
    localparam [4:0] OFF_AI_ACTIVE       = 5'h13;  // 0x4C
    localparam [4:0] OFF_COOLDOWN        = 5'h14;  // 0x50
    localparam [4:0] OFF_PRE_CLAMP       = 5'h15;  // 0x54
    localparam [4:0] OFF_POST_CLAMP      = 5'h16;  // 0x58
    localparam [4:0] OFF_INTEGRATOR      = 5'h17;  // 0x5C

    // -- RW register storage ------------------------------------------------
    reg [31:0] error_low_reg;
    reg [31:0] error_high_reg;
    reg [31:0] u_ai_in_reg;
    reg [31:0] kp_reg;
    reg [31:0] ki_reg;
    reg [31:0] kd_reg;
    reg [31:0] out_min_reg;
    reg [31:0] out_max_reg;
    reg [31:0] inner_clamp_reg;

    // -- RO storage / counters ---------------------------------------------
    reg [31:0] actuator_capture_reg;
    reg        capture_valid;
    reg [31:0] axi_write_count_reg;
    reg [30:0] watchdog_timeout_event_count;
    reg        watchdog_timeout_d;
    reg [30:0] saturation_event_count;
    reg        saturation_d;

    assign error_out             = {error_high_reg, error_low_reg};
    assign u_ai_out              = u_ai_in_reg;
    assign kp_shadow_out         = kp_reg;
    assign ki_shadow_out         = ki_reg;
    assign kd_shadow_out         = kd_reg;
    assign out_min_shadow_out    = out_min_reg;
    assign out_max_shadow_out    = out_max_reg;
    assign inner_clamp_shadow_out = inner_clamp_reg;

    // -- Latched address / data for split-channel handling ------------------
    reg [11:0] awaddr_latched;
    reg [31:0] wdata_latched;
    reg [3:0]  wstrb_latched;
    reg        aw_latched;
    reg        w_latched;
    wire       aw_done = aw_latched | (S_AXI_AWVALID & S_AXI_AWREADY);
    wire       w_done  = w_latched  | (S_AXI_WVALID  & S_AXI_WREADY);
    wire [4:0] wr_off  = awaddr_latched[6:2];
    wire       wstrb_full = (wstrb_latched == 4'hF);

    // -- Actuator capture (always-on, independent of AXI traffic) -----------
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

    // -- Watchdog timeout edge counter (always-on observability) ------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            watchdog_timeout_event_count <= 31'h0;
            watchdog_timeout_d           <= 1'b0;
        end else begin
            watchdog_timeout_d <= watchdog_timeout_in;
            if (watchdog_timeout_in & ~watchdog_timeout_d) begin
                watchdog_timeout_event_count <= watchdog_timeout_event_count + 1'b1;
            end
        end
    end

    // -- Saturation edge counter (always-on observability) ------------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            saturation_event_count <= 31'h0;
            saturation_d           <= 1'b0;
        end else begin
            saturation_d <= saturation_in;
            if (saturation_in & ~saturation_d) begin
                saturation_event_count <= saturation_event_count + 1'b1;
            end
        end
    end

    // -- Write FSM ----------------------------------------------------------
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            S_AXI_AWREADY       <= 1'b0;
            S_AXI_WREADY        <= 1'b0;
            S_AXI_BVALID        <= 1'b0;
            S_AXI_BRESP         <= RESP_OKAY;
            aw_latched          <= 1'b0;
            w_latched           <= 1'b0;
            awaddr_latched      <= 12'h0;
            wdata_latched       <= 32'h0;
            wstrb_latched       <= 4'h0;
            error_low_reg       <= 32'h0;
            error_high_reg      <= 32'h0;
            u_ai_in_reg         <= 32'h0;
            kp_reg              <= 32'h0;
            ki_reg              <= 32'h0;
            kd_reg              <= 32'h0;
            out_min_reg         <= 32'h0;
            out_max_reg         <= 32'h0;
            inner_clamp_reg     <= 32'h0;
            axi_write_count_reg <= 32'h0;
        end else begin
            // Default ready strobes: assert when not yet latched and no
            // outstanding response.
            S_AXI_AWREADY <= ~aw_latched & ~S_AXI_BVALID;
            S_AXI_WREADY  <= ~w_latched  & ~S_AXI_BVALID;

            if (S_AXI_AWVALID & S_AXI_AWREADY) begin
                awaddr_latched <= S_AXI_AWADDR;
                aw_latched     <= 1'b1;
            end
            if (S_AXI_WVALID & S_AXI_WREADY) begin
                wdata_latched <= S_AXI_WDATA;
                wstrb_latched <= S_AXI_WSTRB;
                w_latched     <= 1'b1;
            end

            if (aw_done & w_done & ~S_AXI_BVALID) begin
                if (!wstrb_full) begin
                    // Corpus rule (HB0919 p.12): partial-byte writes undefined.
                    S_AXI_BRESP <= RESP_SLVERR;
                end else begin
                    case (wr_off)
                        // -- I/O test stimulus --
                        OFF_ERROR_LOW: begin
                            error_low_reg       <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_ERROR_HIGH: begin
                            error_high_reg      <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_U_AI_IN: begin
                            u_ai_in_reg         <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        // -- Coefficient shadows --
                        OFF_KP: begin
                            kp_reg              <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_KI: begin
                            ki_reg              <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_KD: begin
                            kd_reg              <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_OUT_MIN: begin
                            out_min_reg         <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_OUT_MAX: begin
                            out_max_reg         <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        OFF_INNER_CLAMP: begin
                            inner_clamp_reg     <= wdata_latched;
                            axi_write_count_reg <= axi_write_count_reg + 1'b1;
                            S_AXI_BRESP         <= RESP_OKAY;
                        end
                        // RO regs: SLVERR
                        OFF_ACTUATOR_CAP, OFF_ACTUATOR_STAT, OFF_AXI_WRITE_COUNT,
                        OFF_WD_FLAG, OFF_WD_EVENTS, OFF_SAT_STATUS, OFF_AI_ACTIVE,
                        OFF_COOLDOWN, OFF_PRE_CLAMP, OFF_POST_CLAMP, OFF_INTEGRATOR: begin
                            S_AXI_BRESP <= RESP_SLVERR;
                        end
                        default: S_AXI_BRESP <= RESP_OKAY; // reserved offsets tolerated
                    endcase
                end
                S_AXI_BVALID  <= 1'b1;
                aw_latched    <= 1'b0;
                w_latched     <= 1'b0;
                S_AXI_AWREADY <= 1'b0;
                S_AXI_WREADY  <= 1'b0;
            end

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
            S_AXI_ARREADY          <= ~S_AXI_RVALID;

            if (S_AXI_ARVALID & S_AXI_ARREADY) begin
                case (S_AXI_ARADDR[6:2])
                    OFF_ACTUATOR_CAP: begin
                        S_AXI_RDATA            <= actuator_capture_reg;
                        actuator_capture_clear <= 1'b1;
                    end
                    OFF_ACTUATOR_STAT:   S_AXI_RDATA <= {31'h0, capture_valid};
                    OFF_ERROR_LOW:       S_AXI_RDATA <= error_low_reg;
                    OFF_ERROR_HIGH:      S_AXI_RDATA <= error_high_reg;
                    OFF_U_AI_IN:         S_AXI_RDATA <= u_ai_in_reg;
                    OFF_AXI_WRITE_COUNT: S_AXI_RDATA <= axi_write_count_reg;
                    OFF_KP:              S_AXI_RDATA <= kp_reg;
                    OFF_KI:              S_AXI_RDATA <= ki_reg;
                    OFF_KD:              S_AXI_RDATA <= kd_reg;
                    OFF_OUT_MIN:         S_AXI_RDATA <= out_min_reg;
                    OFF_OUT_MAX:         S_AXI_RDATA <= out_max_reg;
                    OFF_INNER_CLAMP:     S_AXI_RDATA <= inner_clamp_reg;
                    OFF_WD_FLAG:         S_AXI_RDATA <= {31'h0, watchdog_timeout_in};
                    OFF_WD_EVENTS:       S_AXI_RDATA <= {1'b0, watchdog_timeout_event_count};
                    OFF_SAT_STATUS:      S_AXI_RDATA <= {saturation_event_count, saturation_in};
                    OFF_AI_ACTIVE:       S_AXI_RDATA <= {31'h0, ai_active_in};
                    OFF_COOLDOWN:        S_AXI_RDATA <= cooldown_counter_in;
                    OFF_PRE_CLAMP:       S_AXI_RDATA <= pre_clamp_output_in;
                    OFF_POST_CLAMP:      S_AXI_RDATA <= post_clamp_output_in;
                    OFF_INTEGRATOR:      S_AXI_RDATA <= integrator_state_in;
                    default:             S_AXI_RDATA <= 32'h0;
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
