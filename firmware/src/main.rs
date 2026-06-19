#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use core::ptr::{read_volatile, write_volatile};

// ── LM3S6965 UART0 registers ──
const UART0_DR: *mut u32 = 0x4000_C000 as *mut u32;  // offset 0x000
const UART0_FR: *mut u32 = 0x4000_C018 as *mut u32;  // offset 0x018
const UART0_IBRD: *mut u32 = 0x4000_C024 as *mut u32;
const UART0_FBRD: *mut u32 = 0x4000_C028 as *mut u32;
const UART0_LCRH: *mut u32 = 0x4000_C02C as *mut u32;
const UART0_CR: *mut u32 = 0x4000_C030 as *mut u32;

const RCGC1: *mut u32 = 0x400F_E104 as *mut u32;

fn uart_init() {
    // Enable UART0 clock (bit 0)
    unsafe { write_volatile(RCGC1, read_volatile(RCGC1) | 1) };

    // UARTLCRH: 8-bit, no parity, 1 stop, FIFO enabled
    unsafe { write_volatile(UART0_LCRH, 0x70) }; // WLEN=11 (8bit), FEN=1

    // Baud rate 115200 (ignored by QEMU but proper init)
    unsafe {
        write_volatile(UART0_IBRD, 4);
        write_volatile(UART0_FBRD, 22);
    }

    // UARTCR: enable UART, TX, RX
    unsafe { write_volatile(UART0_CR, 0x301) }; // UARTEN|TXE|RXE
}

fn uart_putc(c: u8) {
    // Wait for TX FIFO not full
    loop {
        let fr = unsafe { read_volatile(UART0_FR) };
        if fr & (1 << 3) == 0 { break; } // TXFF=0 means space available
    }
    unsafe { write_volatile(UART0_DR, c as u32) };
}

fn uart_puts(s: &str) {
    for &b in s.as_bytes() {
        if b == b'\n' {
            uart_putc(b'\r');
        }
        uart_putc(b);
    }
}

fn uart_getc() -> u8 {
    loop {
        let fr = unsafe { read_volatile(UART0_FR) };
        if fr & (1 << 4) == 0 { // RXFE=0 means data available
            let dr = unsafe { read_volatile(UART0_DR) };
            return (dr & 0xFF) as u8;
        }
    }
}

fn display_value(val: i32) {
    // Send display update: "D:+1234567\n"
    // 8-char field, right-aligned, with sign
    let neg = val < 0;
    let abs_val = if neg { -val } else { val };
    let mut buf = [b' '; 8];
    let mut n = abs_val;
    let mut i = 7;
    if n == 0 {
        buf[7] = b'0';
        i = 6;
    }
    while n > 0 && i > 0 {
        buf[i] = (n % 10) as u8 + b'0';
        n /= 10;
        i -= 1;
    }
    if neg {
        if i > 0 {
            buf[i] = b'-';
        } else {
            return display_error();
        }
    }

    uart_putc(b'D');
    uart_putc(b':');
    for &b in buf.iter() {
        uart_putc(b);
    }
    uart_putc(b'\n');
}

fn display_error() {
    uart_puts("E:Error\n");
}

// ── Calculator state machine ──
const MAX_DIGITS: i32 = 100_000_000; // 8-digit limit

#[derive(PartialEq)]
enum State {
    First,
    Second,
    Result,
}

#[entry]
fn main() -> ! {
    uart_init();
    uart_puts("CALC v1.0\n");

    let mut state = State::First;
    let mut operand1: i32 = 0;
    let mut operand2: i32 = 0;
    let mut current: i32 = 0;
    let mut op: u8 = b' ';

    display_value(current);

    loop {
        let key = uart_getc();
        match key {
            b'0'..=b'9' => {
                let digit = (key - b'0') as i32;
                let new = current.wrapping_mul(10).wrapping_add(digit);
                // Prevent overflow / limit to 8 digits
                if current <= MAX_DIGITS / 10 {
                    current = new;
                }
                display_value(current);
            }
            b'C' | b'c' => {
                current = 0;
                operand1 = 0;
                operand2 = 0;
                op = b' ';
                state = State::First;
                display_value(current);
            }
            b'+' | b'-' | b'*' | b'/' => {
                if state == State::First || state == State::Result {
                    operand1 = current;
                    op = key;
                    current = 0;
                    state = State::Second;
                    // Show first operand on display
                    display_value(operand1);
                } else if state == State::Second {
                    // Chain operation
                    operand2 = current;
                    let result = compute(operand1, operand2, op);
                    current = 0;
                    operand1 = result;
                    op = key;
                    display_value(operand1);
                }
            }
            b'=' | b'\n' | b'\r' => {
                if state == State::Second {
                    operand2 = current;
                    let result = compute(operand1, operand2, op);
                    current = result;
                    operand1 = result;
                    state = State::Result;
                    display_value(result);
                } else if state == State::Result {
                    // Repeat last operation with result
                    let result = compute(operand1, operand2, op);
                    current = result;
                    operand1 = result;
                    display_value(result);
                }
            }
            _ => {}
        }
    }
}

fn compute(a: i32, b: i32, op: u8) -> i32 {
    match op {
        b'+' => a.wrapping_add(b),
        b'-' => a.wrapping_sub(b),
        b'*' => a.wrapping_mul(b),
        b'/' => {
            if b == 0 { 0 } else { a / b }
        }
        _ => a,
    }
}
