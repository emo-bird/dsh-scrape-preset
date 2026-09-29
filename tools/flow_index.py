"""Build a compact request inventory from a mitmproxy flow file.

This is step 2 of the capture workflow. It reads the flow file and prints / writes
ONE table of every HTTP exchange: index, method, status, size, host, path.
No bodies, no headers -> safe to paste into the conversation.

Usage:
  python flow_index.py <flow-file>                  # print the table
  python flow_index.py <flow-file> -o index.md      # also write markdown
  python flow_index.py <flow-file> --host uooc.net.cn
  python flow_index.py <flow-file> --json index.json
  python flow_index.py <flow-file> --only-api       # skip static assets
"""
from __future__ import annotations

import argparse
import json
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


def human(n: int | None) -> str:
    if not n:
        return "-"
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0
    return "-"


def looks_static(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(STATIC_EXT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Request inventory from a flow file")
    ap.add_argument("flow_file")
    ap.add_argument("-o", "--out", help="write the table as markdown to this path")
    ap.add_argument("--json", dest="json_out", help="write machine-readable rows to this path")
    ap.add_argument("--host", action="append", default=[], help="only this host (repeatable)")
    ap.add_argument("--only-api", action="store_true", help="drop static-asset requests")
    ap.add_argument("--min-size", type=int, default=0, help="only responses >= this many bytes")
    ap.add_argument("--max-rows", type=int, default=500, help="cap printed rows")
    args = ap.parse_args()

    try:
        from mitmproxy import http
        from mitmproxy import io as mio
    except Exception as exc:  # pragma: no cover
        print("mitmproxy import failed:", type(exc).__name__, exc)
        print("Install it with:  python -m pip install mitmproxy")
        return 2

    rows: list[dict] = []
    with open(args.flow_file, "rb") as fh:
        reader = mio.FlowReader(fh)
        for index, flow in enumerate(reader.stream(), start=1):
            if not isinstance(flow, http.HTTPFlow):
                continue
            req = flow.request
            resp = flow.response
            path = urlsplit(req.pretty_url).path or "/"
            if args.host and req.host not in args.host:
                continue
            if args.only_api and looks_static(path):
                continue
            size = len(resp.content) if (resp and resp.content) else 0
            if size < args.min_size:
                continue
            ctype = ""
            if resp and resp.headers.get("content-type"):
                ctype = resp.headers["content-type"].split(";")[0].strip()
            rows.append(
                {
                    "idx": index,
                    "method": req.method,
                    "status": resp.status_code if resp else None,
                    "size": size,
                    "host": req.host,
                    "path": path,
                    "query": urlsplit(req.pretty_url).query,
                    "ctype": ctype,
                    "req_body": len(req.content) if req.content else 0,
                    "url": req.pretty_url,
                }
            )

    print("total requests: %d" % len(rows))
    print()
    header = "| idx | method | status | resp | req | host | path | ctype |"
    print(header)
    print("|---|---|---|---|---|---|---|---|")
    for row in rows[: args.max_rows]:
        print(
            "| %d | %s | %s | %s | %s | %s | %s | %s |"
            % (
                row["idx"],
                row["method"],
                row["status"] if row["status"] is not None else "-",
                human(row["size"]),
                human(row["req_body"]) if row["req_body"] else "-",
                row["host"],
                row["path"][:80],
                row["ctype"] or "-",
            )
        )
    if len(rows) > args.max_rows:
        print("... (%d more rows truncated)" % (len(rows) - args.max_rows))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("# 抓包请求总表\n\n")
            fh.write("来源文件：`%s`\n\n" % args.flow_file)
            fh.write("请求总数：%d\n\n" % len(rows))
            fh.write(header + "\n")
            fh.write("|---|---|---|---|---|---|---|---|\n")
            for row in rows:
                fh.write(
                    "| %d | %s | %s | %s | %s | %s | %s | %s |\n"
                    % (
                        row["idx"],
                        row["method"],
                        row["status"] if row["status"] is not None else "-",
                        human(row["size"]),
                        human(row["req_body"]) if row["req_body"] else "-",
                        row["host"],
                        row["path"][:120],
                        row["ctype"] or "-",
                    )
                )
        print("\nwrote %s" % args.out)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        print("wrote %s" % args.json_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())