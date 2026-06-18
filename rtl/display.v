module display (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  value,
    input  wire        load,
    output wire [6:0]  seg
);
    reg [7:0] display_val;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            display_val <= 8'b0;
        end else if (load) begin
            display_val <= value;
        end
    end

    reg [6:0] seg_reg;
    always @(*) begin
        case (display_val[3:0])
            4'h0: seg_reg = 7'b0111111;
            4'h1: seg_reg = 7'b0000110;
            4'h2: seg_reg = 7'b1011011;
            4'h3: seg_reg = 7'b1001111;
            4'h4: seg_reg = 7'b1100110;
            4'h5: seg_reg = 7'b1101101;
            4'h6: seg_reg = 7'b1111101;
            4'h7: seg_reg = 7'b0000111;
            4'h8: seg_reg = 7'b1111111;
            4'h9: seg_reg = 7'b1101111;
            4'hA: seg_reg = 7'b1110111;
            4'hB: seg_reg = 7'b1111100;
            4'hC: seg_reg = 7'b0111001;
            4'hD: seg_reg = 7'b1011110;
            4'hE: seg_reg = 7'b1111001;
            4'hF: seg_reg = 7'b1110001;
            default: seg_reg = 7'b0;
        endcase
    end
    assign seg = seg_reg;
endmodule
