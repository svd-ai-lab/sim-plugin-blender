#!/usr/bin/env python3
"""Send one JSON request to a running sim Blender bridge.

Examples:
    python tools/bridge_request.py --port 9876 '{"type":"ping"}'
    echo '{"type":"inspect","name":"scene.summary"}' | python tools/bridge_request.py --port 9876
"""
from __future__ import annotations

import argparse
import json
import socket
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    text = args.payload if args.payload is not None else sys.stdin.read()
    payload = json.loads(text)
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        sock.sendall(body)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break

    raw = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
    parsed = json.loads(raw)
    print(json.dumps(parsed, indent=2, sort_keys=True))
    return 0 if parsed.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
