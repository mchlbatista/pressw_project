"""Wire-format helpers shared by every /callboard/* legacy wrapper.

Confirmed in SEAMS.md's probe log: callboard's envelope is
`{"data": ..., "result": "ok", "tg_flash": null}` on success and
`{"error": ..., "result": "fail"}` on failure, across every endpoint probed
so far - not just crew. Object keys come back alphabetically ordered on the
wire (looks like callboard serializes with sort_keys=True), so callers build
their payload dicts with keys already in that order rather than relying on
a JSON-semantic diff to paper over it. Every body - success or failure - ends
in a trailing "\\n" (confirmed by direct byte comparison against callboard on
port 8091), which `render()` reproduces.
"""
import json

from fastapi import Response


def render(payload: dict) -> Response:
    body = json.dumps(payload, separators=(",", ":")) + "\n"
    return Response(content=body, media_type="application/json")


def resolve_org(header_value: str | None) -> int | None:
    if header_value is None:
        return None
    try:
        return int(header_value)
    except ValueError:
        return None


def ok(data) -> dict:
    return {"data": data, "result": "ok", "tg_flash": None}


def fail(error: str) -> dict:
    return {"error": error, "result": "fail"}
