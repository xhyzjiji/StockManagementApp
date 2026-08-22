#!/usr/bin/env python3
import argparse
import sys

from kb_check_coverage import register as register_check_coverage
from kb_select_key_classes import register as register_select_key_classes
from kb_suggest_doc_roots import register as register_suggest_doc_roots
from kb_validate import register as register_validate

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kb_tool.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    register_suggest_doc_roots(sub)
    register_select_key_classes(sub)
    register_validate(sub)
    register_check_coverage(sub)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
