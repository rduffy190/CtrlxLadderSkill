"""Scan-cycle simulator for a ladder POU in a PLCopenXML file, for testing logic before import.

Import it from a test script:

    import sys; sys.path.insert(0, "<codesys-lad-dir>/scripts")
    from ld_sim import Sim
    sim = Sim("Project.xml", "FB_TrafficLight", scan_ms=10)
    sim.run(5000, bCarB=True)          # set inputs, then run 5 s of scans
    sim.v["bGreenB"], sim.v["_eState"]  # read any variable

Each scan runs the networks top to bottom, as the PLC does. Enum values, VAR CONSTANTs and
initial values are read from the XML. Supported: contacts (not edge contacts), coils
(normal, negated, set, reset), compare boxes (EQ/NE/GT/GE/LT/LE), MOVE, ADD/SUB/MUL/DIV, SEL/MUX/LIMIT,
<type>_TO_<type> conversions and TON. Anything
else raises, so a test can't pass by silently skipping logic.

Other FB boxes (your own FBs, MC_ motion FBs...) run through Python models you pass in:

    class FakeAxis:                      # one object per instance, created on first call
        def __call__(self, pins, sim):   # pins: input name -> value (EN included)
            return {"bInPos": pins["bMove"], "bPowered": pins["bPower"]}
    sim = Sim("Project.xml", "FB_X", models={"FB_AxisCtrl": FakeAxis})

The returned outputs are readable as contacts/expressions ('_fbLift.bInPos') and are written
to any variable wired with 'PIN => var'. An FB box whose EN is off isn't called.

Struct members are flat dotted names: sim.v["stSp.lrPitch"] = 100.0. An unset member of a
declared variable reads 0, and MOVE of a struct (_stSp := stSp) copies every member.
Constants that come from libraries (e.g. ERROR_CODE.DEVICE_ERROR) go in consts={...}.

It checks logic, not the import: how the editor rebuilds a network (see ld_trace.py's
ParallelBranch warning) isn't simulated.
"""
import re
import xml.etree.ElementTree as ET

P = "{http://www.plcopen.org/xml/tc6_0200}"
COMPARE = {"EQ": lambda a, b: a == b, "NE": lambda a, b: a != b, "GT": lambda a, b: a > b,
           "GE": lambda a, b: a >= b, "LT": lambda a, b: a < b, "LE": lambda a, b: a <= b}


def _div(a, b):
    """IEC DIV: integers truncate toward zero; division by zero raises (it's a PLC exception too)."""
    if b == 0:
        raise ZeroDivisionError("DIV by zero in the ladder (the PLC would throw an exception)")
    if isinstance(a, int) and isinstance(b, int):
        return int(a / b)
    return a / b


def _mux(k, *ins):
    if not 0 <= k < len(ins):
        raise IndexError(f"MUX selector {k} out of range 0..{len(ins) - 1} (the PLC result is undefined)")
    return ins[k]


MATH = {"ADD": lambda a, b: a + b, "SUB": lambda a, b: a - b, "MUL": lambda a, b: a * b, "DIV": _div,
        "SEL": lambda g, in0, in1: in1 if g else in0,
        "LIMIT": lambda mn, x, mx: min(max(x, mn), mx),
        "MUX": _mux}

# Integer types for conversions: (bits, signed)
INT_TYPES = {"SINT": (8, True), "USINT": (8, False), "BYTE": (8, False), "INT": (16, True), "UINT": (16, False),
             "WORD": (16, False), "DINT": (32, True), "UDINT": (32, False), "DWORD": (32, False),
             "LINT": (64, True), "ULINT": (64, False), "LWORD": (64, False),
             "TIME": (32, False), "LTIME": (64, False)}   # TIME values are ms in this simulator


def convert(typ, x):
    """<SRC>_TO_<DST>: REAL -> integer rounds to nearest (half away from zero), integers wrap to the
    destination size, anything -> BOOL is x <> 0, BOOL -> number is 0/1."""
    dst = typ.split("_TO_", 1)[1]
    if dst == "BOOL":
        return x != 0
    if dst in ("REAL", "LREAL"):
        return float(x)
    if dst in INT_TYPES:
        if isinstance(x, float):
            x = int(x + 0.5) if x >= 0 else -int(-x + 0.5)
        bits, signed = INT_TYPES[dst]
        x = int(x) & ((1 << bits) - 1)
        return x - (1 << bits) if signed and x >= 1 << (bits - 1) else x
    raise NotImplementedError(f"{typ} isn't simulated")


