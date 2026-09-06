#!/usr/bin/env python3
"""Probe BAM endpoint schema through official local CLI/auth paths."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_BAM = Path.home() / ".bitscli" / "bin" / "bitscli-bam"


def find_byte_cli() -> str | None:
    found = shutil.which("byte-cli")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "byte-cli"
    return str(local) if local.exists() else None


def find_bam_cli() -> str | None:
    found = shutil.which("bitscli-bam")
    if found:
        return found
    return str(DEFAULT_BAM) if DEFAULT_BAM.exists() else None


def get_jwt() -> str | None:
    token = os.environ.get("X_JWT_TOKEN") or os.environ.get("BYTEST_JWT_TOKEN")
    if token:
        return token
    byte_cli = find_byte_cli()
    if not byte_cli:
        return None
    proc = subprocess.run(
        [byte_cli, "login", "--control-plane", "cn", "get-jwt"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return ((payload.get("data") or {}).get("jwt") or None) if payload.get("success") else None


def run_bam(endpoint_id: int, schema: str) -> dict[str, object]:
    bam = find_bam_cli()
    if not bam:
        return {"ok": False, "stage": "bitscli-bam", "error": "bitscli-bam not found"}
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
    proc = subprocess.run(
        [bam, "method", "get", "--endpoint-id", str(endpoint_id), "--schema", schema],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return {"ok": True, "stage": "bitscli-bam", "endpoint_id": endpoint_id, "output": out}
    return {
        "ok": False,
        "stage": "bitscli-bam",
        "endpoint_id": endpoint_id,
        "exit_code": proc.returncode,
        "error": out.strip(),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-id", type=int, required=True)
    parser.add_argument("--schema", choices=["none", "ref", "inline"], default="inline")
    args = parser.parse_args(argv)

    result = {
        "endpoint_id": args.endpoint_id,
        "byte_cli_available": bool(find_byte_cli()),
        "jwt_available": bool(get_jwt()),
        "bam_cli_available": bool(find_bam_cli()),
        "bam": run_bam(args.endpoint_id, args.schema),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["bam"].get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
