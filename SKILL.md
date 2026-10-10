---
name: codesys-lad
description: Write PLC logic as ladder diagram (LD) for Bosch Rexroth ctrlX CORE (ctrlX PLC Engineering) and other CODESYS V3 controllers. Ladder is written in a plain-text rung language and compiled to an importable PLCopenXML file, with networks, contacts, coils, set/reset, compares, MOVE, operator boxes (ADD/SUB/MUL/DIV, SEL, MUX, LIMIT, <type>_TO_<type> conversions), timers and FB calls on EN/ENO, plus ladder state machines in the house sequence structure. Use this skill whenever the user asks for ladder, LD, ladder logic, rungs or a ladder version of something, or wants to read or check ladder exported from CODESYS. It builds on the codesys-st skill, which holds the conventions, sequence rules and the PLCopenXML converter.
---

# CODESYS ladder (LD)

Write ladder as text, compile it to PLCopenXML with the codesys-st converter, then read the result back and check it before handing it over. The CODESYS LD editor can't paste text, so the import file is always the deliverable.

## Before writing

- **House rules come from codesys-st.** Read its `references/conventions.md` (naming, var block order, prefixes) and follow its design rules. Ladder changes the notation, not the rules: one writer per output, outputs written last, no edges in sequences, every FB called every scan.
- **Read `references/ladder.md`** before writing any rung. It defines the language, the three box forms (compare, timer, FB on EN/ENO), and how each maps to the XML the editor expects.
- **Sequences:** read codesys-st's `references/patterns.md` §1, then the **Sequences** section of `references/ladder.md`. Jumps and transitions write `_eNextState`, and a `-> _eState := _eNextState` network commits it after each of those two sections. Start from a worked example: `references/examples/FB_CycleLD.st`, or `references/examples/traffic_light/` (design doc, FB and calling program).

## Writing

Each POU's declaration is normal ST. Its body is ladder when it starts with `NETWORK`:

```
NETWORK Start/stop seal-in
    (bStart | bRun) /bStop /bFault -> bRun

NETWORK Run-on timer
    bRun fbRunOn(PT := T#5S) -> bRunOnDone

NETWORK Valve
    -> fbValve(bOpen := _bOpenCmd, rSetpoint := rSp, bOpened => bValveOpen)

NETWORK Target
    -> rTarget := ADD(rHome, rPitch)
```

Put the source in `.st` files with the `END_...` keywords, as codesys-st describes for PLCopenXML. DUTs, GVLs and ST POUs can go in the same build.

**Converting ST to ladder / all-ladder projects:** read **Converting ST to ladder** in `references/ladder.md`. Math, SEL/MUX/LIMIT and type conversions are ladder operator boxes (`-> y := ADD(a, b)`, `-> r := INT_TO_REAL(i)`). Only loops, strings or calls to your own FUNCTIONs stay in a small ST FB. Everything else, including MC_ axis wrappers and validation, goes to rungs. `references/examples/FB_AxisCtrl.st` is a ladder axis wrapper, compiled and run on ctrlX.

## Building and checking

1. Build:
   ```bash
   python3 <codesys-st-dir>/scripts/st_to_plcopenxml.py E_X.st GVL_IO.st FB_X.st PRG_X.st -o Project.xml
   ```
   The converter finds this skill's compiler next to it in the skills folder. A ladder error names the network and points at the rung.
2. Read it back:
   ```bash
   python3 <codesys-lad-dir>/scripts/ld_trace.py Project.xml
   ```
   It prints each output as a boolean expression and warns about parallel branches the editor would rebuild in series. Check every coil against the intent.
3. For a sequence, test it in the scan simulator, `scripts/ld_sim.py`. It also runs other FBs through Python models (fake axes, fake MC_ blocks), and reads struct members and library constants; see **Simulating FBs** in `references/ladder.md`. It reads enums, constants and initial values from the XML, runs the networks scan by scan with timers, and lets a script set inputs and assert on any variable. `references/examples/traffic_light/test_traffic.py` is a full test plan written that way; copy its shape. Validate against the PLCopen schema with codesys-st's `scripts/validate_plcopen.py`.
4. Hand over the XML (Project → Import PLCopenXML…) with the ladder text, which is the readable form of the rungs, and list the build's warnings.

## ctrlX library and motion lookups

The library and motion references are shared with codesys-st, not copied. They're the same Rexroth manuals, in `<codesys-st-dir>/references/libs/` and `<codesys-st-dir>/references/motion/`. Look things up exactly as codesys-st's **ctrlX library lookups** and **Motion** sections describe: find the name in that folder's `INDEX.md`, then grep the file for its heading and read only that section.

In ladder, the lookup gives you the pins of an FB call. Every library FB except a timer runs on EN/ENO with its pins named, so take the input, `VAR_IN_OUT` and output names from the interface table and wire them all with `PIN := expr` / `PIN => var`, e.g. `-> fbPower:MC_Power(Enable := _bPowerCmd, Axis := stAxis1, Status => bPowered)`. The compiler only knows the pin lists of IEC standard FBs and of FBs in the files you build. For library FBs it can't check pin names or order, and it leaves out the `inputparamtypes` entry. So copy the names from the reference exactly, in the order the table lists them.

## Reference material

- `references/exports/codesys_v35sp15_ladder.xml`: a real CODESYS V3.5 SP15 LD export (from the public ascii-ladder project on CODESYS Forge, Unlicense). It shows networks, labels, set/reset coils, parallel branches and FB boxes. Use it with `ld_trace.py` to see how the editor writes a construct.
- `references/exports/ctrlx_math_compare.xml` and `ctrlx_other_operators.xml`: ctrlX PLC Engineering exports of ADD/SUB/MUL/DIV, all six compares, SEL, MUX, LIMIT and INT_TO_REAL. `scripts/ld_diff.py export.xml built.xml [POU]` compares LD bodies element by element; use it whenever you add a construct from a new export.
- **Regression tests:** `tests/run.sh` rebuilds every example and feature test (`tests/features/`), validates them and runs the tracer check. It also runs:
  - the traffic-light test plan;
  - the ladder `FB_AxisCtrl` test against fake MC_ models (`references/examples/press_tests/`);
  - simulator checks of declaration forms, struct MOVE, FB models, math, SEL/MUX/LIMIT, conversions and case-insensitive names;
  - the `ExampleMath` and `OtherOperators` rebuilds, diffed element for element against the real ctrlX exports;
  - operand-count checks (including MUX's 98-input limit) and a check that `ld_diff` catches a difference.

  Run it after changing `ladder.py`, `ld_sim.py`, `ld_trace.py` or `ld_diff.py`. When you add a construct from a new export, add the export to `references/exports/`, its ladder text to `tests/features/`, and an `ld_diff` line to `run.sh`.

When the editor shows something different from what was intended, ask the user for a small export of the same construct from ctrlX PLC Engineering and match it. `ld_trace.py` reads exports too.
