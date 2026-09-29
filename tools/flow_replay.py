"""Replay one captured request, optionally with overridden parameters.

Step 4 of the capture workflow: once the local model has summarized an interface,
this tool proves the summary is right by actually calling the endpoint.

SAFETY: defaults to --dry-run (prints the request it WOULD send and sends
nothing). Pass --send to really fire it. Only ever aim it at a site you are
authorized to test, and prefer read-only endpoints.

Usage:
  python flow_replay.py capture/flows --idx 37                    # dry run
  python flow_replay.py capture/flows --idx 37 --send             # really send
  python flow_replay.py capture/flows --idx 37 --send \
      --set-query page=2 --set-query limit=20
  python flow_replay.py capture/flows --idx 37 --send \
      --set-header Referer=https://example.com/list
  python flow_replay.py capture/flows --url-contains /api/list --send --dry-body
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SKIP_REQUEST_HEADERS = {
    "host", "content-length", "connection", "accept-encoding", "transfer-encoding",
    "upgrade", "proxy-connection", "te", "trailer",
}


def apply_query(url: str, pairs: list[str]) -> str:
    if not pairs:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for pair in pairs:
        if "=" not in pair:
            query.pop(pair, None)
            continue
        key, value = pair.split("=", 1)
        query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay one captured request")
    ap.add_argument("flow_file")
    ap.add_argument("--idx", type=int, help="1-based index from flow_index.py")
    ap.add_argument("--url-contains", help="pick the first request whose URL contains this")
    ap.add_argument("--send", action="store_true", help="really send it (default: dry run)")
    ap.add_argument("--set-query", action="append", default=[], metavar="K=V",
                    help="override or add a query parameter (repeatable; 'K' alone drops it)")
    ap.add_argument("--set-header", action="append", default=[], metavar="K:V",
                    help="override or add a request header (repeatable)")
    ap.add_argument("--set-body", help="replace the request body")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--max-response", type=int, default=4000,
                    help="truncate the response body at this many chars")
    ap.add_argument("--dry-body", action="store_true",
                    help="print only the response body, nothing else")
    args = ap.parse_args()

    try:
        from mitmproxy import http
        from mitmproxy import io as mio
    except Exception as exc:  # pragma: no cover
        print("mitmproxy import failed:", type(exc).__name__, exc)
        print("Install it with:  python -m pip install mitmproxy")
        return 2

    if args.idx is None and not args.url_contains:
        ap.error("give --idx or --url-contains")

    found = None
    with open(args.flow_file, "rb") as fh:
        reader = mio.FlowReader(fh)
        for index, flow in enumerate(reader.stream(), start=1):
            if not isinstance(flow, http.HTTPFlow):
                continue
            if args.url_contains is not None:
                if args.url_contains in flow.request.pretty_url:
                    found = flow
                    break
                continue
            if index == args.idx:
                found = flow
                break

    if found is None:
        print("no matching request found")
        return 1

    req = found.request
    url = apply_query(req.pretty_url, args.set_query)
    method = req.method
    headers = {}
    for name, value in req.headers.items():
        if name.lower() in SKIP_REQUEST_HEADERS:
            continue
        headers[name] = value
    for pair in args.set_header:
        if ":" not in pair:
            ap.error("--set-header wants K:V, got %r" % pair)
        key, value = pair.split(":", 1)
        headers[key.strip()] = value.strip()

    if args.set_body is not None:
        body = args.set_body.encode("utf-8")
    else:
        body = req.content or None
    if body and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"

    print("=== request that will be sent ===")
    print("%s %s" % (method, url))
    for name, value in headers.items():
        shown = value
        if name.lower() == "cookie":
            names = [p.split("=", 1)[0].strip() for p in value.split(";") if p.strip()]
            shown = "<%d cookies: %s>" % (len(names), ", ".join(names[:20]))
        elif name.lower() == "authorization":
            shown = value[:14] + "...<redacted>"
        print("  %s: %s" % (name, shown[:200]))
    if body:
        preview = body[:1200].decode("utf-8", errors="replace")
        print("  --- body (%d bytes) ---" % len(body))
        print("  " + preview.replace("\n", "\n  "))
    print()

    if not args.send:
        print("DRY RUN — nothing was sent. Add --send to actually call it.")
        return 0

    request = urllib.request.Request(url, data=body, method=method)
    for name, value in headers.items():
        request.add_header(name, value)

    print("=== response ===")
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as resp:
            raw = resp.read()
            print("status: %s %s" % (resp.status, resp.reason))
            for name, value in resp.headers.items():
                if name.lower() in ("content-type", "content-length", "location", "set-cookie"):
                    print("  %s: %s" % (name, value[:200]))
            text = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        print("status: %s %s" % (exc.code, exc.reason))
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        print("request failed: %s: %s" % (type(exc).__name__, exc))
        return 1

    if args.dry_body:
        print(text[: args.max_response])
        return 0

    try:
        decoded = json.loads(text)
        print("body (json, %d bytes):" % len(raw))
        print(json.dumps(decoded, ensure_ascii=False, indent=2)[: args.max_response])
    except Exception:
        print("body (%d bytes):" % len(raw))
        print(text[: args.max_response])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
