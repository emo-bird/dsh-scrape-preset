"""Extract ONE request from a flow file into a compact JSON for the local model.

Use after flow_index.py / flow_slice.py when you need to hand a single exchange
to the local model (or to paste into the conversation) without the noise of the
whole capture.

Usage:
  python flow_extract.py capture/flows --idx 37
  python flow_extract.py capture/flows --idx 37 -o out/req37.json
  python flow_extract.py capture/flows --idx 37 --cookie-mode full
  python flow_extract.py capture/flows --url-contains /api/conversations
  python flow_extract.py capture/flows --list 20        # show idx of first 20
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

REQ_HEADER_ALLOW = {
    "content-type", "accept", "accept-language", "referer", "origin",
    "user-agent", "authorization", "x-requested-with", "content-length",
}

RESP_HEADER_ALLOW = {
    "content-type", "content-length", "set-cookie", "location", "cache-control",
}


def schema_of(value, depth: int = 0, max_depth: int = 8):
    if depth > max_depth:
        return "..."
    if isinstance(value, dict):
        return {k: schema_of(v, depth + 1, max_depth) for k, v in list(value.items())[:60]}
    if isinstance(value, list):
        return {"__list__": schema_of(value[0], depth + 1, max_depth) if value else None,
                "__count__": len(value)}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def redact(name: str, value: str) -> str:
    """Never print a live credential in full, whatever mode was asked for."""
    lowered = name.lower()
    if lowered == "authorization":
        return value[:14] + "...<redacted>"
    if lowered in ("x-token", "x-sign", "x-signature", "x-api-key", "api-key"):
        return value[:8] + "...<redacted>"
    return value


def pick_headers(headers, allow, cookie_mode):
    out = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered == "cookie":
            if cookie_mode == "full":
                out[name] = value
            elif cookie_mode == "summary":
                names = [p.split("=", 1)[0].strip() for p in value.split(";") if p.strip()]
                out[name] = "<%d cookies: %s>" % (len(names), ", ".join(names[:20]))
            continue
        if lowered in allow or lowered.startswith("x-") or lowered.startswith("sec-"):
            out[name] = redact(name, value[:400])
    return out


def body_text(message, max_chars):
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract one request from a flow file")
    ap.add_argument("flow_file")
    ap.add_argument("--idx", type=int, help="1-based request index (from flow_index.py)")
    ap.add_argument("--url-contains", help="pick the first request whose URL contains this")
    ap.add_argument("--list", type=int, metavar="N", help="just list the first N exchanges and exit")
    ap.add_argument("-o", "--out", help="write JSON here instead of stdout")
    ap.add_argument("--max-body", type=int, default=6000)
    ap.add_argument("--cookie-mode", choices=("summary", "full", "drop"), default="summary")
    args = ap.parse_args()

    try:
        from mitmproxy import http
        from mitmproxy import io as mio
    except Exception as exc:  # pragma: no cover
        print("mitmproxy import failed:", type(exc).__name__, exc)
        print("Install it with:  python -m mitmproxy install" if False else
              "Install it with:  python -m pip install mitmproxy")
        return 2

    if args.list:
        with open(args.flow_file, "rb") as fh:
            reader = mio.FlowReader(fh)
            for index, flow in enumerate(reader.stream(), start=1):
                if not isinstance(flow, http.HTTPFlow):
                    continue
                if index > args.list:
                    break
                code = flow.response.status_code if flow.response else "-"
                print("%4d  %-6s %-4s %s" % (index, flow.request.method, code,
                                             flow.request.pretty_url[:180]))
        return 0

    if args.idx is None and not args.url_contains:
        ap.error("give --idx, --url-contains, or --list")

    found = None
    found_index = None
    with open(args.flow_file, "rb") as fh:
        reader = mio.FlowReader(fh)
        for index, flow in enumerate(reader.stream(), start=1):
            if not isinstance(flow, http.HTTPFlow):
                continue
            if args.url_contains is not None:
                if args.url_contains in flow.request.pretty_url:
                    found, found_index = flow, index
                    break
                continue
            if index == args.idx:
                found, found_index = flow, index
                break

    if found is None:
        print("no matching request found")
        return 1

    req = found.request
    resp = found.response
    record = {
        "idx": found_index,
        "method": req.method,
        "url": req.pretty_url,
        "http_version": req.http_version,
        "req_headers": pick_headers(req.headers, REQ_HEADER_ALLOW, args.cookie_mode),
        "req_body_text": body_text(req, args.max_body),
        "req_body_json": body_json(req),
        "status": resp.status_code if resp else None,
        "resp_headers": pick_headers(resp.headers, RESP_HEADER_ALLOW, args.cookie_mode) if resp else {},
        "resp_schema": None,
        "resp_body_json": None,
        "resp_preview": None,
    }
    if resp is not None:
        decoded = body_json(resp)
        if decoded is not None:
            record["resp_schema"] = schema_of(decoded)
            record["resp_body_json"] = decoded if args.max_body >= 6000 else None
        else:
            record["resp_preview"] = body_text(resp, args.max_body)

    text = json.dumps(record, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s (%d bytes)" % (args.out, len(text.encode("utf-8"))))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())