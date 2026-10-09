"""Scan-cycle simulator for a ladder POU in a PLCopenXML file, for testing logic before import.

Import it from a test script:

    import sys; sys.path.insert(0, "<codesys-lad-dir>/scripts")
    from ld_sim import Sim
    sim = Sim("Project.xml", "FB_TrafficLight", scan_ms=10)
    sim.run(5000, bCarB=True)          # set inputs, then run 5 s of scans
    sim.v["bGreenB"], sim.v["_eState"]  # read any variable

Each scan runs the networks top to bottom, as the PLC does. Enum values, VAR CONSTANTs and
initial values are read from the XML. Supported: contacts (not edge contacts), coils
(normal, negated, set, reset), compare boxes (EQ/NE/GT/GE/LT/LE), MOVE, and TON. Anything
else raises, so a test can't pass by silently skipping logic.

It checks logic, not the import: how the editor rebuilds a network (see ld_trace.py's
ParallelBranch warning) isn't simulated.
"""
import re
import xml.etree.ElementTree as ET

P = "{http://www.plcopen.org/xml/tc6_0200}"
COMPARE = {"EQ": lambda a, b: a == b, "NE": lambda a, b: a != b, "GT": lambda a, b: a > b,
           "GE": lambda a, b: a >= b, "LT": lambda a, b: a < b, "LE": lambda a, b: a <= b}


def tag(e):
    return e.tag.split("}")[1]


class Sim:
    def __init__(self, path, pou, scan_ms=10):
        root = ET.parse(path).getroot()
        self.dt = scan_ms
        self.now = 0
        self.enums = {}
        for dt in root.iter(f"{P}dataType"):
            for v in dt.iter(f"{P}value"):
                self.enums[f"{dt.get('name')}.{v.get('name')}"] = int(v.get("value"))
                self.enums.setdefault(v.get("name"), int(v.get("value")))
        node = next((x for x in root.iter(f"{P}pou") if x.get("name") == pou), None)
        if node is None:
            raise ValueError(f"no POU {pou} in {path}")
        self.ld = list(node.find(f"{P}body/{P}LD"))
        self.v, self.consts, self.timers = {}, {}, {}
        blocks = list(node.find(f"{P}interface"))
        # VAR CONSTANT is a constant localVars block. VAR_IN_OUT CONSTANT is also flagged
        # constant="true" but is a read-only reference with no initial values: a variable.
        def is_const(b):
            return b.get("constant") == "true" and tag(b) != "inOutVars"

        # Constants first: initial values may use them (VAR CONSTANT comes after VAR)
        for block in sorted(blocks, key=lambda b: not is_const(b)):
            for var in block.findall(f"{P}variable"):
                name, t = var.get("name"), var.find(f"{P}type")
                is_bool = t is not None and t.find(f"{P}BOOL") is not None
                init = var.find(f"{P}initialValue/{P}simpleValue")
                if is_const(block):
                    self.consts[name] = self.literal(init.get("value"))
                elif init is not None:
                    self.v[name] = self.literal(init.get("value"))
                else:
                    self.v[name] = False if is_bool else 0

    def literal(self, s):
        """Value of an expression on a pin or contact: a variable, constant or literal."""
        s = s.strip()
        if s.upper() in ("TRUE", "FALSE"):
            return s.upper() == "TRUE"
        if m := re.fullmatch(r"T#(?:(\d+)S)?(?:(\d+)MS)?", s, re.I):
            return int(m.group(1) or 0) * 1000 + int(m.group(2) or 0)
        if m := re.fullmatch(r"(2|8|16)#([0-9A-Fa-f_]+)", s):
            return int(m.group(2).replace("_", ""), int(m.group(1)))
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d*", s):
            return float(s)
        if s in self.enums:
            return self.enums[s]
        if s in self.consts:
            return self.consts[s]
        if m := re.fullmatch(r"(\w+)\.(Q|ET)", s):
            return self.timers.get(m.group(1), {"Q": False, "ET": 0})[m.group(2)]
        if s in self.v:
            return self.v[s]
        raise KeyError(f"unknown name or literal '{s}' (only local variables are simulated)")

    def scan(self):
        flow = {}

        def source(cpi):
            """Value arriving on a connection point: one source as is, several ORed."""
            vals = []
            for c in cpi.findall(f"{P}connection"):
                r = flow[c.get("refLocalId")]
                vals.append(r[c.get("formalParameter")] if isinstance(r, dict) else r)
            return vals[0] if len(vals) == 1 else any(vals)

        for e in self.ld:
            t, lid = tag(e), e.get("localId")
            if t == "leftPowerRail":
                flow[lid] = True
            elif t == "inVariable":
                flow[lid] = self.literal(e.findtext(f"{P}expression"))
            elif t == "contact":
                if e.get("edge", "none") != "none":
                    raise NotImplementedError("edge contacts aren't simulated")
                x = bool(self.literal(e.findtext(f"{P}variable")))
                flow[lid] = bool(source(e.find(f"{P}connectionPointIn"))) and (x != (e.get("negated") == "true"))
            elif t == "coil":
                on, var = bool(source(e.find(f"{P}connectionPointIn"))), e.findtext(f"{P}variable")
                storage = e.get("storage")
                if storage == "set":
                    self.v[var] = self.v.get(var, False) or on
                elif storage == "reset":
                    self.v[var] = self.v.get(var, False) and not on
                else:
                    self.v[var] = on != (e.get("negated") == "true")
            elif t == "block":
                flow[lid] = self.block(e, source)
            elif t in ("jump", "return"):
                raise NotImplementedError(f"{t} isn't simulated")
        self.now += self.dt

    def block(self, e, source):
        pins = {v.get("formalParameter"): source(v.find(f"{P}connectionPointIn"))
                for v in e.findall(f"{P}inputVariables/{P}variable")}
        typ = e.get("typeName")
        if typ in COMPARE:
            return {"Out1": bool(pins["EN"]) and COMPARE[typ](pins["In2"], pins["In3"])}
        if typ == "MOVE":
            if pins["EN"]:
                target = next(v.findtext(f"{P}connectionPointOut/{P}expression")
                              for v in e.findall(f"{P}outputVariables/{P}variable")
                              if v.get("formalParameter") == "Out2")
                self.v[target] = pins["In2"]
            return {"ENO": bool(pins["EN"])}
        if typ == "TON":
            tm = self.timers.setdefault(e.get("instanceName"), {"Q": False, "ET": 0})
            if pins.get("EN") is False:
                return {"ENO": False, **tm}
            if pins["IN"]:
                tm["ET"] = min(tm["ET"] + self.dt, pins["PT"])
                tm["Q"] = tm["ET"] >= pins["PT"]
            else:
                tm["ET"], tm["Q"] = 0, False
            for v in e.findall(f"{P}outputVariables/{P}variable"):
                target = v.findtext(f"{P}connectionPointOut/{P}expression")
                if target and v.get("formalParameter") in tm:
                    self.v[target] = tm[v.get("formalParameter")]
            return {"ENO": True, **tm}
        raise NotImplementedError(f"{typ} boxes aren't simulated")

    def run(self, ms, **inputs):
        """Set inputs, then run scans for ms milliseconds."""
        self.v.update(inputs)
        for _ in range(ms // self.dt):
            self.scan()
