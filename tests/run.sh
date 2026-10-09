#!/usr/bin/env bash
# Regression test for the ladder compiler: builds every example and the feature test, checks
# each against the PLCopen schema and the tracer's ParallelBranch check, and runs the
# traffic light's test plan in the simulator. Exits non-zero on the first failure.
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
echo "ALL OK"
