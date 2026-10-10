#!/usr/bin/env bash
# Regression test for the codesys-lad scripts. Builds every example and feature test, checks each
# against the PLCopen schema and the tracer's ParallelBranch check, then:
#  - runs the traffic light's test plan and the FB_AxisCtrl test (fake MC_ models) in ld_sim;
#  - checks ld_sim features: VAR_IN_OUT CONSTANT/16# literals, struct MOVE, FB models, math;
#  - rebuilds ExampleMath and diffs it element for element against the real ctrlX export
#    (and checks ld_diff reports a difference when there is one).
# Exits non-zero on the first failure.
set -euo pipefail
LAD="$(cd "$(dirname "$0")/.." && pwd)"
ST="$LAD/../codesys-st/scripts"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

build() {   # build <name> <dir> <files...>
    local name=$1 dir=$2; shift 2
    if ! (cd "$dir" && python3 "$ST/st_to_plcopenxml.py" "$@" -o "$OUT/$name.xml" 2> "$OUT/$name.err"); then
        cat "$OUT/$name.err"; echo "FAIL: $name doesn't build"; exit 1
    fi
    grep -v "attribute" "$OUT/$name.err" || true
    python3 "$ST/validate_plcopen.py" "$OUT/$name.xml"
    if python3 "$LAD/scripts/ld_trace.py" "$OUT/$name.xml" | grep WARNING; then
        echo "FAIL: $name has parallel boxes without a ParallelBranch marker"; exit 1
    fi
}

build features "$LAD/tests/features" FB_Valve.st GVL_IO.st PRG_Conveyor.st FB_SimDecl.st
build cycle "$LAD/references/examples" E_CycleState.st FB_CycleLD.st
build traffic "$LAD/references/examples/traffic_light" E_TrafficState.st GVL_IO.st FB_TrafficLight.st PRG_Traffic.st
python3 "$LAD/references/examples/traffic_light/test_traffic.py" "$OUT/traffic.xml"
python3 - "$LAD/scripts" "$OUT/features.xml" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from ld_sim import Sim
s = Sim(sys.argv[2], "FB_SimDecl")
s.run(10, wLevel=0x100); hi = s.v["bAbove"]
s.run(10, wLevel=0xFF); lo = s.v["bAbove"]
assert s.consts["LIMIT"] == 255 and hi and not lo, (s.consts, hi, lo)
print("PASS sim reads VAR_IN_OUT CONSTANT and 16# literals")
PY
build math "$LAD/tests/features" ExampleMath.st
python3 "$LAD/scripts/ld_diff.py" "$LAD/references/exports/ctrlx_math_compare.xml" "$OUT/math.xml" ExampleMath
python3 - "$LAD/scripts" "$OUT/math.xml" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from ld_sim import Sim
s = Sim(sys.argv[2], "ExampleMath")
s.run(10, in1=7, in2=-2)
got = [s.v[s.key(k)] for k in ("out1", "out2", "out3", "out4", "equal", "neq", "LessThan", "GreaterThan")]
assert got == [5, 9, -14, -3, False, True, True, False], got
print("PASS sim ADD/SUB/MUL/DIV (DIV truncates toward zero) and compares")
PY
build axisctrl "$LAD/references/examples" press_tests/ST_Dynamics.st FB_AxisCtrl.st
python3 "$LAD/references/examples/press_tests/test_axisctrl.py" "$OUT/axisctrl.xml"

build simmodels "$LAD/tests/features" FB_SimModels.st
python3 - "$LAD/scripts" "$OUT/simmodels.xml" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from ld_sim import Sim

class Child:
    def __call__(self, pins, sim):
        return {"bBusy": pins["bRun"], "rOut": pins["rIn"] * 10}

s = Sim(sys.argv[2], "FB_SimModels", models={"FB_Child": Child})
s.v.update({"stCfg.rLimit": 5.0, "stCfg.rGain": 2.0})
s.run(10, rValue=3.0)
assert not s.v["bOver"] and s.v["_rScaled"] == 0, "config not latched yet: gain reads 0"
s.run(10, bLatch=True)
assert s.v["_stCfg.rLimit"] == 5.0 and s.v["_stCfg.rGain"] == 2.0, "struct MOVE copies members"
s.run(10)
assert s.v["_rScaled"] == 6.0 and s.v["bOver"], (s.v["_rScaled"], s.v["bOver"])
assert s.v["bBusy"] and s.v["rChild"] == 60.0, "model output via contact and =>"
print("PASS sim struct MOVE, struct compares, FB models, MUL")
PY

