#!/usr/bin/env python3
"""Replay recorded ShowCall traffic. Stdlib only - no install needed.

Each line of traffic.jsonl is one request the legacy frontend actually sends:
{"method", "path", "query", "org", "form"} (form is null for GETs).

Examples:
  python3 replay.py --list
  python3 replay.py --index 4                         # one request, via the gateway
  python3 replay.py --grep crew                       # all crew requests
  python3 replay.py --grep shift/list --base http://localhost:8091   # legacy, direct
  python3 replay.py --index 4 --base http://localhost:8092           # encore, direct

Replaying writes mutates the database (that's the point). Reset with:
  docker compose down -v && docker compose up -d
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent


def load():
    lines = (HERE / "traffic.jsonl").read_text().splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def send(req: dict, base: str) -> tuple[int, dict, str]:
    url = base.rstrip("/") + req["path"]
    if req.get("query"):
        url += "?" + urllib.parse.urlencode(req["query"])
    data = None
    headers = {"X-Org-Id": str(req["org"])}
    if req.get("form") is not None:
        data = urllib.parse.urlencode(req["form"]).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(url, data=data, headers=headers, method=req["method"])
    with urllib.request.urlopen(r) as resp:
        return resp.status, dict(resp.headers), resp.read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080",
                    help="where to send (default: the gateway)")
    ap.add_argument("--index", type=int, help="replay one request by index")
    ap.add_argument("--grep", help="replay every request whose path contains this")
    ap.add_argument("--list", action="store_true", help="list requests, send nothing")
    args = ap.parse_args()

    traffic = load()
    if args.list:
        for i, req in enumerate(traffic):
            form = f" form={req['form']}" if req.get("form") else ""
            query = f"?{urllib.parse.urlencode(req['query'])}" if req.get("query") else ""
            print(f"[{i:3}] org={req['org']:<3} {req['method']:<4} {req['path']}{query}{form}")
        return

    selected = list(enumerate(traffic))
    if args.index is not None:
        selected = [(args.index, traffic[args.index])]
    elif args.grep:
        selected = [(i, r) for i, r in selected if args.grep in r["path"]]
    if not selected:
        sys.exit("nothing matched")

    for i, req in selected:
        try:
            status, headers, body = send(req, args.base)
            served = headers.get("X-Served-By", "-")
            print(f"[{i:3}] {status} via {served}: {req['method']} {req['path']}")
            print(body)
            print()
        except Exception as exc:  # noqa: BLE001
            print(f"[{i:3}] FAILED {req['method']} {req['path']}: {exc}")


if __name__ == "__main__":
    main()
