# Ladder text (LD)

Ladder is written as plain text and compiled to a CODESYS LD body by codesys-st's `scripts/st_to_plcopenxml.py`, which loads this skill's `scripts/ladder.py`. A POU is ladder when its implementation starts with `NETWORK`. The declaration stays normal ST. ST and LD POUs can share one `.st` file and one run of the script.

```iecst
PROGRAM PRG_Conveyor
VAR
    bRun : BOOL;             // conveyor running
    bFault : BOOL;
    fbRunOn : TOF;           // fan run-on after stop
END_VAR

NETWORK Start/stop seal-in
// Stop is wired NC, so bDI_StopOk is TRUE when healthy
    (GVL_IO.bDI_Start | bRun) GVL_IO.bDI_StopOk /bFault -> bRun

NETWORK Fan run-on
    bRun fbRunOn(PT := T#5S) -> GVL_IO.bDO_Fan
END_PROGRAM
```

## Networks

- `NETWORK <title>` starts a network. The title is optional and shows as the CODESYS network title.
- `//` lines directly after the header, before the rung, become the network comment.
- `LABEL name` (before the rung) puts a jump label on the network.
- **One rung per network.** A rung may span several lines; they are joined. A trailing `// comment` on a rung line is dropped.
- A network with no rung is an empty network.

## Rung

```
rung := series [ '->' output { ',' output } ]
```

Power flows left to right. Elements written next to each other are in **series** (AND). `( a | b )` puts branches in **parallel** (OR), and each branch is itself a series, so groups nest: `(a b | c (d | /e)) f -> y`.

| Text | Element |
|---|---|
| `bX` | NO contact |
| `/bX` | NC contact |
| `P:bX` / `N:bX` | rising / falling edge contact |
| `[a > b]` | compare box: `>` `>=` `<` `<=` `=` `<>` on any two expressions |
| `( ... | ... )` | parallel branches |

Operands can be anything that names a BOOL: `GVL_IO.bDI_Start`, `aBits[3]`, `stStatus.bReady`, `wStatus.3`, `TRUE`.

**Outputs** after `->` are all in parallel on the rung's end:

| Text | Element |
|---|---|
| `bX` | coil |
| `/bX` | negated coil |
| `S:bX` / `R:bX` | set / reset coil |
| `rOut := expr` | MOVE box (EN from the rung) |
| `rOut := ADD(a, b)` | operator box: `ADD` `SUB` `MUL` `DIV` `SEL` `MUX` `LIMIT` `<type>_TO_<type>`, see **Operator boxes** |
| `fbX(...)` | FB call, see below |
| `JMP:label` | jump to a network's `LABEL` |
| `RET` | return |

A rung that starts with `->` is **unconditional**: its outputs hang straight off the left rail. Example: `-> _eState := _eNextState`.

## FB calls

There are three box forms, matching how the editor exports them:

| Box | Rung in | Rung out | Written as |
|---|---|---|---|
| Compare `[a > b]` | `EN` | `Out1` (rung AND result) | like a contact, anywhere in a rung |
| Timer (TON, TOF, TP, LTON, LTOF, LTP) | `IN` | `Q` | inline: `cond fbT(PT := T#5S) -> coil` |
| Any other FB | `EN` | `ENO` | `-> fbX(PIN := expr, PIN => var, ...)` |

```
instance(PIN := expr, PIN => var, ...)          type taken from the declarations
instance:TYPE(...)                               type given explicitly
```

- **The `(` must touch the name.** `fbT(...)` is a box. `bA (bB | bC)` is a contact followed by a group.
- **Timers:** the contacts in front of the timer are its `IN`, and the rung continues from `Q` into coils or more contacts. Name the other pins (`PT := ...`, `ET => ...`), but never `IN` or `Q`. The timer is still called every scan, because its rung always runs; only `IN` changes.
- **Other FBs run on EN/ENO**, and every pin is named: inputs (and `VAR_IN_OUT`s, e.g. `Axis := stAxis`) with `PIN := expr`, outputs with `PIN => var`. Write them as **unconditional rungs (`-> fbX(...)`)**: with EN off the FB isn't called at all, so an Execute/Done FB stops updating. Conditions go on its inputs. A pin takes a variable or a constant, so a condition built from contacts goes to a helper BOOL coil first. The compiler warns when such an FB's EN isn't on the rail.
- Read results through contacts on the outputs in later rungs (`_fbStepTimer.Q`, `fbMove.Done`), or wire them to variables with `=>`.
- Pins you don't mention stay unconnected. The pin names of TON/TOF/TP, CTU/CTD/CTUD, R_TRIG/F_TRIG, SR/RS, and any FB defined in the files passed to the script, are checked and put in declaration order.

```
bRun fbRunOn(PT := T#5S, ET => tElapsed) -> bRunOnDone
-> fbCount(CU := bSensor, RESET := bReset, PV := 100, Q => bBatchDone, CV => iCount)
-> fbPower:MC_Power(Enable := bEnable, Axis := stAxis1, Status => bPowered)
-> fbMove:MC_MoveAbsolute(Execute := _bMoveCmd, Axis := stAxis1, Position := lrTarget,
                          Velocity := lrVel, Done => bInPos, Error => bMoveErr)
```

## Operator boxes (math, selection, conversion)

`target := OP(operands)` goes after `->` like a MOVE. All of these become the same box ctrlX PLC Engineering exports: the rung goes in on `EN`, the operands go on `In2`, `In3`, … in order, and the result comes out on `Out2` to the target. Each one is verified element for element against a real export (`references/exports/ctrlx_math_compare.xml` and `ctrlx_other_operators.xml`, rebuilt from `tests/features/` by `tests/run.sh`).

| Text | Operands | Result |
|---|---|---|
| `y := ADD(a, b)` / `SUB` / `MUL` / `DIV` | 2 | a+b, a−b, a·b, a/b |
| `y := SEL(g, in0, in1)` | 3 | `in1` when `g` is TRUE, else `in0` |
| `y := MUX(k, in0, in1, …)` | selector + up to 98 inputs | input number `k` (0-based) |
| `y := LIMIT(mn, x, mx)` | 3 | `x` clamped to `mn` … `mx` |
| `y := INT_TO_REAL(x)`, any `<type>_TO_<type>` | 1 | converted value |

```
NETWORK Advance target
    -> _lrAdvanceTarget := ADD(_stSp.lrTransferHome, _stSp.lrPitch)

NETWORK Lift target
    -> _lrLiftTarget := SEL(_bStLifting, _stSp.lrLiftDown, _stSp.lrLiftUp)

NETWORK Raw to REAL
    -> _rRaw := INT_TO_REAL(iRaw)

NETWORK Scale (only when the span is not zero)
    /_bZeroSpan -> _rScaled := DIV(_rNum, _rSpan)
```

- **Operands** are variables, struct members or literals, never expressions. Nest by chaining through intermediate variables, **one box per network**. Several boxes on one rung's outputs run in parallel off the rung, so one can't use another's result in the same network.
- **The rung is EN**: with the rung off, the target keeps its last value, like a MOVE.
- **The operand count is checked** at compile time (e.g. "LIMIT takes exactly 3 operands, got 2").
- **DIV by zero** is a PLC exception for integers, or Inf/NaN for REAL. Guard the divisor in the rung: `[rSpan <> 0.0] -> rOut := DIV(rNum, rSpan)`. Integer `DIV` truncates toward zero (7 / -2 = -3).
- **MUX** with `k` outside 0 … n−1 gives an undefined result on the PLC. Clamp `k` first with `LIMIT`.
- **Operand types must match** for ADD/SUB/MUL/DIV/SEL/MUX/LIMIT (INT with INT, REAL with REAL). Convert first with `<type>_TO_<type>`. The conversion is chosen from the name, e.g. `INT_TO_REAL`, `REAL_TO_DINT`, `DINT_TO_INT`, `BOOL_TO_INT`, `INT_TO_BOOL`. REAL → integer rounds to the nearest (half away from zero), and a narrowing integer conversion wraps (`DINT_TO_INT(40000) = -25536`).
- `ld_trace.py` prints math infix (`y := a + b`) and the others as calls (`y := SEL(g, a, b)`), and `ld_sim.py` simulates them all.

