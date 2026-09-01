"""ShowCall migration gateway.

Reverse proxy in front of both backends. Reads routes.yaml on every request,
picks a backend per (path prefix, org), forwards the request unchanged, and
annotates the response with X-Served-By and X-Trace-Id so you can see which
system handled what.

You may modify this service if your approach needs it, but the assessment is
designed so that editing routes.yaml is enough.
"""
import os
import uuid
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Request, Response

ROUTES_FILE = Path(os.environ.get("ROUTES_FILE", "routes.yaml"))
BACKENDS = {
    "callboard": os.environ.get("CALLBOARD_URL", "http://callboard:8080"),
    "encore": os.environ.get("ENCORE_URL", "http://encore:8080"),
}
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}

app = FastAPI(title="showcall-gateway")
client = httpx.AsyncClient(timeout=30)


def pick_backend(path: str, org: str | None) -> str:
    table = yaml.safe_load(ROUTES_FILE.read_text()) or {}
    routes = table.get("routes") or {}
    best = None
    for prefix in routes:
        if path.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    if best is None:
        return "callboard"
    rule = routes[best] or {}
    orgs = rule.get("orgs") or {}
    if org is not None:
        for key, backend in orgs.items():
            if str(key) == org:
                return backend
    return rule.get("default", "callboard")


@app.get("/gateway/healthz")
async def healthz():
    return {"ok": True, "backends": BACKENDS}


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def forward(path: str, request: Request):
    org = request.headers.get("x-org-id")
    backend = pick_backend("/" + path, org)
    base = BACKENDS.get(backend)
    if base is None:
        return Response(f"unknown backend {backend!r}", status_code=502)

    trace_id = request.headers.get("x-trace-id", uuid.uuid4().hex)
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
    }
    headers["x-trace-id"] = trace_id
    body = await request.body()
    try:
        upstream = await client.request(
            request.method,
            base + "/" + path,
            params=request.url.query,
            headers=headers,
            content=body,
        )
    except httpx.HTTPError as exc:
        return Response(f"backend {backend} unreachable: {exc}", status_code=502)

    out_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP
    }
    out_headers["x-served-by"] = backend
    out_headers["x-trace-id"] = trace_id
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )
