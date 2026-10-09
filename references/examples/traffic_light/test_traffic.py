"""Run DESIGN.md's test plan against a built traffic light, in the scan simulator.

    python3 test_traffic.py TrafficLight.xml

Prints PASS/FAIL per case and exits non-zero on any failure. Every scan of every case is
also checked for safety: never green or yellow on both lanes, exactly one lamp per lane.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from ld_sim import Sim  # noqa: E402

STATES = ["AllRedToA", "GreenA", "YellowA", "AllRedToB", "GreenB", "YellowB"]
LAMPS = ["bRedA", "bYellowA", "bGreenA", "bRedB", "bYellowB", "bGreenB"]
TOL = 30                                    # ms: timers run one scan late in ladder
failures, safety = [], []


def new():
    return Sim(sys.argv[1], "FB_TrafficLight", scan_ms=10)


def state(s):
    n = s.v["_eState"]
    return STATES[n] if 0 <= n < len(STATES) else n


def changes(s, ms, **inputs):
    """Run ms; return [(time, state)] for each state change, checking lamp safety every scan."""
    s.v.update(inputs)
    log, last = [], getattr(s, "_last", None)
    for _ in range(ms // s.dt):
        s.scan()
        a = s.v["bYellowA"] or s.v["bGreenA"]
        b = s.v["bYellowB"] or s.v["bGreenB"]
        lit = [lamp for lamp in LAMPS if s.v[lamp]]
        if (a and b) or sum(lamp.endswith("A") for lamp in lit) != 1 or sum(lamp.endswith("B") for lamp in lit) != 1:
            safety.append(f"{s.now} ms: {lit}")
        if state(s) != last:
            log.append((s.now, state(s)))
            last = state(s)
    s._last = last
    return log


def check(n, ok, detail):
    print("PASS" if ok else "FAIL", n, detail)
    if not ok:
        failures.append(n)


def near(a, b):
    return abs(a - b) <= TOL


def names(log):
    return [st for _, st in log]


# 1 power-up: all red 2 s, then A green, which rests
s = new(); log = changes(s, 60000)
check(1, names(log) == ["AllRedToA", "GreenA"] and near(log[1][0], 2000), log)
# 2 car in B after the minimum green: yellow 6 s, all red 2 s, B green
s.v["bCarB"] = True; log = changes(s, 20000)
check(2, names(log) == ["YellowA", "AllRedToB", "GreenB"] and near(log[1][0] - log[0][0], 6000)
      and near(log[2][0] - log[1][0], 2000), log)
# 3 car in B 5 s into green: yellow exactly 30 s after green started
s = new(); changes(s, 2010); t0 = s.now; changes(s, 5000); s.v["bCarB"] = True
log = changes(s, 30000)
check(3, log and log[0][1] == "YellowA" and near(log[0][0] - t0, 30000), log)
# 4 car in B for 3 s, gone before 30 s: no change
s = new(); changes(s, 2010); changes(s, 10000); s.v["bCarB"] = True; changes(s, 3000); s.v["bCarB"] = False
log = changes(s, 60000)
check(4, log == [] and state(s) == "GreenA", log)
# 5 pedestrian tap for one scan at 10 s: change at 30 s, request cleared at B green
s = new(); changes(s, 2010); t0 = s.now; changes(s, 10000)
s.v["bPedButton"] = True; s.scan(); s.v["bPedButton"] = False
log = changes(s, 60000)
check(5, names(log) == ["YellowA", "AllRedToB", "GreenB"] and near(log[0][0] - t0, 30000)
      and not s.v["_bPedRequest"], log)
# 6 pedestrian tap during A yellow: B green, request cleared, B rests
s = new(); changes(s, 2010); s.v["bCarB"] = True; changes(s, 30010); s.v["bCarB"] = False
s.v["bPedButton"] = True; s.scan(); s.v["bPedButton"] = False
log = changes(s, 90000)
check(6, names(log) == ["AllRedToB", "GreenB"] and not s.v["_bPedRequest"], log)
# 7 cars in both lanes: alternate 30 / 6 / 2 s
s = new(); log = changes(s, 200000, bCarA=True, bCarB=True)
want = {"GreenA": 30000, "GreenB": 30000, "YellowA": 6000, "YellowB": 6000, "AllRedToA": 2000, "AllRedToB": 2000}
gaps = [(b[0] - a[0], a[1]) for a, b in zip(log, log[1:])]
check(7, len(log) > 8 and all(near(d, want[st]) for d, st in gaps), gaps[:6])
# 8 car only in the green lane: stays green
s = new(); log = changes(s, 120000, bCarA=True)
check(8, names(log) == ["AllRedToA", "GreenA"], log)
# 9 invalid state value: all red, then A green after 2 s
s = new(); changes(s, 40000); s.v["_eState"] = s.v["_eNextState"] = 17
log = changes(s, 5000)
check(9, names(log) == ["AllRedToA", "GreenA"] and near(log[1][0] - log[0][0], 2000), log)
# 10 every scan of every case above
check(10, not safety, safety[:3])

sys.exit(1 if failures else 0)