build otherops "$LAD/tests/features" OtherOperators.st
python3 "$LAD/scripts/ld_diff.py" "$LAD/references/exports/ctrlx_other_operators.xml" "$OUT/otherops.xml" OtherOperators
python3 - "$LAD/scripts" "$OUT/otherops.xml" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from ld_sim import Sim, convert
s = Sim(sys.argv[2], "OtherOperators")
# the export reads in1/in2 but declares In1/In2: names must resolve case-insensitively
s.run(10, bChoice=True, In1=10, In2=20, iMuxSel=2, in3=-7, in4=40, in5=50, minVal=-5, maxVal=5)
got = [s.v[k] for k in ("out1", "out2", "out3", "out4")]
assert got == [20, -7, -5, -7.0], got
s.run(10, bChoice=False, iMuxSel=0, in3=9)
assert [s.v["out1"], s.v["out2"], s.v["out3"], s.v["out4"]] == [10, 10, 5, 9.0]
try:
    s.run(10, iMuxSel=5); raise AssertionError("MUX out of range must raise")
except IndexError:
    pass
assert [convert("REAL_TO_INT", 2.5), convert("REAL_TO_INT", -2.5), convert("REAL_TO_INT", 2.4)] == [3, -3, 2]
assert convert("DINT_TO_INT", 40000) == -25536 and convert("INT_TO_UINT", -1) == 65535
assert convert("INT_TO_BOOL", 3) is True and convert("BOOL_TO_INT", True) == 1 and convert("INT_TO_LREAL", 4) == 4.0
print("PASS sim SEL/MUX/LIMIT, conversions (rounding, wrap, BOOL), case-insensitive names")
PY

# operand counts are checked
printf 'PROGRAM T\nVAR\n a:INT; b:INT; y:INT;\nEND_VAR\nNETWORK x\n    -> y := LIMIT(a, b)\nEND_PROGRAM\n' > "$OUT/arity.st"
if (cd "$OUT" && python3 "$ST/st_to_plcopenxml.py" arity.st -o "$OUT/arity.xml" 2> "$OUT/arity.err"); then
    echo "FAIL: LIMIT with 2 operands compiled"; exit 1
fi
grep -q "LIMIT takes exactly 3 operands, got 2" "$OUT/arity.err" && echo "PASS operand count checked" \
    || { cat "$OUT/arity.err"; echo "FAIL: wrong arity message"; exit 1; }

# MUX takes a selector and up to 98 inputs
python3 - "$OUT" "$ST" <<'PY'
import os, subprocess, sys
out, st = sys.argv[1], sys.argv[2]
def build(n):
    ins = ", ".join(f"i{k}" for k in range(n))
    src = ("PROGRAM M\nVAR\n k:INT; y:INT;\n" + "".join(f" i{k}:INT;\n" for k in range(n)) +
           f"END_VAR\nNETWORK x\n    -> y := MUX(k, {ins})\nEND_PROGRAM\n")
    open(os.path.join(out, "mux.st"), "w").write(src)
    return subprocess.run([sys.executable, os.path.join(st, "st_to_plcopenxml.py"), "mux.st", "-o", "mux.xml"],
                          cwd=out, capture_output=True, text=True)
assert build(98).returncode == 0, "MUX with 98 inputs must compile"
r = build(99)
assert r.returncode != 0 and "MUX takes 2 to 99 operands, got 100" in r.stderr, r.stderr
print("PASS MUX with 98 inputs compiles, 99 is rejected")
PY

# ld_diff must notice a real difference (a changed operand)
sed 's/out2 := SUB(in1, in2)/out2 := SUB(in2, in1)/' "$LAD/tests/features/ExampleMath.st" > "$OUT/ExampleMathBad.st"
(cd "$OUT" && python3 "$ST/st_to_plcopenxml.py" ExampleMathBad.st -o "$OUT/mathbad.xml" 2>/dev/null)
if python3 "$LAD/scripts/ld_diff.py" "$LAD/references/exports/ctrlx_math_compare.xml" "$OUT/mathbad.xml" ExampleMath > /dev/null; then
    echo "FAIL: ld_diff missed a changed operand"; exit 1
fi
echo "PASS ld_diff reports differences"
echo "ALL OK"
