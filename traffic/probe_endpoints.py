#!/usr/bin/env python3
"""Replay one representative request per unique (method, path) pair from traffic.jsonl,
capturing each response to its own file. Reuses replay.py's load()/send() so requests are
sent identically to `replay.py --index`.

Phase 1 needs one sample per distinct endpoint (not all 51 lines) to discover callboard's
wire behavior - this picks the first recorded index for each (method, path) and fires it.

Usage:
  python3 traffic/probe_endpoints.py --base http://localhost:8091
  python3 traffic/probe_endpoints.py --base http://localhost:8091 --out scratch/probe
  python3 traffic/probe_endpoints.py --base http://localhost:8091 --methods GET
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from replay import load, send  # noqa: E402


def label_for(req: dict) -> str:
    path = req["path"].strip("/").replace("/", "_")
    return f"{req['method']}_{path}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8091",
                     help="where to send (default: callboard direct)")
    ap.add_argument("--out", default="scratch/probe", help="output directory")
    ap.add_argument("--methods",
                     help="comma-separated HTTP methods to include, e.g. GET or GET,POST "
                          "(default: all). Read-only vs. mutating passes can then be run "
                          "as separate, non-overlapping steps.")
    args = ap.parse_args()
    methods = {m.strip().upper() for m in args.methods.split(",")} if args.methods else None

    traffic = load()
    first_index_for = {}
    for i, req in enumerate(traffic):
        if methods is not None and req["method"].upper() not in methods:
            continue
        key = (req["method"], req["path"])
        first_index_for.setdefault(key, i)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for (method, path), i in first_index_for.items():
        req = traffic[i]
        label = label_for(req)
        dest = out_dir / f"{label}.txt"
        try:
            status, headers, body = send(req, args.base)
            served = headers.get("X-Served-By", "-")
            dest.write_text(f"[{i:3}] {status} via {served}: {method} {path}\n{body}\n")
        except Exception as exc:  # noqa: BLE001
            dest.write_text(f"[{i:3}] FAILED {method} {path}: {exc}\n")
        print(f"[{i:3}] {method:<4} {path:<35} -> {dest}")


if __name__ == "__main__":
    main()
