"""Slice a mitmproxy flow file into model-friendly JSON chunks.

Step 3 of the capture workflow. Groups requests by host + first path segment and
packs them into slices of roughly --max-bytes each (default 24 KB), so every
slice can be handed to the local model without blowing its context window.

Outputs:
  <out>/slice_01.json, slice_02.json, ...
  <out>/manifest.json

Usage:
  python flow_slice.py capture/flows -o capture/slices
  python flow_slice.py capture/flows -o capture/slices --host www.uooc.net.cn
  python flow_slice.py capture/flows -o capture/slices --only-api
  python flow_slice.py capture/flows -o capture/slices --max-bytes 24576
  python flow_slice.py capture/flows -o capture/slices --cookie-mode full
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlsplit

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

STATIC_EXT = (
    ".js", ".mjs", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".mp4", ".webm",
    ".mp3", ".wav", ".avif", ".bmp",
)

# Request headers worth showing the model. Everything else is dropped to save
# tokens; anything starting with x- is kept as well.
REQ_HEADER_ALLOW = {
    "content-type", "accept", "accept-language", "referer", "origin",
    "user-agent", "authorization", "x-requested-with", "content-length",
    "x-csrf-token", "x-xsrf-token", "x-token", "x-sign", "x-signature",
}

RESP_HEADER_ALLOW = {
    "content-type", "content-length", "set-cookie", "location", "cache-control",
    "x-total-count", "x-page-count",
}


def looks_static(path: str) -> bool:
    return path.lower().endswith(STATIC_EXT)


def schema_of(value, depth: int = 0, max_depth: int = 6):
    """Compact structural skeleton of a decoded JSON value."""
    if depth > max_depth:
        return "..."
    if isinstance(value, dict):
        return {k: schema_of(v, depth + 1, max_depth) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        first = schema_of(value[0], depth + 1, max_depth) if value else None
        return {"__list__": first, "__count__": len(value)}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def summarize_cookie(raw: str, mode: str) -> str:
    if mode == "full":
        return raw
    names = []
    for part in raw.split(";"):
        name = part.split("=", 1)[0].strip()
        if name:
            names.append(name)
    if not names:
        return ""
    return "<%d cookies: %s>" % (len(names), ", ".join(names[:20]))


def redact(name: str, value: str) -> str:
    """Never put a live credential into a slice, whatever mode was asked for."""
    lowered = name.lower()
    if lowered == "authorization":
        return value[:14] + "...<redacted>"
    if lowered in ("x-token", "x-sign", "x-signature", "x-api-key", "api-key"):
        return value[:8] + "...<redacted>"
    return value


def pick_headers(headers, allow: set[str], cookie_mode: str) -> dict:
    out = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered == "cookie":
            if cookie_mode != "drop":
                out[name] = summarize_cookie(value, cookie_mode)
            continue
        if lowered in allow or lowered.startswith("x-") or lowered.startswith("sec-"):
            out[name] = redact(name, value[:300])
    return out


def body_text(message, max_chars: int) -> str | None:
    try:
        raw = message.get_content(strict=False)
    except Exception:
        return None
    if not raw:
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return "<binary %d bytes>" % len(raw)
    if len(text) > max_chars:
        return text[:max_chars] + "\n...<truncated %d chars>" % (len(text) - max_chars)
    return text


def body_json(message):
    try:
        raw = message.get_content(strict=False)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def build_record(index: int, flow, args) -> dict:
    req = flow.request
    resp = flow.response
    parts = urlsplit(req.pretty_url)
    path = parts.path or "/"
    record = {
        "idx": index,
        "method": req.method,
        "url": req.pretty_url,
        "host": req.host,
        "path": path,
        "query": parts.query,
        "status": resp.status_code if resp else None,
        "req_headers": pick_headers(req.headers, REQ_HEADER_ALLOW, args.cookie_mode),
        "req_body": body_text(req, args.max_body),
        "req_body_json": body_json(req),
        "resp_headers": pick_headers(resp.headers, RESP_HEADER_ALLOW, args.cookie_mode) if resp else {},
        "resp_size": len(resp.get_content(strict=False) or b"") if resp else 0,
        "resp_schema": None,
        "resp_preview": None,
    }
    if resp is not None:
        decoded = body_json(resp)
        if decoded is not None:
            record["resp_schema"] = schema_of(decoded)
        else:
            record["resp_preview"] = body_text(resp, min(args.max_body, 1200))
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="Slice a flow file into JSON chunks")
    ap.add_argument("flow_file")
    ap.add_argument("-o", "--out", required=True, help="output directory")
    ap.add_argument("--max-bytes", type=int, default=24576, help="target size per slice")
    ap.add_argument("--max-body", type=int, default=4000, help="max chars per body")
    ap.add_argument("--host", action="append", default=[], help="only this host (repeatable)")
    ap.add_argument("--only-api", action="store_true", help="drop static assets")
    ap.add_argument(
        "--cookie-mode",
        choices=("summary", "full", "drop"),
        default="summary",
        help="how to render the Cookie header (default: names only)",
    )
    args = ap.parse_args()

    try:
        from mitmproxy import http
        from mitmproxy import io as mio
    except Exception as exc:  # pragma: no cover
        print("mitmproxy import failed:", type(exc).__name__, exc)
        print("Install it with:  python -m pip install mitmproxy")
        return 2

    groups: "list[tuple[tuple, list[dict]]]" = []
    current_key = None
    current_rows: list[dict] = []

    with open(args.flow_file, "rb") as fh:
        reader = mio.FlowReader(fh)
        for index, flow in enumerate(reader.stream(), start=1):
            if not isinstance(flow, http.HTTPFlow):
                continue
            req = flow.request
            path = urlsplit(req.pretty_url).path or "/"
            if args.host and req.host not in args.host:
                continue
            if args.only_api and looks_static(path):
                continue
            segment = path.strip("/").split("/")[0] if path.strip("/") else ""
            key = (req.host, segment)
            if key != current_key:
                if current_rows:
                    groups.append((current_key, current_rows))
                current_key = key
                current_rows = []
            current_rows.append(build_record(index, flow, args))
    if current_rows:
        groups.append((current_key, current_rows))

    os.makedirs(args.out, exist_ok=True)
    manifest = []
    slice_no = 0
    chunk: list[dict] = []
    chunk_key = None
    chunk_bytes = 0

    def flush() -> None:
        nonlocal chunk, chunk_key, chunk_bytes, slice_no
        if not chunk:
            return
        slice_no += 1
        name = "slice_%02d.json" % slice_no
        path = os.path.join(args.out, name)
        payload = {
            "slice": slice_no,
            "group": {"host": chunk_key[0], "segment": chunk_key[1]} if chunk_key else None,
            "requests": chunk,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        manifest.append(
            {
                "slice": name,
                "host": chunk_key[0] if chunk_key else None,
                "segment": chunk_key[1] if chunk_key else None,
                "requests": len(chunk),
                "bytes": len(text.encode("utf-8")),
                "idx": [chunk[0]["idx"], chunk[-1]["idx"]],
            }
        )
        chunk = []
        chunk_key = None
        chunk_bytes = 0

    for key, rows in groups:
        for row in rows:
            row_bytes = len(json.dumps(row, ensure_ascii=False))
            if chunk and (chunk_key != key or chunk_bytes + row_bytes > args.max_bytes):
                flush()
            if not chunk:
                chunk_key = key
            chunk.append(row)
            chunk_bytes += row_bytes
    flush()

    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": args.flow_file, "slices": manifest}, fh, ensure_ascii=False, indent=2)

    print("slices: %d  ->  %s" % (len(manifest), args.out))
    for entry in manifest:
        print(
            "  %-14s %-28s %-14s %3d req  %6d B  idx %s-%s"
            % (
                entry["slice"],
                (entry["host"] or "-")[:28],
                (entry["segment"] or "-")[:14],
                entry["requests"],
                entry["bytes"],
                entry["idx"][0],
                entry["idx"][1],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
