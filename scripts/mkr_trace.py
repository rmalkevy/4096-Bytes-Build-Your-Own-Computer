#!/usr/bin/env python3
"""Print a step-by-step trace table of an ember program, in the MKR.md format.

    python3 scripts/mkr_trace.py 28 40 08 20 FD 2A 2B 18 32 05 00 00
    python3 scripts/mkr_trace.py --stack 20 51 54 0A 00 ...
    python3 scripts/mkr_trace.py --ember ./build/ember 20 05 ...

The bytes are put at address 0x000 with `set`, then the script sends `step`,
`regs` (and `stack` with --stack) once per step and reads the answers. It
needs an ember that understands `set`, `step`, `regs` and `dump` and prints
registers as PC=0x.. H=0x.. SP=0x.. A=.. B=.. Z=. N=. C=. — the reference
does; your own ember does if it uses the same names. By default it runs
reference/build/ember; pass --ember for any other binary.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# opcode: (mnemonic, size, operand) -- operand: None, "imm8" or "addr16"
OPS = {
    0x00: ("HALT", 1, None), 0x01: ("NOP", 1, None), 0x02: ("OUT", 1, None),
    0x03: ("OUTN", 1, None), 0x04: ("OUTS {}", 3, "addr16"),
    0x10: ("ADD A, B", 1, None), 0x11: ("SUB A, B", 1, None), 0x12: ("AND A, B", 1, None),
    0x13: ("OR A, B", 1, None), 0x14: ("XOR A, B", 1, None), 0x15: ("NOT A", 1, None),
    0x16: ("SHL A", 1, None), 0x17: ("SHR A", 1, None), 0x18: ("INC A", 1, None),
    0x19: ("DEC A", 1, None), 0x1A: ("CMP A, B", 1, None), 0x1B: ("MUL A, B", 1, None),
    0x20: ("LOADI A, {}", 2, "imm8"), 0x21: ("LOADI B, {}", 2, "imm8"),
    0x22: ("LOAD A, [{}]", 3, "addr16"), 0x23: ("LOAD B, [{}]", 3, "addr16"),
    0x24: ("STORE [{}], A", 3, "addr16"), 0x25: ("STORE [{}], B", 3, "addr16"),
    0x26: ("MOV A, B", 1, None), 0x27: ("MOV B, A", 1, None),
    0x28: ("LOADH H, {}", 3, "addr16"), 0x29: ("LOAD A, [H]", 1, None),
    0x2A: ("STORE [H], A", 1, None), 0x2B: ("INCH", 1, None), 0x2C: ("DECH", 1, None),
    0x2D: ("HLOW", 1, None),
    0x30: ("JMP {}", 3, "addr16"), 0x31: ("JZ {}", 3, "addr16"), 0x32: ("JNZ {}", 3, "addr16"),
    0x33: ("JC {}", 3, "addr16"), 0x34: ("JNC {}", 3, "addr16"),
    0x40: ("CLS", 1, None), 0x41: ("PLOT", 1, None), 0x42: ("UNPLOT", 1, None), 0x43: ("SHOW", 1, None),
    0x50: ("PUSH A", 1, None), 0x51: ("POP A", 1, None), 0x52: ("PUSH B", 1, None),
    0x53: ("POP B", 1, None), 0x54: ("CALL {}", 3, "addr16"), 0x55: ("RET", 1, None),
    0x56: ("PUSH H", 1, None), 0x57: ("POP H", 1, None), 0x60: ("ALLOC", 1, None),
}

REGS = re.compile(r"PC=0x([0-9a-fA-F]+)\s+H=0x([0-9a-fA-F]+)\s+SP=0x([0-9a-fA-F]+)\s+"
                  r"A=(\d+)\s+B=(\d+)\s+Z=(\d)\s+N=(\d)\s+C=(\d)")
DUMP = re.compile(r"^([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}\s+){15}[0-9a-fA-F]{2})", re.M)


def disasm(mem, pc):
    op = mem.get(pc, 0)
    if op not in OPS:
        return f"0x{op:02X}?"
    text, size, kind = OPS[op]
    if kind == "imm8":
        return text.format(f"0x{mem.get(pc + 1, 0):02X}")
    if kind == "addr16":
        return text.format(f"0x{mem.get(pc + 1, 0) | (mem.get(pc + 2, 0) << 8):04X}")
    return text


def parse_dump(text):
    cells = {}
    for addr, row in DUMP.findall(text):
        for i, b in enumerate(row.split()):
            cells[int(addr, 16) + i] = int(b, 16)
    return cells


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bytes", nargs="+", help="program bytes in hex, from address 0x000")
    ap.add_argument("--ember", default=os.path.join(ROOT, "reference", "build", "ember"),
                    help="ember binary (default: reference/build/ember)")
    ap.add_argument("--stack", action="store_true", help="add SP and stack columns (MKR 2)")
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--prompt", default="ember> ", help="your ember's prompt")
    args = ap.parse_args()

    if not os.path.isfile(args.ember):
        print(f"no ember binary at {args.ember}\n"
              "build one (cmake -S . -B build && cmake --build build) and pass --ember PATH",
              file=sys.stderr)
        return 2

    program = [int(b, 16) for b in args.bytes]
    mem = dict(enumerate(program))
    per_step = ["step", "regs"] + (["stack"] if args.stack else [])
    cmds = [f"set {i} 0x{b:02X}" for i, b in enumerate(program)] + ["dump"]
    cmds += per_step * args.max_steps + ["dump", "quit"]
    out = subprocess.run([args.ember], input="\n".join(cmds) + "\n",
                         capture_output=True, text=True).stdout
    answers = out.split(args.prompt)[1:]  # answers[i] is the reply to cmds[i]
    if len(answers) < len(cmds) - 1:
        print("could not split the output by the prompt; try --prompt", file=sys.stderr)
        return 2

    first = len(program)
    before = parse_dump(answers[first])
    head = "| # | PC | Інструкція | A | B | H | Z N C |"
    if args.stack:
        head += " SP | Стек (від вершини) |"
    rows, outputs = [], []

    pc, k, done = 0, first + 1, False
    for n in range(1, args.max_steps + 1):
        step_out = answers[k].strip()
        m = REGS.search(answers[k + 1])
        if not m:
            break
        npc, h, sp, a, b, z, nf, c = m.groups()
        row = (f"| {n} | `0x{pc:03X}` | `{disasm(mem, pc)}` | `0x{int(a):02X}` | `0x{int(b):02X}` "
               f"| `0x{int(h, 16):03X}` | {z} {nf} {c} |")
        if args.stack:
            top = answers[k + 2].split("top:")[-1].split()
            row += f" `0x{int(sp, 16):03X}` | {' '.join(t.upper() for t in top) or '—'} |"
        rows.append(row)
        outputs.append(step_out.replace("\n", " ").replace("|", "\\|"))
        pc = int(npc, 16)
        k += len(per_step)
        if "halted" in answers[k - len(per_step) + 1] or "error" in step_out:
            done = True
            break
    with_output = any(outputs)
    print(head + (" Вивід |" if with_output else ""))
    print("|---" * (head.count("|") - 1 + with_output) + "|")
    for row, shown in zip(rows, outputs):
        print(row + (f" {('`' + shown + '`') if shown else ''} |" if with_output else ""))
    if not done:
        print(f"\n(stopped after {args.max_steps} steps without HALT)")

    after = parse_dump(answers[len(cmds) - 2])
    changed = [a for a in sorted(after) if after[a] != before.get(a, 0)]
    if changed:
        print("\nПам'ять, що змінилась: " +
              ", ".join(f"`0x{a:03X}` = `0x{after[a]:02X}`" for a in changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
