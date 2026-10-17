`timescale 1ns/1ps
// AXI4 slave: 64-bit bus, aligned 32-bit single-beat register transactions.
// Unsupported read bursts return the requested number of SLVERR beats.
// Unsupported write bursts are drained without register side effects.
module quantum_demo_axi #(
    parameter ADDR_WIDTH = 38,
    parameter ID_WIDTH = 9,
    parameter [ADDR_WIDTH-1:0] BASE_ADDR = 38'h0060040000
)(
    input wire aclk, input wire aresetn,
    input wire [ID_WIDTH-1:0] s_axi_awid,
    input wire [ADDR_WIDTH-1:0] s_axi_awaddr,
    input wire [7:0] s_axi_awlen, input wire [2:0] s_axi_awsize,
    input wire [1:0] s_axi_awburst, input wire [1:0] s_axi_awlock,
    input wire [3:0] s_axi_awcache, input wire [2:0] s_axi_awprot,
    input wire [3:0] s_axi_awqos, input wire [3:0] s_axi_awregion, input wire s_axi_awuser,
    input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [63:0] s_axi_wdata, input wire [7:0] s_axi_wstrb,
    input wire s_axi_wlast, input wire s_axi_wuser, input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [ID_WIDTH-1:0] s_axi_bid, output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid, output wire s_axi_buser, input wire s_axi_bready,
    input wire [ID_WIDTH-1:0] s_axi_arid,
    input wire [ADDR_WIDTH-1:0] s_axi_araddr,
    input wire [7:0] s_axi_arlen, input wire [2:0] s_axi_arsize,
    input wire [1:0] s_axi_arburst, input wire [1:0] s_axi_arlock,
    input wire [3:0] s_axi_arcache, input wire [2:0] s_axi_arprot,
    input wire [3:0] s_axi_arqos, input wire [3:0] s_axi_arregion, input wire s_axi_aruser,
    input wire s_axi_arvalid, output wire s_axi_arready,
    output reg [ID_WIDTH-1:0] s_axi_rid, output reg [63:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp, output reg s_axi_rlast,
    output reg s_axi_rvalid, output wire s_axi_ruser, input wire s_axi_rready
);
    reg aw_pending, w_pending;
    reg [ID_WIDTH-1:0] aw_id;
    reg [ADDR_WIDTH-1:0] aw_addr;
    reg [7:0] aw_len, write_beat;
    reg aw_bad;
    reg [63:0] w_data;
    reg [7:0] w_strb;
    reg w_last;
    reg read_active, ar_bad;
    reg [ADDR_WIDTH-1:0] ar_addr;
    reg [ID_WIDTH-1:0] ar_id;
    reg [7:0] read_remaining;
    wire write_issue = aw_pending && w_pending && !s_axi_bvalid;
    wire lane_ok = aw_addr[2] ? (w_strb == 8'hf0) : (w_strb == 8'h0f);
    wire single_write_ok = !aw_bad && aw_len == 0 && write_beat == 0 && w_last && lane_ok;
    wire reg_wr = write_issue && single_write_ok;
    wire reg_wr_error, reg_rd_error;
    wire [31:0] reg_rd_data;
    wire [31:0] reg_wr_data = aw_addr[2] ? w_data[63:32] : w_data[31:0];
    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !read_active && !s_axi_rvalid;
    assign s_axi_buser = 1'b0;
    assign s_axi_ruser = 1'b0;

    quantum_demo_regs regs(
        .clk(aclk), .reset(!aresetn), .wr_en(reg_wr), .wr_addr(aw_addr[11:0]),
        .wr_data(reg_wr_data), .wr_error(reg_wr_error),
        .rd_addr(ar_addr[11:0]), .rd_data(reg_rd_data), .rd_error(reg_rd_error));

    always @(posedge aclk) begin
        if (!aresetn) begin
            aw_pending <= 0; w_pending <= 0; aw_id <= 0; aw_addr <= 0;
            aw_len <= 0; write_beat <= 0; aw_bad <= 0;
            w_data <= 0; w_strb <= 0; w_last <= 0;
            s_axi_bid <= 0; s_axi_bresp <= 0; s_axi_bvalid <= 0;
            read_active <= 0; ar_bad <= 0; ar_addr <= 0; ar_id <= 0; read_remaining <= 0;
            s_axi_rid <= 0; s_axi_rdata <= 0; s_axi_rresp <= 0; s_axi_rlast <= 0; s_axi_rvalid <= 0;
        end else begin
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (s_axi_awvalid && s_axi_awready) begin
                aw_pending <= 1; aw_id <= s_axi_awid; aw_addr <= s_axi_awaddr;
                aw_len <= s_axi_awlen; write_beat <= 0;
                aw_bad <= (s_axi_awlen != 0) || (s_axi_awsize != 2) ||
                          (s_axi_awburst > 1) || (|s_axi_awlock) || (s_axi_awaddr[1:0] != 0) ||
                          (s_axi_awaddr[ADDR_WIDTH-1:12] != BASE_ADDR[ADDR_WIDTH-1:12]);
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_pending <= 1; w_data <= s_axi_wdata;
                w_strb <= s_axi_wstrb; w_last <= s_axi_wlast;
            end
            if (write_issue) begin
                w_pending <= 0;
                if (write_beat == aw_len || w_last) begin
                    aw_pending <= 0; s_axi_bvalid <= 1; s_axi_bid <= aw_id;
                    s_axi_bresp <= (single_write_ok && !reg_wr_error) ? 2'b00 : 2'b10;
                end else begin
                    write_beat <= write_beat + 1;
                end
            end

            if (s_axi_arvalid && s_axi_arready) begin
                read_active <= 1; ar_addr <= s_axi_araddr; ar_id <= s_axi_arid;
                read_remaining <= s_axi_arlen;
                ar_bad <= (s_axi_arlen != 0) || (s_axi_arsize != 2) ||
                          (s_axi_arburst > 1) || (|s_axi_arlock) || (s_axi_araddr[1:0] != 0) ||
                          (s_axi_araddr[ADDR_WIDTH-1:12] != BASE_ADDR[ADDR_WIDTH-1:12]);
            end
            if (read_active && !s_axi_rvalid) begin
                s_axi_rvalid <= 1; s_axi_rid <= ar_id; s_axi_rlast <= read_remaining == 0;
                s_axi_rresp <= (ar_bad || reg_rd_error) ? 2'b10 : 2'b00;
                s_axi_rdata <= (ar_bad || reg_rd_error) ? 64'd0 :
                               ar_addr[2] ? {reg_rd_data, 32'd0} : {32'd0, reg_rd_data};
            end
            if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 0;
                if (read_remaining == 0) read_active <= 0;
                else read_remaining <= read_remaining - 1;
            end
        end
    end
endmodule
