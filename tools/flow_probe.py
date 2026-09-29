"""Probe a mitmproxy flow file: format, flow count, hosts, methods, statuses.

Read-only, never loads the whole file into memory.

Usage:
  python flow_probe.py <flow-file> [--top 25] [--samples 20]
"""
from __future__ import annotations

import argparse
import collections
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - older runtimes
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe a mitmproxy flow file")
    ap.add_argument("flow_file", help="path to a .flow / flows file written by mitmdump -w")
    ap.add_argument("--top", type=int, default=25, help="how many hosts to list")
    ap.add_argument("--samples", type=int, default=20, help="how many sample URLs to print")
    args = ap.parse_args()

    with open(args.flow_file, "rb") as fh:
        head = fh.read(64)
    print("=== head bytes ===")
    print(repr(head[:48]))
    print("legacy magic '!mitmproxy' :", head.startswith(b"!mitmproxy"))
    if not head.startswith(b"!mitmproxy"):
        print("NOTE: modern mitmproxy writes a tnetstring stream header instead of the")
        print("      legacy '!mitmproxy' magic. Not an error by itself; parsing below")
        print("      is what decides whether this file is readable.")

    try:
        from mitmproxy import http
        from mitmproxy import io as mio
    except Exception as exc:  # pragma: no cover
        print("=== mitmproxy import FAILED ===")
        print(type(exc).__name__, exc)
        print("Install it with:  python -m pip install mitmproxy")
        return 2

    total = 0
    http_flows = 0
    hosts: collections.Counter = collections.Counter()
    methods: collections.Counter = collections.Counter()
    statuses: collections.Counter = collections.Counter()
    samples: list[str] = []

    with open(args.flow_file, "rb") as fh:
        reader = mio.FlowReader(fh)
        for flow in reader.stream():
            total += 1
            if not isinstance(flow, http.HTTPFlow):
                continue
            http_flows += 1
            req = flow.request
            hosts[req.host] += 1
            methods[req.method] += 1
            code = flow.response.status_code if flow.response else None
            statuses[code] += 1
            if len(samples) < args.samples:
                shown = code if code is not None else "NO-RESPONSE"
                samples.append("%s %s -> %s" % (req.method, req.pretty_url, shown))

    print("=== totals ===")
    print("flows:", total, "| http:", http_flows)
    print("=== methods ===", methods.most_common())
    print("=== statuses ===", statuses.most_common(10))
    print("=== top %d hosts ===" % args.top)
    for host, count in hosts.most_common(args.top):
        print("  %6d  %s" % (count, host))
    print("=== samples ===")
    for sample in samples:
        print("  " + sample[:240])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
