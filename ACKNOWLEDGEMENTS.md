# Acknowledgements

## Use of AI in this software

Parts of this skill were generated and tested with the help of Anthropic's AI models **Claude Opus 5.5** and
**Claude Sonnet 5.5**, working in Claude Code under the direction of the author.

What that covers:

- **Instructions and references:** `SKILL.md`, the README and the reference notes were drafted or edited with the models.
- **Code:** the ladder compiler (`scripts/ladder.py`), the tracer, the simulator and the diff tool under `scripts/` were written or revised by the models from the author's requests.
- **Testing:** the models wrote and ran tests where this repo has them, ran the tools against real ctrlX software or
  a simulator, and helped investigate and fix the problems that turned up.

The author set the requirements, directed the work, ran it on real ctrlX installations and decided what was kept.
AI-assisted work can still contain mistakes. Check every coil of generated ladder against the intent (the tracer exists for that), and test on a simulator before it runs on a machine that can move or hurt something.

## Other software and trademarks

`references/exports/codesys_v35sp15_ladder.xml` is taken from the "ascii-ladder" project on CODESYS Forge (https://forge.codesys.com/u/i-campbell/ascii-ladder/), which is released under the Unlicense, and keeps those terms. The other files in `references/exports/` are exports made with ctrlX PLC Engineering. The skill builds on [ctrlx-engineer](https://github.com/rduffy190/CtrlxPlcSkill), whose converter produces the PLCopenXML.

ctrlX, ctrlX CORE, ctrlX DRIVE, ctrlX OS and ctrlX PLC Engineering are products of Bosch Rexroth AG, and CODESYS
is a product of CODESYS GmbH. This project is independent and is not affiliated with or endorsed by either, or by
Anthropic.

This repository is licensed under the MIT License, except for the Unlicense file named above, see [LICENSE](LICENSE). It comes without warranty of any kind.
