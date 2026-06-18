module top (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  btn_a,
    input  wire [7:0]  btn_b,
    input  wire [1:0]  opcode,
    output wire [7:0]  alu_result,
    output wire        alu_carry,
    output wire        alu_zero,
    output wire        alu_overflow,
    output wire [6:0]  seg_out
);

    alu u_alu (
        .clk      (clk),
        .rst_n    (rst_n),
        .opcode   (opcode),
        .a        (btn_a),
        .b        (btn_b),
        .result   (alu_result),
        .carry    (alu_carry),
        .zero     (alu_zero),
        .overflow (alu_overflow)
    );

    display u_display (
        .clk   (clk),
        .rst_n (rst_n),
        .value (alu_result),
        .load  (1'b1),
        .seg   (seg_out)
    );

endmodule
