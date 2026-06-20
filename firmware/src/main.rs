#![no_std]
#![no_main]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

// ── Vector table as a single repr(C) struct in one section ──
#[repr(C)]
struct Vt {
    sp: u32,
    handlers: [Option<unsafe extern "C" fn() -> !>; 79],
}

#[link_section = ".vector_table"]
#[used]
static VECTOR_TABLE: Vt = Vt {
    sp: 0x2001_0000,
    handlers: [
        Some(Reset),                        // 1: Reset
        Some(NonMaskableInt),               // 2: NMI
        Some(HardFault_),                   // 3: HardFault
        Some(MemoryManagement),             // 4: MemManage
        Some(BusFault),                     // 5: BusFault
        Some(UsageFault),                   // 6: UsageFault
        None, None, None, None,             // 7-10: reserved
        Some(SVCall),                       // 11: SVCall
        Some(DebugMonitor),                 // 12: DebugMonitor
        None,                               // 13: reserved
        Some(PendSV),                       // 14: PendSV
        Some(SysTick),                      // 15: SysTick
        // 16-79: interrupt handlers
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None,
        None, None, None, None,
    ],
};

extern "C" fn DefaultHandler() -> ! { loop {} }
extern "C" fn HardFault_() -> ! { loop {} }
extern "C" fn NonMaskableInt() -> ! { DefaultHandler() }
extern "C" fn MemoryManagement() -> ! { DefaultHandler() }
extern "C" fn BusFault() -> ! { DefaultHandler() }
extern "C" fn UsageFault() -> ! { DefaultHandler() }
extern "C" fn SVCall() -> ! { DefaultHandler() }
extern "C" fn DebugMonitor() -> ! { DefaultHandler() }
extern "C" fn PendSV() -> ! { DefaultHandler() }
extern "C" fn SysTick() -> ! { DefaultHandler() }

// ── Reset handler ──
#[no_mangle]
pub unsafe extern "C" fn Reset() -> ! {
    uart_init();
    oled_puts(b"CALCULATOR 1.0", b"    READY    ");
    let mut calc = Calc::new();
    calc.send_display();
    loop {
        calc.handle_key(uart_getc());
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

// ── LM3S6965 UART0 registers ──
const UART0_DR: *mut u32 = 0x4000_C000 as *mut u32;
const UART0_FR: *mut u32 = 0x4000_C018 as *mut u32;
const UART0_IBRD: *mut u32 = 0x4000_C024 as *mut u32;
const UART0_FBRD: *mut u32 = 0x4000_C028 as *mut u32;
const UART0_LCRH: *mut u32 = 0x4000_C02C as *mut u32;
const UART0_CR: *mut u32 = 0x4000_C030 as *mut u32;

const RCGC1: *mut u32 = 0x400F_E104 as *mut u32;

fn uart_init() {
    unsafe { write_volatile(RCGC1, read_volatile(RCGC1) | 1) };
    core::hint::spin_loop();
    core::hint::spin_loop();
    unsafe {
        write_volatile(UART0_IBRD, 104);
        write_volatile(UART0_FBRD, 11);
        write_volatile(UART0_LCRH, 0x70);
        write_volatile(UART0_CR, 0x301);
    }
}

fn uart_putc(c: u8) {
    unsafe {
        // Wait until TX FIFO not full (TXFF bit 5 = 0)
        while (read_volatile(UART0_FR) & (1 << 5)) != 0 {}
        write_volatile(UART0_DR, c as u32);
    }
}

fn uart_puts(s: &[u8]) {
    for &b in s {
        uart_putc(b);
        if b == b'\n' {
            uart_putc(b'\r');
        }
    }
}

fn oled_puts(line1: &[u8], line2: &[u8]) {
    uart_puts(b"O:");
    uart_puts(line1);
    uart_puts(b"|");
    uart_puts(line2);
    uart_puts(b"\n");
}

fn uart_getc() -> u8 {
    unsafe {
        // Wait until RX FIFO not empty (RXFE bit 4 = 0)
        while (read_volatile(UART0_FR) & (1 << 4)) != 0 {}
        read_volatile(UART0_DR) as u8
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Op { Add, Sub, Mul, Div }

struct Calc {
    display: [u8; 8],
    accum: i64,
    op: Option<Op>,
    fresh: bool,
}

impl Calc {
    fn new() -> Self {
        Calc { display: *b"       0", accum: 0, op: None, fresh: true }
    }

    fn send_display(&self) {
        uart_puts(b"D: ");
        uart_puts(&self.display);
        uart_puts(b"\n");
    }

    fn digit(&mut self, d: u8) {
        if self.fresh {
            self.display = *b"        ";
            self.fresh = false;
        }
        // Shift left by 1, then place new digit at the right end
        for j in 0..7 {
            self.display[j] = self.display[j + 1];
        }
        self.display[7] = b'0' + d;
        self.send_display();
    }

    fn set_op(&mut self, op: Op) {
        if !self.fresh { self.accum = self.parse_display(); }
        self.op = Some(op);
        self.fresh = true;
    }

    fn parse_display(&self) -> i64 {
        let s = core::str::from_utf8(&self.display).unwrap_or("0").trim();
        if s.is_empty() { return 0; }
        s.parse::<i64>().unwrap_or(0)
    }

    fn set_display(&mut self, v: i64) {
        // Format v as right-aligned 8-char string (no_std-compatible)
        let mut buf = [b' '; 8];
        let mut pos = 8;
        let mut neg = false;
        let mut n = if v < 0 { neg = true; (0u64).wrapping_sub(v as u64) } else { v as u64 };
        loop {
            pos -= 1;
            buf[pos] = b'0' + (n % 10) as u8;
            n /= 10;
            if n == 0 { break; }
        }
        if neg {
            pos -= 1;
            buf[pos] = b'-';
        }
        self.display = buf;
    }

    fn equals(&mut self) {
        if self.fresh {
            self.display = *b"       0";
            self.send_display();
            return;
        }
        let val = self.parse_display();
        let result = match self.op {
            Some(Op::Add) => self.accum + val,
            Some(Op::Sub) => self.accum - val,
            Some(Op::Mul) => self.accum * val,
            Some(Op::Div) => if val != 0 { self.accum / val } else { 0 },
            None => val,
        };
        self.accum = result;
        self.set_display(result);
        self.send_display();
        if self.op.is_some() {
            oled_puts(b"CALCULATOR OK", b" AWESOME! ");
            for _ in 0..8_000_000 {
                core::hint::spin_loop();
            }
            oled_puts(b"             ", b"             ");
            self.set_display(result);
            self.send_display();
        }
        self.op = None;
        self.fresh = true;
    }

    fn clear(&mut self) {
        self.display = *b"       0";
        self.accum = 0;
        self.op = None;
        self.fresh = true;
        self.send_display();
    }

    fn handle_key(&mut self, key: u8) {
        match key {
            b'0'..=b'9' => self.digit(key - b'0'),
            b'+' => self.set_op(Op::Add),
            b'-' => self.set_op(Op::Sub),
            b'*' => self.set_op(Op::Mul),
            b'/' => self.set_op(Op::Div),
            b'=' | b'\n' => self.equals(),
            b'c' | b'C' => self.clear(),
            _ => {}
        }
    }
}