## Compares

`[...]` behaves exactly like a contact and can go anywhere a contact can. It becomes a compare box in the rung: the rung goes in on `EN`, and power goes on out of `Out1` only when the rung is powered **and** the comparison is true.

```
[rTemp > rTempMax] -> S:bOverTemp
bAuto [rLevel < 10.0] -> bFill
```

**Never put a compare in a parallel branch.** ctrlX PLC Engineering has imported `([a = 1] | [a = 2]) -> y` with the compares in series (an AND). Decode instead: one compare per rung into a BOOL, then contacts in the logic.

```
NETWORK Decode Clamping
    [_eState = E_X.Clamping] -> _bStClamping
NETWORK Decode Working
    [_eState = E_X.Working] -> _bStWorking
NETWORK Out bClampCmd
    (_bStClamping | _bStWorking) -> bClampCmd
```

The compiler warns when a compare sits in a parallel branch.

## Sequences

A ladder sequence uses the same sections as the ST house structure in codesys-st's `references/patterns.md` §1, in the same order. Read §1 first, because the reasons for the order carry over. Ladder has no `IF`/`CASE` and every rung runs every scan, so it adds two things:

- **`_eNextState`.** Jumps and transitions never write `_eState`. They write `_eNextState` with a MOVE (`-> _eNextState := E_X.Working`).
- **A commit after each section that can change state.** The network `-> _eState := _eNextState` follows the jumps and follows the transitions. That gives the same behaviour as the ST version: the transitions see the state the jumps chose, and on-change sees the final state. Every commit leaves `_eNextState = _eState`, so a section in which nothing fires changes nothing.

The order of networks, each section a run of networks:

