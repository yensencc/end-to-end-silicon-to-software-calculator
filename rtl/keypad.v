module keypad (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [3:0]  col_in,
    output reg  [3:0]  row_out,
    output reg  [3:0]  key_value,
    output reg         key_pressed
);
    reg [3:0] row_state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            row_state   <= 4'b1110;
            key_value   <= 4'b0;
            key_pressed <= 1'b0;
        end else begin
            row_out <= row_state;
            case (row_state)
                4'b1110: if (col_in != 4'b1111) begin
                    key_value   <= {2'b00, col_in[1:0]};
                    key_pressed <= 1'b1;
                end else begin
                    row_state   <= 4'b1101;
                    key_pressed <= 1'b0;
                end
                4'b1101: if (col_in != 4'b1111) begin
                    key_value   <= {2'b01, col_in[1:0]};
                    key_pressed <= 1'b1;
                end else begin
                    row_state   <= 4'b1011;
                    key_pressed <= 1'b0;
                end
                4'b1011: if (col_in != 4'b1111) begin
                    key_value   <= {2'b10, col_in[1:0]};
                    key_pressed <= 1'b1;
                end else begin
                    row_state   <= 4'b0111;
                    key_pressed <= 1'b0;
                end
                4'b0111: if (col_in != 4'b1111) begin
                    key_value   <= {2'b11, col_in[1:0]};
                    key_pressed <= 1'b1;
                end else begin
                    row_state   <= 4'b1110;
                    key_pressed <= 1'b0;
                end
                default: row_state <= 4'b1110;
            endcase
        end
    end
endmodule
