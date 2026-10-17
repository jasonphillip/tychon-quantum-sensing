`timescale 1ns/1ps
// Register bank and synchronous HLS input memories. One operation at a time.
module quantum_demo_regs(
    input wire clk, input wire reset,
    input wire wr_en, input wire [11:0] wr_addr, input wire [31:0] wr_data,
    output reg wr_error,
    input wire [11:0] rd_addr, output reg [31:0] rd_data, output reg rd_error
);
    localparam ID = 32'h51465047; // QFPG
    reg [1:0] selected_core, active_core;
    reg [7:0] syndrome;
    reg [31:0] timeout_limit, cycles, completed_count, error_code;
    reg busy, done, score_valid;
    reg [63:0] result_value, score_value;
    reg [31:0] input_words [0:63];
    reg [63:0] input_valid;
    reg core_reset, ro_start, nv_start, qec_start;
    wire ro_ready, ro_finish, nv_ready, nv_finish, qec_ready, qec_finish;
    wire [63:0] ro_result, nv_score;
    wire [15:0] nv_result;
    wire [31:0] qec_result;
    wire nv_score_en;
    wire ro_clken, ro_re_a, ro_re_b, nv_clken, nv_re_a, nv_re_b;
    wire [6:0] ro_addr_a, ro_addr_b, nv_addr_a, nv_addr_b;
    reg [15:0] ro_data_a, ro_data_b, nv_data_a, nv_data_b;
    wire all_inputs_valid = &input_valid;
    wire reset_cores = reset | core_reset;
    wire selected_ready = (selected_core == 1) ? ro_ready :
                          (selected_core == 2) ? nv_ready :
                          (selected_core == 3) ? qec_ready : 1'b0;
    wire active_finish = (active_core == 1) ? ro_finish :
                         (active_core == 2) ? nv_finish :
                         (active_core == 3) ? qec_finish : 1'b0;
    wire input_write = (wr_addr >= 12'h100 && wr_addr <= 12'h1fc);
    wire input_read = (rd_addr >= 12'h100 && rd_addr <= 12'h1fc);

    readout_top_top readout_core(
        .clk(clk), .reset(reset_cores), .start(ro_start), .ready(ro_ready),
        .finish(ro_finish), .return_val(ro_result), .input_var_clken(ro_clken),
        .input_var_read_en_a(ro_re_a), .input_var_address_a(ro_addr_a), .input_var_read_data_a(ro_data_a),
        .input_var_read_en_b(ro_re_b), .input_var_address_b(ro_addr_b), .input_var_read_data_b(ro_data_b));
    nv_template_top_top nv_core(
        .clk(clk), .reset(reset_cores), .start(nv_start), .ready(nv_ready),
        .finish(nv_finish), .return_val(nv_result), .input_var_clken(nv_clken),
        .input_var_read_en_a(nv_re_a), .input_var_address_a(nv_addr_a), .input_var_read_data_a(nv_data_a),
        .input_var_read_en_b(nv_re_b), .input_var_address_b(nv_addr_b), .input_var_read_data_b(nv_data_b),
        .score_write_en(nv_score_en), .score_write_data(nv_score));
    qec_top_top qec_core(
        .clk(clk), .reset(reset_cores), .start(qec_start), .ready(qec_ready),
        .finish(qec_finish), .return_val(qec_result), .syndrome(syndrome));

    // Each HLS address selects a 16-bit element, not a byte offset.
    // Clock-enabled registered reads implement the required one-cycle RAM.
    always @(posedge clk) begin
        if (reset) begin
            ro_data_a <= 0; ro_data_b <= 0; nv_data_a <= 0; nv_data_b <= 0;
        end else begin
            if (ro_clken && ro_re_a)
                ro_data_a <= ro_addr_a[0] ? input_words[ro_addr_a[6:1]][31:16] : input_words[ro_addr_a[6:1]][15:0];
            if (ro_clken && ro_re_b)
                ro_data_b <= ro_addr_b[0] ? input_words[ro_addr_b[6:1]][31:16] : input_words[ro_addr_b[6:1]][15:0];
            if (nv_clken && nv_re_a)
                nv_data_a <= nv_addr_a[0] ? input_words[nv_addr_a[6:1]][31:16] : input_words[nv_addr_a[6:1]][15:0];
            if (nv_clken && nv_re_b)
                nv_data_b <= nv_addr_b[0] ? input_words[nv_addr_b[6:1]][31:16] : input_words[nv_addr_b[6:1]][15:0];
        end
    end

    always @* begin
        wr_error = 1'b0;
        if (wr_addr[1:0] != 0) wr_error = 1'b1;
        else if (input_write) wr_error = busy;
        else case (wr_addr)
            12'h008: begin
                if (wr_data != 1 && wr_data != 2 && wr_data != 4) wr_error = 1'b1;
                else if (wr_data == 1)
                    wr_error = busy || core_reset || !selected_ready ||
                               ((selected_core != 3) && !all_inputs_valid);
                else if (wr_data == 4) wr_error = busy;
            end
            12'h010: wr_error = busy || (wr_data < 1) || (wr_data > 3);
            12'h014: wr_error = busy || (wr_data > 255);
            12'h018: wr_error = busy || (wr_data == 0);
            default: wr_error = 1'b1;
        endcase
    end

    always @* begin
        rd_data = 0; rd_error = 0;
        if (rd_addr[1:0] != 0) rd_error = 1;
        else if (input_read)
            rd_data = input_valid[rd_addr[7:2]] ? input_words[rd_addr[7:2]] : 32'd0;
        else case (rd_addr)
            12'h000: rd_data = ID;
            12'h004: rd_data = 32'h00010000;
            12'h008: rd_data = 0;
            12'h00c: rd_data = {28'd0, all_inputs_valid, (error_code != 0), done, busy};
            12'h010: rd_data = {30'd0, selected_core};
            12'h014: rd_data = {24'd0, syndrome};
            12'h018: rd_data = timeout_limit;
            12'h01c: rd_data = cycles;
            12'h020: rd_data = result_value[31:0];
            12'h024: rd_data = result_value[63:32];
            12'h028: rd_data = score_value[31:0];
            12'h02c: rd_data = score_value[63:32];
            12'h030: rd_data = completed_count;
            12'h034: rd_data = error_code;
            default: rd_error = 1;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            selected_core <= 0; active_core <= 0; syndrome <= 0;
            timeout_limit <= 1000000; cycles <= 0; completed_count <= 0;
            error_code <= 0; busy <= 0; done <= 0; score_valid <= 0;
            result_value <= 0; score_value <= 0; input_valid <= 0;
            core_reset <= 0; ro_start <= 0; nv_start <= 0; qec_start <= 0;
        end else begin
            ro_start <= 0; nv_start <= 0; qec_start <= 0; core_reset <= 0;
            if (busy) begin
                cycles <= cycles + 1;
                if (active_core == 2 && nv_score_en) begin
                    score_value <= nv_score;
                    score_valid <= 1;
                end
                if (active_finish) begin
                    busy <= 0; done <= 1; completed_count <= completed_count + 1;
                    case (active_core)
                        1: result_value <= ro_result;
                        2: begin
                            result_value <= {48'd0, nv_result};
                            if (!score_valid && !nv_score_en) error_code <= 3;
                        end
                        3: result_value <= {32'd0, qec_result};
                        default: error_code <= 4;
                    endcase
                end else if (cycles >= timeout_limit - 1) begin
                    busy <= 0; done <= 1; error_code <= 1; core_reset <= 1;
                    result_value <= 0; score_value <= 0; score_valid <= 0;
                    completed_count <= completed_count + 1;
                end
            end
            if (wr_en && !wr_error) begin
                if (input_write) begin
                    input_words[wr_addr[7:2]] <= wr_data;
                    input_valid[wr_addr[7:2]] <= 1;
                end else case (wr_addr)
                    12'h008: begin
                        if (wr_data == 1) begin
                            busy <= 1; done <= 0; error_code <= 0; cycles <= 0;
                            active_core <= selected_core; result_value <= 0;
                            score_value <= 0; score_valid <= 0;
                            ro_start <= selected_core == 1;
                            nv_start <= selected_core == 2;
                            qec_start <= selected_core == 3;
                        end else if (wr_data == 2) begin
                            core_reset <= 1;
                            if (busy) begin
                                busy <= 0; done <= 1; error_code <= 2;
                                completed_count <= completed_count + 1;
                                result_value <= 0; score_value <= 0; score_valid <= 0;
                            end
                        end else begin
                            done <= 0; error_code <= 0;
                            result_value <= 0; score_value <= 0; score_valid <= 0;
                        end
                    end
                    12'h010: selected_core <= wr_data[1:0];
                    12'h014: syndrome <= wr_data[7:0];
                    12'h018: timeout_limit <= wr_data;
                    default: begin end
                endcase
            end
        end
    end
endmodule
