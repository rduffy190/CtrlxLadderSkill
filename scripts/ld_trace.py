#!/usr/bin/env python3
"""Read the LD bodies of a PLCopenXML file back as one boolean expression per output.

Usage:
    ld_trace.py Project.xml

Use it to check that generated ladder is wired as intended, or to read ladder exported
from CODESYS. It follows the connections and ignores positions. Parallel branches print
as OR, series as AND, and boxes as Instance(pins).Pin.
"""
import sys
import xml.etree.ElementTree as ET

P = "{http://www.plcopen.org/xml/tc6_0200}"
X = "{http://www.w3.org/1999/xhtml}"
INFIX = {"GT": ">", "GE": ">=", "LT": "<", "LE": "<=", "EQ": "=", "NE": "<>"}


def tag(e):
    return e.tag.split("}")[1]


def trace_ld(ld):
    els = {e.get("localId"): e for e in ld}

    def source(cpi):
        terms = [expr(c.get("refLocalId"), c.get("formalParameter"))
                 for c in cpi.findall(f"{P}connection")]
        if not terms:
            return "<unconnected>"
        return terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"

    def expr(lid, pin=None):
        e = els[lid]
        t = tag(e)
        if t == "leftPowerRail":
            return "TRUE"
        if t == "inVariable":
            return e.findtext(f"{P}expression")
        if t == "contact":
            v = e.findtext(f"{P}variable")
            if e.get("negated") == "true":
                v = "NOT " + v
            if e.get("edge", "none") != "none":
                v = f"{e.get('edge').upper()}({v})"
            left = source(e.find(f"{P}connectionPointIn"))
            return v if left == "TRUE" else f"{left} AND {v}"
        if t == "block" and not e.get("instanceName") and e.get("typeName") in INFIX:
            # Compare in the rung: EN carries the rung, In2/In3 are compared, Out1 continues
            en, a, b = (source(v.find(f"{P}connectionPointIn"))
                        for v in e.findall(f"{P}inputVariables/{P}variable"))
            cmp = f"[{a} {INFIX[e.get('typeName')]} {b}]"
            return cmp if en == "TRUE" else f"{en} AND {cmp}"
        if t == "block":
            args = [f"{v.get('formalParameter')} := {source(v.find(f'{P}connectionPointIn'))}"
                    for v in e.findall(f"{P}inputVariables/{P}variable")]
            args += [f"{v.get('formalParameter').strip() or 'result'} => {v.findtext(f'{P}connectionPointOut/{P}expression')}"
                     for v in e.findall(f"{P}outputVariables/{P}variable")
                     if v.findtext(f"{P}connectionPointOut/{P}expression")]
            name = e.get("instanceName") or e.get("typeName")
            return f"{name}({', '.join(args)}).{(pin or '').strip() or 'result'}"
        return f"<{t} {lid}>"

    check_parallel_markers(ld, els)
    consumed = {c.get("refLocalId") for c in ld.iter(f"{P}connection")}
    net, label = 0, None
    for e in ld:
        t = tag(e)
        if t == "label":
            label = e.get("label")
        elif t == "vendorElement" and e.findtext(f".//ElementType") == "networktitle":
            net += 1
            title = e.findtext(f"{P}alternativeText/{X}xhtml") or ""
            print(f"  NETWORK {net} {title}".rstrip())
            if label:
                print(f"    LABEL {label}")
                label = None
        elif t == "coil":
            mod = {"set": "S:", "reset": "R:"}.get(e.get("storage"), "")
            neg = "NOT " if e.get("negated") == "true" else ""
            print(f"    {mod}{e.findtext(f'{P}variable')} := {neg}{source(e.find(f'{P}connectionPointIn'))}")
        elif t in ("jump", "return"):
            target = f" {e.get('label')}" if t == "jump" else ""
            print(f"    {t.upper()}{target} IF {source(e.find(f'{P}connectionPointIn'))}")
        elif t == "block" and e.get("typeName") == "MOVE" and e.get("localId") not in consumed:
            pins = {v.get("formalParameter"): v for v in e.findall(f"{P}inputVariables/{P}variable")}
            target = next(v.findtext(f"{P}connectionPointOut/{P}expression")
                          for v in e.findall(f"{P}outputVariables/{P}variable")
                          if v.findtext(f"{P}connectionPointOut/{P}expression"))
            cond = source(pins["EN"].find(f"{P}connectionPointIn"))
            value = source(pins["In2"].find(f"{P}connectionPointIn"))
            print(f"    {target} := {value}" + ("" if cond == "TRUE" else f"  IF {cond}"))
        elif t == "block" and e.get("localId") not in consumed:
            call = expr(e.get('localId')).removesuffix('.result').removesuffix('.ENO')
            print(f"    CALL {call.replace('(EN := TRUE, ', '(').replace('(EN := TRUE)', '()')}")


def check_parallel_markers(ld, els):
    """Warn about parallel joins where every branch holds a box but there's no ParallelBranch
    marker: the editor rebuilds those branches in series, so the OR silently becomes an AND."""
    def key(conns):
        return frozenset((c.get("refLocalId"), c.get("formalParameter")) for c in conns)

    marked = {key(pb.iter("connection")) - key(pb.find("BranchInput").iter("connection"))
              for pb in ld.iter("ParallelBranch")}

    def chain(lid):
        """Element ids from lid back along the rung (EN for boxes) to the rail or a join."""
        ids = []
        while lid in els:
            ids.append(lid)
            e = els[lid]
            cpi = e.find(f"{P}inputVariables/{P}variable[@formalParameter='EN']/{P}connectionPointIn") \
                if tag(e) == "block" else e.find(f"{P}connectionPointIn")
            cons = cpi.findall(f"{P}connection") if cpi is not None else []
            if len(cons) != 1:
                break
            lid = cons[0].get("refLocalId")
        return ids

    def boxes_before_split(cons):
        chains = [chain(c.get("refLocalId")) for c in cons]
        common = set(chains[0]).intersection(*chains[1:])
        # Seen in editor exports: a branch of contacts beside a box branch needs no marker;
        # boxes in every branch do
        return all(any(tag(els[i]) == "block"
                       for i in ch[:next((n for n, i in enumerate(ch) if i in common), len(ch))])
                   for ch in chains)

    for e in ld:
        if tag(e) not in ("contact", "coil", "block", "jump", "return"):
            continue
        for cpi in e.findall(f".//{P}connectionPointIn"):
            cons = cpi.findall(f"{P}connection")
            if len(cons) > 1 and key(cons) not in marked and boxes_before_split(cons):
                print(f"  WARNING: parallel branches into localId {e.get('localId')} all hold a box "
                      "but have no ParallelBranch marker; the editor will chain them in series (AND)")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = ET.parse(sys.argv[1]).getroot()
    for pou in root.iter(f"{P}pou"):
        ld = pou.find(f"{P}body/{P}LD")
        if ld is not None:
            print(f"{pou.get('name')}:")
            trace_ld(ld)


if __name__ == "__main__":
    main()
