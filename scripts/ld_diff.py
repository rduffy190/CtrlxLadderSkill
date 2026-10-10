#!/usr/bin/env python3
"""Compare the LD bodies of two PLCopenXML files element by element (tags, attributes, text;
positions and sizes ignored). Use it to check compiler output against a real editor export:

    ld_diff.py export.xml compiled.xml [POU]     -> exit 0 if identical, else prints a diff
"""
import difflib
import sys
import xml.etree.ElementTree as ET

P = "{http://www.plcopen.org/xml/tc6_0200}"
IGNORE = {"height", "width", "x", "y"}


def body(path, pou=None):
    root = ET.parse(path).getroot()
    pous = [p for p in root.iter(f"{P}pou") if pou is None or p.get("name") == pou]
    if not pous or pous[0].find(f"{P}body/{P}LD") is None:
        sys.exit(f"{path}: no LD POU {pou or ''}")
    out = []
    for e in pous[0].find(f"{P}body/{P}LD").iter():
        if not isinstance(e.tag, str):
            continue
        attrs = sorted((k, v) for k, v in e.attrib.items() if k not in IGNORE)
        out.append(f"{e.tag.split('}')[-1]} {attrs} {(e.text or '').strip()}")
    return out


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    a, b = body(argv[0], argv[2] if len(argv) > 2 else None), body(argv[1], argv[2] if len(argv) > 2 else None)
    diff = list(difflib.unified_diff(a, b, argv[0], argv[1], lineterm="", n=1))
    if diff:
        print("\n".join(diff[:200]))
        sys.exit(1)
    print(f"IDENTICAL LD bodies ({len(a)} elements)")


if __name__ == "__main__":
    main(sys.argv[1:])
