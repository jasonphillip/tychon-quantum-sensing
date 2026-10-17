`timescale 1ns/1ps
module tb_quantum_demo;
    reg clk=0; always #5 clk=~clk;
    // Explicit assertion edge initializes the generated HLS forwarding aliases.
    reg resetn=1;
    reg [8:0] awid=0, arid=0;
    reg [37:0] awaddr=0, araddr=0;
    reg [7:0] awlen=0, arlen=0;
    reg [2:0] awsize=2, arsize=2;
    reg [1:0] awburst=1, arburst=1, awlock=0, arlock=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0,wlast=1;
    reg [63:0] wdata=0; reg [7:0] wstrb=0;
    wire awready,wready,bvalid,arready,rvalid,rlast,buser,ruser;
    wire [8:0] bid,rid; wire [1:0] bresp,rresp; wire [63:0] rdata;
    localparam [37:0] BASE=38'h0060040000;
    quantum_demo_axi dut(
        .aclk(clk),.aresetn(resetn),
        .s_axi_awid(awid),.s_axi_awaddr(awaddr),.s_axi_awlen(awlen),.s_axi_awsize(awsize),
        .s_axi_awburst(awburst),.s_axi_awlock(awlock),.s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
        .s_axi_awqos(4'd0),.s_axi_awregion(4'd0),.s_axi_awuser(1'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wlast(wlast),.s_axi_wuser(1'b0),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bid(bid),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_buser(buser),.s_axi_bready(bready),
        .s_axi_arid(arid),.s_axi_araddr(araddr),.s_axi_arlen(arlen),.s_axi_arsize(arsize),
        .s_axi_arburst(arburst),.s_axi_arlock(arlock),.s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
        .s_axi_arqos(4'd0),.s_axi_arregion(4'd0),.s_axi_aruser(1'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rid(rid),.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rlast(rlast),.s_axi_rvalid(rvalid),
        .s_axi_ruser(ruser),.s_axi_rready(rready));

    reg [31:0] ro_input[0:2303], nv_input[0:511], qec_expected[0:255];
    reg [63:0] ro_expected[0:35], nv_score[0:7];
    reg [15:0] nv_index[0:7];
    integer checks=0, writes=0, reads=0, qec_calls=0, ro_calls=0, nv_calls=0;
    integer k,j; reg [31:0] value,low_word,high_word; reg [63:0] actual_score;
    integer cycle_counter=0;
    always @(posedge clk) cycle_counter <= cycle_counter+1;
    initial begin #200000000; $fatal(1,"Global timeout"); end

    task automatic check(input bit condition, input string text);
        begin
            checks=checks+1;
            if (!condition) $fatal(1,"CHECK FAILED: %s at cycle %0d",text,cycle_counter);
        end
    endtask
    task automatic send_aw(input [37:0] address, input [7:0] length, input [2:0] size, input [8:0] id);
        begin
            @(negedge clk); awaddr=address; awlen=length; awsize=size; awid=id; awvalid=1;
            do @(posedge clk); while (!awready);
            @(negedge clk); awvalid=0;
        end
    endtask
    task automatic send_w(input [63:0] data, input [7:0] strobes, input bit last);
        begin
            @(negedge clk); wdata=data; wstrb=strobes; wlast=last; wvalid=1;
            do @(posedge clk); while (!wready);
            @(negedge clk); wvalid=0;
        end
    endtask
    task automatic get_b(input [1:0] expected, input [8:0] id, input integer stall);
        reg [1:0] saved_resp; reg [8:0] saved_id;
        begin
            while(!bvalid) @(negedge clk);
            saved_resp=bresp; saved_id=bid;
            repeat(stall) begin
                @(negedge clk);
                check(bvalid && bresp===saved_resp && bid===saved_id,"B stable under backpressure");
            end
            if (!(bresp===expected && bid===id && buser===0))
                $display("B diagnostic got=%h expected=%h id=%h expected_id=%h aw=%h data=%h strobes=%h selected=%d busy=%b ready=%b aw_bad=%b",
                         bresp,expected,bid,id,dut.aw_addr,dut.w_data,dut.w_strb,dut.regs.selected_core,dut.regs.busy,dut.regs.selected_ready,dut.aw_bad);
            check(bresp===expected && bid===id && buser===0,"B response and full9-bit ID");
            bready=1; @(posedge clk); @(negedge clk); bready=0;
        end
    endtask
    task automatic write_word(input [11:0] offset,input [31:0] data,input [1:0] expected);
        reg [63:0] bus_data; reg [7:0] strobes; integer order;
        begin
            bus_data=offset[2] ? {data,32'd0} : {32'd0,data};
            strobes=offset[2] ? 8'hf0 : 8'h0f; order=writes%3;
            writes=writes+1;
            if(order==0) begin
                send_aw(BASE+offset,0,2,9'h1ab); repeat(2) @(negedge clk); send_w(bus_data,strobes,1);
            end else if(order==1) begin
                send_w(bus_data,strobes,1); repeat(2) @(negedge clk); send_aw(BASE+offset,0,2,9'h1ab);
            end else fork
                send_aw(BASE+offset,0,2,9'h1ab);
                send_w(bus_data,strobes,1);
            join
            get_b(expected,9'h1ab,writes%4);
        end
    endtask
    task automatic send_ar(input [37:0] address,input [7:0] length,input [2:0] size,input [8:0] id);
        begin
            @(negedge clk); araddr=address; arlen=length; arsize=size; arid=id; arvalid=1;
            do @(posedge clk); while(!arready);
            @(negedge clk); arvalid=0;
        end
    endtask
    task automatic get_r(input [1:0] expected,input [8:0] id,input bit last,input integer stall,output [63:0] data);
        reg [63:0] saved; reg [1:0] resp; reg [8:0] saved_id; reg saved_last;
        begin
            while(!rvalid) @(negedge clk);
            saved=rdata; resp=rresp; saved_id=rid; saved_last=rlast;
            repeat(stall) begin
                @(negedge clk);
                check(rvalid && rdata===saved && rresp===resp && rid===saved_id && rlast===saved_last,"R stable under backpressure");
            end
            check(rresp===expected && rid===id && rlast===last && ruser===0,"R response, full9-bit ID, RLAST");
            data=rdata; rready=1; @(posedge clk); @(negedge clk); rready=0;
        end
    endtask
    task automatic read_word(input [11:0] offset,input [1:0] expected,output [31:0] data);
        reg [63:0] bus_data;
        begin
            reads=reads+1; send_ar(BASE+offset,0,2,9'h16d);
            get_r(expected,9'h16d,1,reads%3,bus_data);
            data=offset[2] ? bus_data[63:32] : bus_data[31:0];
            if(expected==0) check((offset[2] ? bus_data[31:0] : bus_data[63:32])===0,"Unused narrow-read lane is zero");
        end
    endtask
    task automatic wait_done(input integer limit);
        integer begin_cycle; reg [31:0] status;
        begin
            begin_cycle=cycle_counter; status=1;
            while(status[0] && cycle_counter-begin_cycle<limit) begin
                read_word(12'h00c,0,status);
                if(status[0]) repeat(16) @(negedge clk);
            end
            check(!status[0] && status[1],"Operation reaches DONE");
        end
    endtask
    task automatic check_success;
        reg [31:0] code,cycles;
        begin
            read_word(12'h034,0,code); check(code==0,"Operation ERROR=0");
            read_word(12'h01c,0,cycles); check(cycles>0 && cycles<1000000,"Measured fabric cycles within watchdog");
        end
    endtask
    task automatic reset_bus;
        begin
            @(negedge clk); resetn=0; awvalid=0; wvalid=0; arvalid=0; bready=0; rready=0;
            repeat(4) @(negedge clk); resetn=1; repeat(4) @(negedge clk);
            check(!bvalid && !rvalid,"Reset flushes bus responses");
        end
    endtask
    reg [63:0] burst_data;
    initial begin
        $readmemh("vectors/readout_input.hex",ro_input);
        $readmemh("vectors/readout_expected.hex",ro_expected);
        $readmemh("vectors/nv_input.hex",nv_input);
        $readmemh("vectors/nv_index.hex",nv_index);
        $readmemh("vectors/nv_score.hex",nv_score);
        $readmemh("vectors/qec_expected.hex",qec_expected);
        reset_bus();
        read_word(0,0,value); check(value==32'h51465047,"Identity");
        read_word(4,0,value); check(value==32'h10000,"ABI high lane");
        write_word(12'h010,1,0); write_word(12'h008,1,2); // incomplete input rejected
        write_word(12'h018,0,2); write_word(12'h010,0,2); write_word(12'h020,1,2);
        read_word(12'h03c,2,value); read_word(12'h003,2,value);
        // Unsupported bursts drain correctly and have no register side effects.
        send_aw(BASE+12'h010,1,2,9'h1ff); send_w(64'd3,8'h0f,0); send_w(64'd2,8'h0f,1);
        get_b(2,9'h1ff,5); read_word(12'h010,0,value); check(value==1,"Unsupported write burst has no effects");
        send_ar(BASE,2,2,9'h1fe);
        get_r(2,9'h1fe,0,2,burst_data); get_r(2,9'h1fe,0,2,burst_data); get_r(2,9'h1fe,1,2,burst_data);
        send_aw(BASE+12'h010,0,3,9'h1aa); send_w(64'd3,8'hff,1); get_b(2,9'h1aa,0);
        send_aw(BASE+12'h010,0,2,9'h1aa); send_w(64'd3,8'h01,1); get_b(2,9'h1aa,0);
        send_ar(BASE+38'h1000,0,2,9'h1ee); get_r(2,9'h1ee,1,0,burst_data);
        $display("PROTOCOL BASIC PASS");

        write_word(12'h010,3,0);
        for(k=0;k<256;k=k+1) begin
            write_word(12'h014,k,0); write_word(12'h008,1,0); wait_done(1000); check_success();
            read_word(12'h020,0,low_word); read_word(12'h024,0,high_word);
            check(low_word===qec_expected[k] && high_word===0,"QEC full correction");
            qec_calls=qec_calls+1;
        end
        $display("QEC PASS 256/256");

        write_word(12'h010,1,0);
        for(k=0;k<36;k=k+1) begin
            for(j=0;j<64;j=j+1) write_word(12'h100+j*4,ro_input[k*64+j],0);
            write_word(12'h008,1,0); wait_done(2000); check_success();
            read_word(12'h020,0,low_word); read_word(12'h024,0,high_word);
            if({high_word,low_word}!==ro_expected[k])
                $display("Readout case%0d got%h expected%h",k,{high_word,low_word},ro_expected[k]);
            check({high_word,low_word}===ro_expected[k],"Readout exact signed64 score");
            ro_calls=ro_calls+1;
        end
        $display("READOUT PASS 36/36 signed64 scores");

        write_word(12'h010,2,0);
        for(k=0;k<8;k=k+1) begin
            for(j=0;j<64;j=j+1) write_word(12'h100+j*4,nv_input[k*64+j],0);
            write_word(12'h008,1,0);
            if(k==0) begin
                write_word(12'h100,32'hdeadbeef,2); write_word(12'h010,3,2); write_word(12'h008,1,2);
            end
            wait_done(100000); check_success();
            read_word(12'h020,0,low_word); check(low_word==nv_index[k],"NV full index");
            read_word(12'h028,0,low_word); read_word(12'h02c,0,high_word);
            if({high_word,low_word}!==nv_score[k])
                $display("NV case%0d got%h expected%h",k,{high_word,low_word},nv_score[k]);
            check({high_word,low_word}===nv_score[k],"NV full unsigned64 SSE");
            nv_calls=nv_calls+1;
        end
        $display("NV PASS 8/8 indices and full64 scores");

        write_word(12'h018,3,0); write_word(12'h008,1,0); wait_done(1000);
        read_word(12'h034,0,value); check(value==1,"Watchdog timeout reported");
        read_word(12'h020,0,value); check(value==0,"Timeout invalidates result");
        write_word(12'h008,4,0); read_word(12'h034,0,value); check(value==0,"Clear error");
        write_word(12'h018,1000000,0); write_word(12'h008,1,0); write_word(12'h008,2,0); wait_done(1000);
        read_word(12'h034,0,value); check(value==2,"Abort reported");
        write_word(12'h010,3,0); write_word(12'h014,165,0); write_word(12'h008,1,0); wait_done(1000); check_success();
        read_word(12'h020,0,value); check(value===qec_expected[165],"Core recovery after timeout/abort");
        write_word(12'h010,2,0); write_word(12'h008,1,0); reset_bus();
        read_word(12'h00c,0,value); check(value==0,"Reset cancels operation and invalidates input");
        read_word(12'h030,0,value); check(value==0,"Reset clears completion counter");
        send_aw(BASE+12'h010,0,2,9'h1cc); reset_bus();
        write_word(12'h010,3,0); write_word(12'h014,7,0); write_word(12'h008,1,0); wait_done(1000);
        read_word(12'h020,0,value); check(value===qec_expected[7],"Reset flushes pending AW and accepts new work");
        $display("RECOVERY PASS timeout/abort/reset");
        $display("PASS checks=%0d writes=%0d reads=%0d qec=%0d readout=%0d nv=%0d cycles=%0d",
                 checks,writes,reads,qec_calls,ro_calls,nv_calls,cycle_counter);
        $finish;
    end
endmodule
