#!/usr/bin/env python3
"""Send a JSON request file to POST /v1/chat/completions (e.g. data.json)."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(
        description="POST a JSON file to AIGate /v1/chat/completions",
    )
    parser.add_argument(
        "json_file",
        help="Path to JSON request body (e.g. data.json)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("AIGATE_URL", "http://localhost:8000"),
        help="Base URL (default: AIGATE_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=330,
        help="Request timeout in seconds (default: 330)",
    )
    parser.add_argument(
        "--header-timeout",
        type=float,
        default=300,
        help="X-Timeout header value in seconds (default: 300)",
    )
    args = parser.parse_args()

    api_key = os.getenv("AIGATE_DEV_API_KEY")
    if not api_key:
        print("AIGATE_DEV_API_KEY not set. Create a key: pipenv run python tools/seed_dev_api_key.py", file=sys.stderr)
        return 1

    with open(args.json_file, "rb") as f:
        body = f.read()

    try:
        json.loads(body)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {args.json_file}: {e}", file=sys.stderr)
        return 1

    url = f"{args.url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Timeout": str(int(args.header_timeout)),
    }

    print(f"POST {url} (X-Timeout: {args.header_timeout}s, request timeout: {args.timeout}s)", file=sys.stderr)
    try:
        resp = httpx.post(
            url,
            content=body,
            headers=headers,
            timeout=args.timeout,
        )
    except httpx.HTTPError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    print(f"HTTP {resp.status_code}", file=sys.stderr)
    out = resp.text
    if len(out) > 2000:
        print(out[:2000] + "\n... (truncated)", file=sys.stderr)
    else:
        print(out, file=sys.stderr)
    print(resp.text)
    return 0 if resp.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
