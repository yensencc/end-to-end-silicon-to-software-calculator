#include <verilated.h>
#include "Vtop.h"
#include <cstdio>

vluint64_t main_time = 0;

double sc_time_stamp() {
    return main_time;
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    Verilated::traceEverOn(true);

    Vtop *top = new Vtop;

    top->clk   = 0;
    top->rst_n = 1;
    top->btn_a = 0;
    top->btn_b = 0;
    top->opcode = 0;

    top->rst_n = 0;
    for (int i = 0; i < 10; i++) {
        top->clk = !top->clk;
        top->eval();
        main_time++;
    }
    top->rst_n = 1;

    printf("=== RTL Simulation: ALU Test ===\n");

    printf("\nTest 1: 2 + 2 = 4\n");
    top->btn_a  = 2;
    top->btn_b  = 2;
    top->opcode = 0;
    for (int i = 0; i < 4; i++) {
        top->clk = !top->clk;
        top->eval();
        main_time++;
    }
    printf("  result=%d (expected 4) %s\n", top->alu_result,
           top->alu_result == 4 ? "PASS" : "FAIL");

    printf("\nTest 2: 5 + 3 = 8\n");
    top->btn_a  = 5;
    top->btn_b  = 3;
    top->opcode = 0;
    for (int i = 0; i < 4; i++) {
        top->clk = !top->clk;
        top->eval();
        main_time++;
    }
    printf("  result=%d (expected 8) %s\n", top->alu_result,
           top->alu_result == 8 ? "PASS" : "FAIL");

    printf("\nTest 3: 10 - 3 = 7\n");
    top->btn_a  = 10;
    top->btn_b  = 3;
    top->opcode = 1;
    for (int i = 0; i < 4; i++) {
        top->clk = !top->clk;
        top->eval();
        main_time++;
    }
    printf("  result=%d (expected 7) %s\n", top->alu_result,
           top->alu_result == 7 ? "PASS" : "FAIL");

    printf("\nTest 4: 200 - 50 = 150\n");
    top->btn_a  = 200;
    top->btn_b  = 50;
    top->opcode = 1;
    for (int i = 0; i < 4; i++) {
        top->clk = !top->clk;
        top->eval();
        main_time++;
    }
    printf("  result=%d (expected 150) %s\n", top->alu_result,
           top->alu_result == 150 ? "PASS" : "FAIL");

    top->final();
    delete top;
    printf("\n=== RTL Simulation Complete ===\n");
    return 0;
}
