"""Compile ladder text (one rung per NETWORK) into a CODESYS PLCopenXML <LD> body.

The language is specified in references/ladder.md. In short:

    NETWORK Motor seal-in
    // network comment
        (bStart | bRun) /bStop -> bRun

    NETWORK Run-on timer
        bRun fbRunOn(PT := T#5S, ET => tElapsed) -> bRunOnDone

The XML mirrors what ctrlX PLC Engineering / CODESYS itself exports: every element at
position 0,0 (the editor lays LD out itself from the connections), one shared left power
rail (localId 0), each network opened by a <comment> + 'networktitle' <vendorElement>,
parallel branches as several <connection>s on one connectionPointIn (plus a 'ParallelBranch'
marker when a branch holds a box), boxes in the rung (compare: EN/In2/In3 -> Out1,
MOVE: EN/In2 -> ENO/Out2, FB calls: EN + pins -> ENO + pins), and a right power rail at the end.

Loaded by codesys-st's st_to_plcopenxml.py (this skill sits next to it in the skills folder):
a POU whose implementation starts with NETWORK is ladder.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

NS = "http://www.plcopen.org/xml/tc6_0200"
XHTML = "http://www.w3.org/1999/xhtml"
RAIL = (0, None)                      # (localId, formalParameter) of the left power rail
RIGHT_RAIL_ID = 2147483646            # what CODESYS uses
CALLTYPE = "http://www.3s-software.com/plcopenxml/fbdcalltype"
PARAMTYPES = "http://www.3s-software.com/plcopenxml/inputparamtypes"
ELEMENTTYPE = "http://www.3s-software.com/plcopenxml/fbdelementtype"
PARALLELBRANCH = "http://www.3s-software.com/plcopenxml/ldparallelbranch"

COMPARE_OPS = {">=": "GE", "<=": "LE", "<>": "NE", ">": "GT", "<": "LT", "=": "EQ"}

# Library FBs: type -> ([(input, type)], [outputs]). These pin lists fix the pin order, give
# the input types for the inputparamtypes entry, and let unknown pin names be reported. FBs
# defined in the input files are read from their source.
STD_FBS = {
    "TON": ([("IN", "BOOL"), ("PT", "TIME")], ["Q", "ET"]),
    "TOF": ([("IN", "BOOL"), ("PT", "TIME")], ["Q", "ET"]),
    "TP": ([("IN", "BOOL"), ("PT", "TIME")], ["Q", "ET"]),
    "LTON": ([("IN", "BOOL"), ("PT", "LTIME")], ["Q", "ET"]),
    "LTOF": ([("IN", "BOOL"), ("PT", "LTIME")], ["Q", "ET"]),
    "LTP": ([("IN", "BOOL"), ("PT", "LTIME")], ["Q", "ET"]),
    "CTU": ([("CU", "BOOL"), ("RESET", "BOOL"), ("PV", "WORD")], ["Q", "CV"]),
    "CTD": ([("CD", "BOOL"), ("LOAD", "BOOL"), ("PV", "WORD")], ["Q", "CV"]),
    "CTUD": ([("CU", "BOOL"), ("CD", "BOOL"), ("RESET", "BOOL"), ("LOAD", "BOOL"), ("PV", "WORD")],
             ["QU", "QD", "CV"]),
    "R_TRIG": ([("CLK", "BOOL")], ["Q"]),
    "F_TRIG": ([("CLK", "BOOL")], ["Q"]),
    "SR": ([("SET1", "BOOL"), ("RESET", "BOOL")], ["Q1"]),
    "RS": ([("SET", "BOOL"), ("RESET1", "BOOL")], ["Q1"]),
}
# Timers sit in the rung without EN/ENO, as the editor exports them: the rung drives IN and
# continues from Q. Every other FB call runs on EN/ENO.
TIMERS = {"TON", "TOF", "TP", "LTON", "LTOF", "LTP"}


class LadderError(Exception):
    pass


# ---------------------------------------------------------------- AST

@dataclass
class Contact:
    var: str
    negated: bool = False
    edge: str = "none"                 # none | rising | falling


@dataclass
class Compare:
    op: str                            # GT, GE, ...
    lhs: str
    rhs: str
    text: str


@dataclass
class Box:
    instance: str
    type: str | None                   # None: take it from the declarations
    inputs: list = field(default_factory=list)    # [(pin, expr)]
    outputs: list = field(default_factory=list)   # [(pin, var)]


@dataclass
class Parallel:
    branches: list                     # list of series (list of nodes)


@dataclass
class Coil:
    var: str
    negated: bool = False
    storage: str = "none"              # none | set | reset


@dataclass
class Jump:
    label: str


@dataclass
class Return:
    pass


@dataclass
class Move:
    target: str
    expr: str


@dataclass
class Network:
    title: str
    line: int
    comment: list = field(default_factory=list)
    label: str | None = None
    rung: list = field(default_factory=list)      # source lines


# ---------------------------------------------------------------- network splitting

NETWORK_RE = re.compile(r"NETWORK\b[ \t:]*(.*)$", re.I)
LABEL_RE = re.compile(r"LABEL\s+(\w+)\s*:?\s*$", re.I)


def is_ladder(impl: str) -> bool:
    for line in impl.splitlines():
        s = line.strip()
        if s and not s.startswith("//"):
            return bool(NETWORK_RE.match(s))
    return False


def strip_line_comment(line: str) -> str:
    """Drop a trailing // comment, ignoring // inside string literals."""
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif line.startswith("//", i):
            return line[:i]
    return line


