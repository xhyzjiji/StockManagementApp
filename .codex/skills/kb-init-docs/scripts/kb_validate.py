#!/usr/bin/env python3
"""validate-kb-docs: thin wrapper that runs the kb-docs-validator on generated
doc roots.

Why this exists: the Step-4 generation gate must call the validator, but the
skill's `allowed-tools` only permits `Bash(python3 scripts/kb_tool.py*)`. Calling
`../kb-docs-validator/scripts/validate_kb_docs.py` directly is NOT covered by that
allowlist, so under a strict tool allowlist (e.g. the cloud kb pipeline) the gate
silently never runs. Routing the call through `kb_tool.py validate-kb-docs` keeps
the allowlist tight while making the gate actually executable. Arguments are
passed straight through to the validator (which still resolves its own deps and
doc-root paths relative to its location, so absolute doc roots remain the safe
input)."""
import subprocess
import sys
from pathlib import Path

# .../kb-init-docs/scripts/kb_validate.py -> skills/kb-docs-validator/scripts/validate_kb_docs.py
_VALIDATOR = (
    Path(__file__).resolve().parent.parent.parent
    / "kb-docs-validator" / "scripts" / "validate_kb_docs.py"
)


def _run(args) -> int:
    if not _VALIDATOR.is_file():
        print(f"validate-kb-docs: validator not found at {_VALIDATOR}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(_VALIDATOR)]
    if args.strict:
        cmd.append("--strict")
    cmd += list(args.doc_roots)
    return subprocess.run(cmd).returncode


def register(sub) -> None:
    p = sub.add_parser(
        "validate-kb-docs",
        help="Run kb-docs-validator on the given doc roots (the after-generation gate).",
    )
    p.add_argument(
        "doc_roots",
        nargs="+",
        help="One or more doc root directories (pass absolute paths).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any ERROR is found (makes the exit code the gate).",
    )
    p.set_defaults(func=_run)
