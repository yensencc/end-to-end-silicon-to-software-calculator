module alu (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [1:0]  opcode,
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    output reg  [7:0]  result,
    output reg         carry,
    output reg         zero,
    output reg         overflow
);
    wire [8:0] add_result;
    wire [8:0] sub_result;

    assign add_result = a + b;
    assign sub_result = a - b;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result   <= 8'b0;
            carry    <= 1'b0;
            zero     <= 1'b1;
            overflow <= 1'b0;
        end else begin
            case (opcode)
                2'b00: begin
                    result   <= add_result[7:0];
                    carry    <= add_result[8];
                    zero     <= (add_result[7:0] == 8'b0);
                    overflow <= (a[7] == b[7]) && (add_result[7] != a[7]);
                end
                2'b01: begin
                    result   <= sub_result[7:0];
                    carry    <= sub_result[8];
                    zero     <= (sub_result[7:0] == 8'b0);
                    overflow <= (a[7] != b[7]) && (sub_result[7] != a[7]);
                end
                default: begin
                    result   <= 8'b0;
                    carry    <= 1'b0;
                    zero     <= 1'b1;
                    overflow <= 1'b0;
                end
            endcase
        end
    end
endmodule