def split_networks(impl: str) -> list[Network]:
    nets: list[Network] = []
    for no, raw in enumerate(impl.splitlines(), 1):
        s = raw.strip()
        m = NETWORK_RE.match(s)
        if m:
            nets.append(Network(title=m.group(1).strip().strip('"'), line=no))
            continue
        if not nets:
            if s and not s.startswith("//"):
                raise LadderError(f"line {no}: text before the first NETWORK: {s!r}")
            continue
        net = nets[-1]
        if not net.rung and s.startswith("//"):
            net.comment.append(s[2:].strip())
            continue
        m = LABEL_RE.match(s)
        if m and not net.rung:
            net.label = m.group(1)
            continue
        code = strip_line_comment(s).strip()
        if code:
            net.rung.append(code)
    return nets


# ---------------------------------------------------------------- rung parser

OPERAND_RE = re.compile(r"%?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\]|\^)*")


class Parser:
    def __init__(self, text: str):
        self.s, self.i = text, 0

    def error(self, msg):
        raise LadderError(f"{msg}\n    {self.s}\n    {' ' * self.i}^")

    def ws(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def peek(self, k=1):
        self.ws()
        return self.s[self.i:self.i + k]

    def eat(self, tok):
        if self.peek(len(tok)) != tok:
            self.error(f"expected '{tok}'")
        self.i += len(tok)

    def operand(self, what="a variable"):
        self.ws()
        m = OPERAND_RE.match(self.s, self.i)
        if not m:
            self.error(f"expected {what}")
        self.i = m.end()
        return m.group(0)

    def at_call(self):
        """A box is NAME( with no space; 'bA (bB | bC)' is a contact in series with a group."""
        return self.s[self.i:self.i + 1] == "("

    def balanced(self, close):
        """Text up to the matching close bracket (consumed), respecting nesting and strings."""
        start, depth, quote = self.i, 0, None
        while self.i < len(self.s):
            c = self.s[self.i]
            if quote:
                quote = None if c == quote else quote
            elif c in "'\"":
                quote = c
            elif c in "([":
                depth += 1
            elif c in ")]":
                if depth == 0:
                    if c != close:
                        self.error(f"expected '{close}'")
                    self.i += 1
                    return self.s[start:self.i - 1]
                depth -= 1
            self.i += 1
        self.error(f"missing '{close}'")

    # rung := series ['->' outputs]
    def rung(self):
        # '-> outputs' with nothing before it is unconditional (outputs on the left rail)
        series = [] if self.peek(2) == "->" else self.series()
        outputs = []
        if self.peek(2) == "->":
            self.i += 2
            outputs = self.outputs()
        if self.peek():
            self.error("unexpected text (only one rung per NETWORK)")
        return series, outputs

    def series(self):
        items = []
        while True:
            c = self.peek()
            if not c or c in ")|," or self.peek(2) == "->":
                break
            items.append(self.term())
        if not items:
            self.error("expected a contact, '(', '[' or a box")
        return items

    def term(self):
        c = self.peek()
        if c == "(":
            self.i += 1
            branches = [self.series()]
            while self.peek() == "|":
                self.i += 1
                branches.append(self.series())
            self.eat(")")
            return Parallel(branches)       # one branch is just grouping
        if c == "[":
            self.i += 1
            return self.compare(self.balanced("]"))
        if c == "/":
            self.i += 1
            return Contact(self.operand(), negated=True)
        name = self.operand("a contact, '(', '[' or a box")
        call = self.at_call()
        if self.peek() == ":" and self.peek(2) != ":=":
            self.i += 1
            if name.upper() in ("P", "N"):
                return Contact(self.operand(), edge="rising" if name.upper() == "P" else "falling")
            typ = self.operand("an FB type after ':'")
            if not self.at_call():
                self.error("expected '(' right after instance:TYPE")
            return self.box(name, typ)
        if call:
            return self.box(name, None)
        return Contact(name)

    def compare(self, text):
        depth, quote = 0, None
        for i, c in enumerate(text):
            if quote:
                quote = None if c == quote else quote
            elif c in "'\"":
                quote = c
            elif c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif depth == 0 and c in "<>=":
                op = text[i:i + 2] if text[i:i + 2] in COMPARE_OPS else c
                lhs, rhs = text[:i].strip(), text[i + len(op):].strip()
                if not lhs or not rhs:
                    break
                return Compare(COMPARE_OPS[op], lhs, rhs, text.strip())
        self.error(f"expected a comparison like [a > b] (ops: {' '.join(COMPARE_OPS)})")

    def box(self, instance, typ):
        self.eat("(")
        box = Box(instance, typ)
        for arg in split_args(self.balanced(")")):
            if m := re.fullmatch(r"(\w+)\s*:=\s*(.+)", arg, re.S):
                box.inputs.append((m.group(1), " ".join(m.group(2).split())))
            elif m := re.fullmatch(r"(\w+)\s*=>\s*(.+)", arg, re.S):
                box.outputs.append((m.group(1), m.group(2).strip()))
            else:
                self.error(f"{instance}: can't read pin '{arg}' (use PIN := expr or PIN => var; "
                           "the rung always goes through EN/ENO)")
        return box

    # outputs := output {',' output}
    def outputs(self):
        outs = [self.output()]
        while self.peek() == ",":
            self.i += 1
            outs.append(self.output())
        return outs

    def output(self):
        if self.peek() == "/":
            self.i += 1
            return Coil(self.operand(), negated=True)
        name = self.operand("a coil, S:var, R:var, JMP:label, RET, target := value or a box")
        call = self.at_call()
        up = name.upper()
        if up == "RET":
            return Return()
        if self.peek() == ":" and self.peek(2) != ":=":
            self.i += 1
            if up in ("S", "R"):
                return Coil(self.operand(), storage="set" if up == "S" else "reset")
            if up == "JMP":
                return Jump(self.operand("a label"))
            typ = self.operand("an FB type after ':'")
            if not self.at_call():
                self.error("expected '(' right after instance:TYPE")
            return self.box(name, typ)
        if self.peek(2) == ":=":
            self.i += 2
            self.ws()
            start, depth = self.i, 0
            while self.i < len(self.s):
                c = self.s[self.i]
                if c == "," and depth == 0:
                    break
                depth += (c in "([") - (c in ")]")
                self.i += 1
            expr = " ".join(self.s[start:self.i].split())
            if not expr:
                self.error(f"expected a value after '{name} :='")
            return Move(name, expr)
        if call:
            return self.box(name, None)
        return Coil(name)


def has_box(node) -> bool:
    """Does a Parallel (or a series list) contain a compare or FB box anywhere?"""
    if isinstance(node, (Compare, Box)):
        return True
    if isinstance(node, Parallel):
        return any(has_box(b) for b in node.branches)
    if isinstance(node, list):
        return any(has_box(n) for n in node)
    return False


def walk(node):
    """Every node inside a Parallel (or a series list), depth first."""
    for n in (node.branches if isinstance(node, Parallel) else node):
        if isinstance(n, list):
            yield from walk(n)
        else:
            yield n
            if isinstance(n, Parallel):
                yield from walk(n)


def split_args(text: str) -> list[str]:
    args, depth, quote, start = [], 0, None, 0
    for i, c in enumerate(text):
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "," and depth == 0:
            args.append(text[start:i])
            start = i + 1
    args.append(text[start:])
    return [a.strip() for a in args if a.strip()]


# ---------------------------------------------------------------- XML emitter

def q(tag):
    return f"{{{NS}}}{tag}"


def sub(parent, tag, **attrs):
    return ET.SubElement(parent, q(tag), {k: str(v) for k, v in attrs.items()})


def xhtml(parent, text=""):
    el = ET.SubElement(parent, f"{{{XHTML}}}xhtml")
    if text:
        el.text = text
    return el


def add_data(parent, entries):
    """One <addData> with a <data name=...><Tag>value</Tag></data> per (name, tag, value)."""
    ad = sub(parent, "addData")
    for name, tag, value in entries:
        d = sub(ad, "data", name=name, handleUnknown="implementation")
        # Serialised with xmlns="" by st_to_plcopenxml.py, as CODESYS writes it
        ET.SubElement(d, tag).text = value


@dataclass
class Context:
    var_types: dict          # lower-case variable name -> declared type text
    fb_sigs: dict            # upper-case FB name -> [(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT, name, type)]
    warnings: list


class Emitter:
    def __init__(self, ld, ctx: Context, where: str):
        self.ld, self.ctx, self.where = ld, ctx, where
        self.next_id = 1

    def new_id(self):
        self.next_id += 1
        return self.next_id - 1

    def node(self, tag, lid=None, **attrs):
        el = sub(self.ld, tag, localId=self.new_id() if lid is None else lid, **attrs)
        sub(el, "position", x=0, y=0)
        return el

    @staticmethod
    def connect(parent, refs):
        cpi = sub(parent, "connectionPointIn")
        for rid, pin in refs:
            c = sub(cpi, "connection", refLocalId=rid)
            if pin is not None:
                c.set("formalParameter", pin)
        return cpi

    # -- networks

    def network(self, net: Network):
        el = self.node("comment", height=0, width=0)
        xhtml(sub(el, "content"), "\n".join(net.comment))
        if net.label:
            self.node("label", label=net.label)
        el = self.node("vendorElement")
        xhtml(sub(el, "alternativeText"), net.title)
        add_data(el, [(ELEMENTTYPE, "ElementType", "networktitle")])
        if not net.rung:
            return
        series, outputs = Parser(" ".join(net.rung)).rung()
        refs = self.series(series, [RAIL])
        if not outputs and not isinstance(series[-1], Box):
            raise LadderError("rung has no output: add '-> coil' (or end it with a box)")
        for out in outputs:
            self.output(out, refs)

    def series(self, items, refs):
        for item in items:
            if isinstance(item, Contact):
                el = self.node("contact", negated=str(item.negated).lower(), storage="none",
                               edge=item.edge)
                self.connect(el, refs)
                sub(el, "connectionPointOut")
                ET.SubElement(el, q("variable")).text = item.var
                refs = [(int(el.get("localId")), None)]
            elif isinstance(item, Parallel):
                # Without a ParallelBranch marker the editor chains boxes in parallel branches
                # in series (an AND). Like the box ids, the editor numbers the marker before
                # the branch elements, although it is written after them
                marker = self.new_id() if len(item.branches) > 1 and has_box(item) else None
                if len(item.branches) > 1 and any(isinstance(n, Compare) for n in walk(item)):
                    self.ctx.warnings.append(
                        f"{self.where}: compare in a parallel branch; the editor has shown these "
                        "ANDed. Decode it into a BOOL first ([x = y] -> _bFlag) and use a contact")
                ends = [self.series(branch, refs) for branch in item.branches]
                if marker is not None:
                    self.parallel_marker(refs, ends, marker)
                refs = list(dict.fromkeys(r for end in ends for r in end))
            elif isinstance(item, Compare):
                # In the rung like a contact: power in on EN, Out1 = EN AND (In2 op In3)
                refs = [(self.operator(item.op, refs, [item.lhs, item.rhs], ["Out1"]), "Out1")]
            elif isinstance(item, Box):
                refs = self.box(item, refs)
        return refs

    def parallel_marker(self, refs, ends, lid):
        el = self.node("vendorElement", lid)
        xhtml(sub(el, "alternativeText"), "ParallelBranch")
        d = sub(sub(el, "addData"), "data", name=PARALLELBRANCH, handleUnknown="implementation")
        # No namespace, like ElementType (st_to_plcopenxml.py writes xmlns="" on it)
        pb = ET.SubElement(d, "ParallelBranch", mode="sce")

        def point(parent, rs):
            cpi = ET.SubElement(parent, "connectionPointIn")
            for rid, pin in rs:
                c = ET.SubElement(cpi, "connection", refLocalId=str(rid))
                if pin is not None:
                    c.set("formalParameter", pin)

        point(ET.SubElement(pb, "BranchInput"), refs)
        trees = ET.SubElement(pb, "BranchTrees")
        for end in ends:
            point(ET.SubElement(trees, "Tree"), end)

    def output(self, out, refs):
        if isinstance(out, Coil):
            el = self.node("coil", negated=str(out.negated).lower(), storage=out.storage)
            self.connect(el, refs)
            sub(el, "connectionPointOut")
            ET.SubElement(el, q("variable")).text = out.var
        elif isinstance(out, Jump):
            self.connect(self.node("jump", label=out.label), refs)
        elif isinstance(out, Return):
            self.connect(self.node("return"), refs)
        elif isinstance(out, Move):
            self.operator("MOVE", refs, [out.expr], ["ENO", "Out2"], {"Out2": out.target})
        elif isinstance(out, Box):
            self.box(out, refs)

    # -- boxes

    def in_variables(self, pins):
        ids = []
        for _, expr in pins:
            el = self.node("inVariable")
            sub(el, "connectionPointOut")
            ET.SubElement(el, q("expression")).text = expr
            ids.append(int(el.get("localId")))
        return ids

    def operator(self, op, refs, operands, outputs, targets=None):
        """Operator box in the rung, as ctrlX PLC Engineering exports it: pin 1 is EN (the
        rung), the operands are In2, In3, ... and the outputs Out1.. / ENO. Returns its localId."""
        # The editor numbers a box before the variables on its pins (written after them)
        lid = self.new_id()
        ids = self.in_variables([(None, e) for e in operands])
        blk = self.node("block", lid, typeName=op)
        iv = sub(blk, "inputVariables")
        self.connect(sub(iv, "variable", formalParameter="EN"), refs)
        for n, rid in enumerate(ids, 2):
            self.connect(sub(iv, "variable", formalParameter=f"In{n}"), [(rid, None)])
        sub(blk, "inOutVariables")
        ov = sub(blk, "outputVariables")
        for pin in outputs:
            cpo = sub(sub(ov, "variable", formalParameter=pin), "connectionPointOut")
            if targets and pin in targets:
                ET.SubElement(cpo, q("expression")).text = targets[pin]
        add_data(blk, [(CALLTYPE, "CallType", "operator"), (PARAMTYPES, "InputParamTypes", "BOOL")])
        return int(blk.get("localId"))

    def instance_type(self, instance):
        base = re.sub(r"\[[^\]]*\]", "", instance).split(".")[-1].lower()
        t = self.ctx.var_types.get(base)
        if t is None:
            return None
        m = re.fullmatch(r"ARRAY\s*\[.*?\]\s*OF\s+(.+)", t, re.I | re.S)
        return (m.group(1) if m else t).strip()

    def signature(self, typ):
        """([(input, type)] or None, [outputs] or None) of an FB type."""
        tu = typ.upper()
        if tu in self.ctx.fb_sigs:
            sig = self.ctx.fb_sigs[tu]
            return ([(n, t) for k, n, t in sig if k in ("VAR_INPUT", "VAR_IN_OUT")],
                    [n for k, n, _ in sig if k == "VAR_OUTPUT"])
        return STD_FBS.get(tu, (None, None))

    def box(self, box: Box, refs):
        """FB call. Timers: the rung drives IN and continues from Q. Every other FB: the rung
        drives EN and continues from ENO. All other pins are named."""
        typ = box.type or self.instance_type(box.instance)
        if not typ:
            raise LadderError(f"{box.instance}: not declared in this POU or a GVL; "
                              "write it as instance:TYPE(...)")
        timer = typ.upper() in TIMERS
        rung_in, rung_out = ("IN", "Q") if timer else ("EN", "ENO")
        if timer:
            if any(pin.upper() == "IN" for pin, _ in box.inputs):
                raise LadderError(f"{box.instance}: a timer's IN is the rung; put its condition "
                                  "in front of it instead of IN :=")
            if any(pin.upper() == "Q" for pin, _ in box.outputs):
                raise LadderError(f"{box.instance}: a timer's Q continues the rung; follow it "
                                  "with -> coil instead of Q =>")
        elif refs != [RAIL]:
            self.ctx.warnings.append(
                f"{self.where}: {box.instance} is called only while its rung is on (EN), so it "
                "stops updating when the rung goes off; house style calls FBs every scan")
        ins, outs = self.signature(typ)

        def order(pins, known, kind):
            if known is None:
                return pins
            lower = [k.lower() for k in known]
            for pin, _ in pins:
                if pin.lower() not in lower:
                    raise LadderError(f"{box.instance} ({typ}) has no {kind} '{pin}'")
            return sorted(pins, key=lambda p: lower.index(p[0].lower()))

        in_types = {n.lower(): t for n, t in ins} if ins is not None else None
        inputs = order(box.inputs, in_types and list(in_types), "input")
        outputs = order(box.outputs, outs, "output")
        if outs is not None:
            # Like the editor's export: every output pin listed, unused ones with an empty expression
            given = {p.lower(): (p, v) for p, v in outputs}
            outputs = [given.get(n.lower(), (n, None)) for n in outs if n.upper() != rung_out]

        lid = self.new_id()                    # box numbered before its pin variables
        ids = self.in_variables(inputs)
        blk = self.node("block", lid, typeName=typ, instanceName=box.instance)
        iv = sub(blk, "inputVariables")
        self.connect(sub(iv, "variable", formalParameter=rung_in), refs)
        for (pin, _), rid in zip(inputs, ids):
            self.connect(sub(iv, "variable", formalParameter=pin), [(rid, None)])
        sub(blk, "inOutVariables")
        ov = sub(blk, "outputVariables")
        sub(sub(ov, "variable", formalParameter=rung_out), "connectionPointOut")
        for pin, var in outputs:
            cpo = sub(sub(ov, "variable", formalParameter=pin), "connectionPointOut")
            ET.SubElement(cpo, q("expression")).text = var
        data = [(CALLTYPE, "CallType", "functionblock")]
        if in_types is not None:
            # The rung pin (EN or a timer's IN) is BOOL, then the named inputs' types
            data.append((PARAMTYPES, "InputParamTypes",
                         " ".join(["BOOL"] + [in_types[p.lower()].upper() for p, _ in inputs])))
        add_data(blk, data)
        return [(int(blk.get("localId")), rung_out)]

def build_ld(body, impl: str, ctx: Context, where: str):
    """Append an <LD> element for the ladder text `impl` to the POU <body>."""
    ld = sub(body, "LD")
    rail = sub(ld, "leftPowerRail", localId=0)
    sub(rail, "position", x=0, y=0)
    sub(rail, "connectionPointOut", formalParameter="none")
    em = Emitter(ld, ctx, where)
    for n, net in enumerate(split_networks(impl), 1):
        try:
            em.network(net)
        except LadderError as e:
            title = f" '{net.title}'" if net.title else ""
            raise LadderError(f"{where}: network {n}{title}: {e}") from None
    rr = sub(ld, "rightPowerRail", localId=RIGHT_RAIL_ID)
    sub(rr, "position", x=0, y=0)
    sub(rr, "connectionPointIn")