def tag(e):
    return e.tag.split("}")[1]


class Sim:
    def __init__(self, path, pou, scan_ms=10, models=None, consts=None):
        root = ET.parse(path).getroot()
        self.models = models or {}
        self.instances = {}     # instance name -> model object
        self.fbout = {}         # instance name -> {output pin: value}
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
        self.consts.update(consts or {})
        # Instances of modelled FB types, so their outputs read as defaults before the first call
        self._model_insts = set()
        for block in blocks:
            for var in block.findall(f"{P}variable"):
                d = var.find(f"{P}type/{P}derived")
                if d is not None and d.get("name") in self.models:
                    self._model_insts.add(var.get("name"))

    def key(self, name):
        """The declared spelling of a variable: IEC names are case-insensitive (In1 = in1)."""
        if name in self.v:
            return name
        low = name.lower()
        for k in self.v:
            if k.lower() == low:
                return k
        return name

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
            if m.group(1) in self.timers or m.group(1) not in self.fbout:
                return self.timers.get(m.group(1), {"Q": False, "ET": 0})[m.group(2)]
        if s in self.v or self.key(s) in self.v:
            return self.v[self.key(s)]
        if m := re.fullmatch(r"(\w+)\.([\w.]+)", s):
            # FB output, also a struct member of one: model returns {"ErrorIdent.Additional1": ...}
            if m.group(1) in self.fbout:
                return self.fbout[m.group(1)].get(m.group(2), False)
            if m.group(1) in self.instances or m.group(1) in self.models_by_instance():
                return False    # FB not called yet: outputs at their defaults
        if "." in s and s.split(".")[0] in self.v:
            return 0            # unset struct member of a declared variable
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
                on, var = bool(source(e.find(f"{P}connectionPointIn"))), self.key(e.findtext(f"{P}variable"))
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
        if typ in MATH or (re.fullmatch(r"[A-Z_]+_TO_[A-Z_]+", typ or "") and not e.get("instanceName")):
            if pins["EN"]:
                target = next(v.findtext(f"{P}connectionPointOut/{P}expression")
                              for v in e.findall(f"{P}outputVariables/{P}variable")
                              if v.get("formalParameter") == "Out2")
                operands = [pins[f"In{n}"] for n in range(2, len(pins) + 1) if f"In{n}" in pins]
                target = self.key(target)
                self.v[target] = MATH[typ](*operands) if typ in MATH else convert(typ, operands[0])
            return {"ENO": bool(pins["EN"])}
        if typ == "MOVE":
            if pins["EN"]:
                target = next(v.findtext(f"{P}connectionPointOut/{P}expression")
                              for v in e.findall(f"{P}outputVariables/{P}variable")
                              if v.get("formalParameter") == "Out2")
                self.move(e, self.key(target), pins["In2"])
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
        inst = e.get("instanceName")
        if typ in self.models and inst:
            if pins.get("EN") is False:
                return {"ENO": False}
            model = self.instances.setdefault(inst, self.models[typ]())
            outs = model({k: v for k, v in pins.items()}, self) or {}
            self.fbout[inst] = outs
            for v in e.findall(f"{P}outputVariables/{P}variable"):
                target = v.findtext(f"{P}connectionPointOut/{P}expression")
                if target and v.get("formalParameter") in outs:
                    self.v[target] = outs[v.get("formalParameter")]
            return {"ENO": True, **outs}
        raise NotImplementedError(f"{typ} boxes aren't simulated (pass a model for it)")

    def models_by_instance(self):
        """Instance names declared in the POU whose FB type has a model."""
        return self._model_insts

    def move(self, e, target, value):
        """MOVE: a plain value, or every member when the source is a struct variable."""
        src = next((iv for iv in self.ld if tag(iv) == "inVariable" and iv.get("localId") in
                    {c.get("refLocalId") for v in e.findall(f"{P}inputVariables/{P}variable")
                     if v.get("formalParameter") == "In2"
                     for c in v.findall(f"{P}connectionPointIn/{P}connection")}), None)
        name = src.findtext(f"{P}expression").strip() if src is not None else ""
        members = {k: val for k, val in self.v.items() if k.startswith(name + ".")} if name else {}
        if members:
            for k, val in members.items():
                self.v[target + k[len(name):]] = val
        self.v[target] = value

    def run(self, ms, **inputs):
        """Set inputs, then run scans for ms milliseconds."""
        self.v.update(inputs)
        for _ in range(ms // self.dt):
            self.scan()
