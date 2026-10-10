"""Scan-by-scan test of the ladder FB_AxisCtrl (../FB_AxisCtrl.st) with fake CXA_PLCopen FBs.

    python3 test_axisctrl.py <built.xml>     (tests/run.sh builds it from ST_Dynamics.st + ../FB_AxisCtrl.st)

Also a worked example of ld_sim models: one Python class per FB type, struct members, nested
outputs (ErrorIdent.Additional1) and library constants.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from ld_sim import Sim  # noqa: E402

XML = sys.argv[1]
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        fails.append(name)


AX = {"errorstop": False, "power_error": False, "status_error": False}   # shared fake axis state
CONSTS = {"ERROR_CODE.NONE_ERROR": 0, "ERROR_CODE.DEVICE_ERROR": 8, "MC_BUFFER_MODE.mcAborting": 0}


def err(flag, add1=0x090F2001, add2=0x0C570100):
    return {"Error": flag, "ErrorID": 8 if flag else 0,
            "ErrorIdent.Additional1": add1 if flag else 0, "ErrorIdent.Additional2": add2 if flag else 0}


class Power:
    def __init__(self): self.n = 0; self.last = False; self.err = False
    def __call__(self, p, sim):
        if p["Enable"] and not self.last:
            self.err = AX["power_error"]          # error decided on the edge, held until Enable drops
        if not p["Enable"]:
            self.err = False
        self.last = p["Enable"]
        self.n = self.n + 1 if p["Enable"] and not self.err else 0
        return {"Status": self.n >= 2, **err(self.err)}


class Status:
    def __call__(self, p, sim):
        e = p["Enable"] and AX["status_error"]
        return {"Valid": p["Enable"] and not e, "ErrorStop": p["Enable"] and AX["errorstop"],
                "Standstill": p["Enable"] and not AX["errorstop"], **err(e)}


class ActPos:
    def __call__(self, p, sim):
        return {"Valid": p["Enable"], "Position": 12.5 if p["Enable"] else 0.0, **err(False)}


class Reset:
    def __init__(self): self.calls = 0
    def __call__(self, p, sim):
        if p["Execute"]:
            self.calls += 1
            AX["errorstop"] = False
        return {"Done": p["Execute"], "Active": False, **err(False)}


class Move:
    def __init__(self): self.last = False; self.left = None; self.edges = 0
    def __call__(self, p, sim):
        if p["Execute"] and not self.last:
            self.edges += 1; self.left = 3
        if not p["Execute"]:
            self.left = None
        elif self.left:
            self.left -= 1
        self.last = p["Execute"]
        return {"Done": p["Execute"] and self.left == 0, "Active": bool(self.left), **err(False)}


class Halt:
    def __init__(self): self.execs = 0
    def __call__(self, p, sim):
        self.execs += bool(p["Execute"])
        return {"Done": p["Execute"], "Active": False, **err(False)}


s = Sim(XML, "FB_AxisCtrl", models={"MC_Power": Power, "MC_ReadStatus": Status, "MC_ReadActualPosition": ActPos,
                                    "MC_Reset": Reset, "MC_MoveAbsolute": Move,
                                    "MC_Halt": Halt}, consts=CONSTS)

s.run(500, bPower=True)
check("power: bPowered, actual position read", s.v["bPowered"] and s.v["lrActPos"] == 12.5)

s.run(100, bMove=True)
check("move abs: bInPos after Done", s.v["bInPos"])
s.run(100, bMove=False)
check("move abs: bInPos drops with the command (gated Done)", not s.v["bInPos"])

# Drive error while moving: ErrorStop latches DEVICE_ERROR; move is blocked; reset runs MC_Reset and clears
AX["errorstop"] = True
s.run(200, bMove=True)
check("errorstop: bError latched with DEVICE_ERROR", s.v["bError"] and s.v["eErrorID"] == 8)
check("errorstop: halt not executed in ErrorStop", s.instances["_fbHalt"].execs == 0 or not s.v["_bHaltExecute"])
moves = s.instances["_fbMove"].edges
s.run(200, bMove=False, bReset=True)
check("errorstop: reset ran MC_Reset and cleared the error", not s.v["bError"] and s.instances["_fbReset"].calls > 0
      and s.v["eErrorID"] == 0)
s.run(100, bReset=False)
check("errorstop: no move issued while in error", s.instances["_fbMove"].edges == moves)

# Power error (e.g. motion not RUNNING): latched with the ctrlX diagnosis; reset re-edges Enable and recovers
s.run(100, bPower=False)
AX["power_error"] = True
s.run(200, bPower=True)
check("power error: latched with diagnosis 090F2001/0C570100",
      s.v["bError"] and s.v["dwDiagMain"] == 0x090F2001 and s.v["dwDiagDetail"] == 0x0C570100,
      (s.v["bError"], hex(s.v["dwDiagMain"])))
AX["power_error"] = False
s.run(300, bReset=True)
s.run(300, bReset=False)
check("power error: reset re-edges Enable, powered and error cleared", s.v["bPowered"] and not s.v["bError"],
      (s.v["bPowered"], s.v["bError"]))

# First error is kept: a later error doesn't overwrite the latched diagnosis
AX["status_error"] = True
s.run(100)
first = s.v["dwDiagMain"]
AX["errorstop"] = True
s.run(100)
check("first error kept", s.v["dwDiagMain"] == first and first == 0x090F2001)
AX.update(status_error=False, errorstop=False)
s.run(300, bReset=True); s.run(100, bReset=False)

# Halt on a powered healthy axis
s.run(100, bHalt=True)
check("halt: executed and bHalted", s.v["bHalted"] and s.instances["_fbHalt"].execs > 0)

raise SystemExit(1 if fails else 0)
