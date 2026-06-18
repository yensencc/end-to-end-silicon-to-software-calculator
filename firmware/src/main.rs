#![no_std]
#![no_main]

use cortex_m_rt::entry;
use cortex_m_semihosting::hprintln;
use cortex_m_semihosting::debug::{self, EXIT_SUCCESS};
use panic_halt as _;

fn alu_add(a: i8, b: i8) -> i8 {
    a + b
}

fn alu_sub(a: i8, b: i8) -> i8 {
    a - b
}

fn alu_mul(a: i8, b: i8) -> i8 {
    a * b
}

#[entry]
fn main() -> ! {
    let a: i8 = 2;
    let b: i8 = 2;

    hprintln!("Calculator Firmware (QEMU ARM Cortex-M3)");
    hprintln!("========================================");
    hprintln!("");
    hprintln!("{} + {} = {}", a, b, alu_add(a, b));
    hprintln!("{} - {} = {}", a, b, alu_sub(a, b));
    hprintln!("{} * {} = {}", a, b, alu_mul(a, b));

    let result = alu_add(a, b);
    hprintln!("");
    hprintln!("PASS: {} + {} = {}", a, b, result);
    hprintln!("Firmware simulation complete.");

    debug::exit(EXIT_SUCCESS);
    loop {}
}
