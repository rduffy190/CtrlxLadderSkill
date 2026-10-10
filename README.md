# codesys-lad

A [Claude Code](https://claude.com/claude-code) skill for writing **ladder diagram (LD)** for Bosch Rexroth **ctrlX CORE** (ctrlX PLC Engineering) and other CODESYS V3 controllers.

The CODESYS LD editor can't paste text, so Claude writes ladder in a small plain-text rung language and compiles it into a PLCopenXML file for **Project → Import PLCopenXML…**:

```
NETWORK Start/stop seal-in
    (bStart | bRun) /bStop /bFault -> bRun

NETWORK Run-on timer
    bRun fbRunOn(PT := T#5S) -> bRunOnDone

NETWORK Valve
    -> fbValve(bOpen := _bOpenCmd, rSetpoint := rSp, bOpened => bValveOpen)

NETWORK Advance target
    -> rTarget := ADD(rHome, rPitch)
```

It handles contacts, coils, set/reset, compares, MOVE, operator boxes (ADD/SUB/MUL/DIV, SEL, MUX, LIMIT, `<type>_TO_<type>` conversions), timers, FB calls on EN/ENO, jumps, and ladder state machines in the house sequence structure. The XML format follows real exports from CODESYS V3.5 SP15 and ctrlX PLC Engineering 3.6.5 / 4.6.2, and the operator boxes are checked element for element against ctrlX exports.

## Requires codesys-st

This skill is an add-on to [codesys-st](https://github.com/rduffy190/CtrlxPlcSkill) and doesn't work without it. codesys-st provides:

- the house rules (naming, sequence structure) this skill follows;
- `st_to_plcopenxml.py`, the converter that builds the import file and loads this skill's compiler for ladder POUs;
- the ctrlX library and Motion App references used to look up FB pins.

## Install

Clone both into your Claude Code skills folder, side by side, under these exact names:

```bash
git clone git@github.com:rduffy190/CtrlxPlcSkill.git    ~/.claude/skills/codesys-st
git clone git@github.com:rduffy190/CtrlxLadderSkill.git ~/.claude/skills/codesys-lad
~/.claude/skills/codesys-lad/tests/run.sh               # should end with ALL OK
```

Ask Claude for ladder ("write the start/stop logic in ladder") and it's used.

Requirements: Python 3.10+, and `lxml` for the schema check that `tests/run.sh` runs (`pip install lxml`).

## What's inside

| Path | Contents |
|---|---|
| `SKILL.md` | The skill: when to use it, how to write, build and check ladder |
| `references/ladder.md` | The ladder text language, the three box forms, ladder sequences, and the XML mapping |
| `references/examples/FB_CycleLD.st` | codesys-st's clamp/work/unclamp sequence, in ladder |
| `references/examples/traffic_light/` | A complete example: design doc, ladder FB and program, and a test plan |
| `references/examples/FB_AxisCtrl.st`, `press_tests/` | A ladder ctrlX MC_ axis wrapper (power, move, halt, reset, latched diagnosis) and its simulator test with fake MC_ blocks |
| `references/exports/` | Real LD exports used as format references: a CODESYS V3.5 SP15 export (third-party) and ctrlX PLC Engineering exports of the operator boxes and compares |
| `scripts/ladder.py` | The compiler (loaded by codesys-st's converter) |
| `scripts/ld_trace.py` | Reads LD from any PLCopenXML file back as one boolean expression per output |
| `scripts/ld_sim.py` | Scan-cycle simulator for testing ladder logic before import, with Python models for other FBs (e.g. fake axes) |
| `scripts/ld_diff.py` | Compares the LD bodies of two PLCopenXML files element by element (compiler output vs. a real export) |
| `tests/run.sh`, `tests/features/` | Regression suite: builds, validates, traces and simulates every example and feature test, and diffs rebuilt exports against the real ones |

## Building and checking an import file yourself

```bash
python3 ~/.claude/skills/codesys-st/scripts/st_to_plcopenxml.py E_State.st GVL_IO.st FB_Seq.st PRG_Main.st -o Project.xml
python3 ~/.claude/skills/codesys-lad/scripts/ld_trace.py Project.xml
```

The tracer also works on ladder exported from CODESYS, which makes it handy for comparing what the editor did with what was meant.

## License

MIT, except `references/exports/codesys_v35sp15_ladder.xml`, which keeps its original Unlicense terms. See [LICENSE](LICENSE).