| # | Section | Networks |
|---|---|---|
| 1 | **Jumps** | One network per jump, highest priority first. Each rung starts `[_eState <> E_X.Faulted]`, and locks out the jumps above it with their conditions negated (`/bExternalFault /_fbStepTimer.Q bAbort ...`), which is the ELSIF chain. A jump that records a fault writes the code and state on the same rung: `-> _eNextState := E_X.Faulted, _uiFaultCode := FAULT_X, _eFaultState := _eState`. |
| | commit | `-> _eState := _eNextState` |
| 2 | **Transitions** | One network per transition: `[_eState = E_X.Idle] bExecute /bAbort -> _eNextState := E_X.Clamping`. Every one reads `_eState`, never `_eNextState`, so transitions don't chain within a scan, just like a `CASE`. If one state has two exits, lock them out from each other (`/cond`), because whichever writes last would otherwise win silently. One compare per rung: a jump or transition that applies in two states is two networks. The last transition network is the `CASE ELSE`: `[_eState > E_X.<last state>] -> _eNextState := E_X.Faulted, _uiFaultCode := FAULT_INVALID_STATE, _eFaultState := _eState`. |
| | commit | `-> _eState := _eNextState` |
| | decode | One network per state: `[_eState = E_X.Working] -> _bStWorking`. From here on, the logic uses contacts on these BOOLs, so no compare ever sits in a parallel branch. They hold until the end of the scan, because nothing changes `_eState` after the last commit. |
| 3 | **On change** | `[_eState <> _eLastState] -> _bStateChanged` (a coil, so it's TRUE only on the change scan). Then the common actions on `_bStateChanged`, then one entry network per state: `_bStateChanged _bStWorking -> _tStepTimeout := WORK_TIMEOUT`. Close the section with `-> _eLastState := _eState`. |
| 4 | **Cyclic** | First every FB call: timers inline with their condition as the rung (`/_bStateChanged _fbStepTimer(PT := ...)`), other FBs on unconditional EN/ENO rungs with inputs driven from the state through helper bits set in earlier networks (`-> fbMove(Execute := _bMoveCmd, ...)`). Then the outputs, last: one coil per output, as contacts on the decoded state (`(_bStClamping \| _bStWorking) -> bClampCmd`). Then one unconditional rung that copies the internal values out (`-> eState := _eState, uiFaultCode := _uiFaultCode`). |

Notes:
- **Naming.** Title each network by its section (`J1 External fault`, `T Idle -> Clamping`, `Entry Working`, `Out bClampCmd`), so the online view reads like the ST layout.
- **Step timer.** ST resets the step timer inside the on-change section. Ladder holds its IN off for the change scan instead: `[_tStepTimeout > T#0S] /_bStateChanged _fbStepTimer(PT := _tStepTimeout)`. The `> T#0S` keeps a step with no timeout from timing out at once; leave it out when every step has a time. So the timeout starts one scan later than in ST, which doesn't matter for second-scale timeouts.
- **Writers.** `_eNextState`, `_tStepTimeout` and the fault fields are each written by several MOVEs, the way ST assigns `_eState` in many CASE branches. They're internal registers, not outputs. Every real output still has exactly one coil.
- **`_eState > last state`** needs the states to be numbered in order, with the last one highest. Keep `Faulted` (or whatever is last) at the end of the enum.

The full worked example is `references/examples/FB_CycleLD.st`: the `FB_Cycle` from codesys-st's `patterns.md` §1 in ladder. It uses the `E_CycleState` enum from that section. Start from it when writing a ladder sequence. `references/examples/traffic_light/` is a second, complete example: a design doc (`DESIGN.md`), a ladder sequence FB with demand-driven transitions, and a program that calls it on EN/ENO.

## When to use ladder

Use ladder when the user asks for it, or for logic electricians read online: interlocks, permissives, seal-ins, simple timers and counters, I/O mapping. Calculations and anything with loops stay in ST. Sequences can be ladder when the user wants them, but must use the structure in **Sequences** above. A ladder POU can still follow the house rules: one writer per output, and outputs written in the last networks.

## Converting ST to ladder (all-ladder projects)

When a customer wants "all ladder unless it must be ST", these points have been worked out:

- **Math, selection and type conversion are ladder.** The operator boxes (see **Operator boxes**) cover formulas like linear scaling with a raw INT: `INT_TO_REAL`, then SUB, MUL and a guarded DIV, one box per network through intermediate variables. `SEL`/`MUX`/`LIMIT` replace entry-MOVE workarounds and clamping logic. Compute targets directly (e.g. advance to `ADD(home, pitch)` with an absolute move) instead of designing the math away with relative moves. A MOVE's value still goes into the XML as raw text, so keep it to a variable, a struct member or a constant, never an expression.
- **What still stays ST:** loops, string handling, and calling your own FUNCTIONs from a rung (not supported). Put these in a small **ST function block** called on EN/ENO, with the reason in its header comment.
- **Small validation functions** (e.g. `Fn_DynValid`) become one rung of compares in series into a BOOL, which is allowed. Split a long chain over two rungs plus an AND rung.
- **IF/ELSIF latches** (first error wins): put the clear rung first. Then each latch rung is `/_bError cause -> S:_bError, _eErrorID := ..., _dwDiag := ...`. The set coil locks out the rungs below in the same scan, which is the ELSIF.
- **`NOT (a AND b)` on a pin** goes into a helper coil: `bPower (/_fbPower.Error | /bReset) -> _bPowerEnable`.
- **Entry MOVEs that depend on a latch** (`_stSp := stSp`, then `_lrTarget := _stSp.x`) go in **separate networks**, latch first. Don't rely on the order of parallel outputs on one rung.
- **A jump that applies in several states** (e.g. overpressure only while closing): use the decode bits. They still hold the state the scan started in, because nothing changes `_eState` between the last decode and the next scan's jumps. Build a helper coil before the jumps: `_bOverPressure (_bStApproaching | _bStPressing) -> _bTrip`. Never use decode bits in the transitions, which have to see the state after the jump commit.
- **Re-edge a move FB between consecutive move steps**: `/_bStateChanged (_bStA | _bStB) -> _bMove`.
- `references/examples/FB_AxisCtrl.st` is a complete ladder MC_ axis wrapper, and `references/examples/press_tests/` has its simulator test with fake MC_ models.

## Simulating FBs, structs and library constants (ld_sim)

`Sim(xml, pou, models={...}, consts={...})` handles:
- **FB boxes** other than TON (your own FBs, MC_ FBs) run through Python models. The type name maps to a class, one object is created per instance, and it's called as `model(pins, sim)` and returns its outputs. The outputs are readable as `inst.pin` (nested too: `"ErrorIdent.Additional1"`) and are written to `PIN => var`. Use this to test a sequence against a fake axis, e.g. one where moves take N scans, halts take M scans, and errors can be injected.
- **Structs** are flat dotted keys: `sim.v["stSp.lrPitch"] = 250.0`. An unset member reads 0, and `MOVE _stSp := stSp` copies every member.
- **Names are case-insensitive**, as in IEC: `in1` reads the declared `In1`. Use `sim.key(name)` for the declared spelling when reading back.
- **Library constants** (`ERROR_CODE.DEVICE_ERROR`, `MC_BUFFER_MODE.mcAborting`) go in `consts`.
- `run(ms)` runs `ms / scan_ms` scans, so `run(10)` at the default 10 ms is **one scan**. Give a multi-scan fake enough time.
- **Make fakes realistic about time.** A halt that completes instantly hides logic that only runs during the halting step.

## Checking the result

After generating, read the XML back:

```bash
python3 <codesys-lad-dir>/scripts/ld_trace.py Project.xml
```

It prints each coil as a boolean expression, e.g. `bRun := (bDI_Start OR bRun) AND bDI_StopOk AND NOT bFault`. Compare that against the intent before handing the file over.

## How it maps to PLCopenXML

This follows real LD exports from CODESYS V3.5 SP15 and ctrlX PLC Engineering 3.6.5:
- every element is at position 0,0, because CODESYS lays out LD itself from the connections;
- one `leftPowerRail` (localId 0) is shared by all networks;
- each network opens with a `comment` and a `vendorElement` whose `fbdelementtype` is `networktitle`;
- parallel branches are several `<connection>`s on one `connectionPointIn`. When a parallel group holds a box (a compare or an FB call), the compiler also adds a `vendorElement` with an `ldparallelbranch` `ParallelBranch mode="sce"` marker, listing the branch input and each branch's end, after the branches. The editor needs it when every branch holds a box: without it, it chains those boxes in series and the OR becomes an AND. `ld_trace.py` warns when that marker is missing;
- A box's pins other than the rung pins (`EN`/`ENO`, a timer's `IN`/`Q`, a compare's `EN`/`Out1`) never connect to contacts or coils: inputs come from `inVariable` elements, and outputs go to variables through `<connectionPointOut><expression>`. A box gets its localId **before** its pin `inVariable`s, even though they're written before it in the file; that's how the editor numbers them. Outputs wired to variables use `<connectionPointOut><expression>`, and inputs use `inVariable` elements. Every output pin of a known FB is listed; an unused one has an empty `<expression/>`;
- compare boxes (`EQ`, `NE`, `GT`, `GE`, `LT`, `LE`) sit in the rung: inputs `EN` (the rung), `In2`, `In3`, and output `Out1`, which feeds the next element (`formalParameter="Out1"` on that connection);
- MOVE has inputs `EN` (the rung) and `In2` (the value), and outputs `ENO` and `Out2`, whose `<expression>` is the target variable;
- the other operator boxes (ADD/SUB/MUL/DIV, SEL, MUX, LIMIT, `<type>_TO_<type>`) are the same with more operands: inputs `EN`, `In2`, `In3`, … (one per operand), outputs `ENO`, `Out2`, calltype `operator`, `InputParamTypes` `BOOL`, and no instance name (from ctrlX PLC Engineering exports);
- FB calls have their rung pin first among the inputs (`EN`, or `IN` for a timer) and first among the outputs (`ENO`, or `Q`), then the named pins;
- every block carries `fbdcalltype` (`operator` or `functionblock`) and `inputparamtypes` in its `addData`. Operators get `BOOL`. FBs get their input types, space-separated in pin order, the rung pin first (TON: `BOOL TIME`, as exported). For EN/ENO FBs that means `BOOL` for EN, then the inputs; that form is inferred, not seen in an export. The entry is left out when the FB's interface isn't known;
- a `rightPowerRail` (localId 2147483646) closes the body.

When the editor produces something the compiler doesn't, build a small example in the editor, export it, and copy its form. `ld_trace.py` reads exported LD, so it shows what the example means.
