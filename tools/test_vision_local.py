"""Send a vision request with local image file(s) to AIGate API."""

from __future__ import annotations

import argparse
import base64
import os
import sys

import httpx


def _mime_from_path(path: str) -> str:
    ext = path.lower().split(".")[-1]
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "gif":
        return "image/gif"
    if ext == "webp":
        return "image/webp"
    return "image/jpeg"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send vision request with local image(s) to AIGate",
    )
    parser.add_argument(
        "images",
        nargs="+",
        metavar="IMAGE",
        help="Path(s) to image file(s)",
    )
    parser.add_argument(
        "-p",
        "--prompt",
        default="What's in the image?",
        help="Prompt text (default: What's in the image?)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="qwen:qwen3-vl-plus",
        help="Model (default: qwen:qwen3-vl-plus)",
    )
    parser.add_argument(
        "-u",
        "--url",
        default="http://localhost:8000",
        help="AIGate base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    api_key = os.getenv("AIGATE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        print("Set AIGATE_API_KEY or QWEN_API_KEY", file=sys.stderr)
        return 1

    content_parts: list[dict] = [{"type": "text", "text": args.prompt}]

    for img_path in args.images:
        if not os.path.isfile(img_path):
            print(f"File not found: {img_path}", file=sys.stderr)
            return 1
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        mime = _mime_from_path(img_path)
        url = f"data:{mime};base64,{b64}"
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    body = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": content_parts,
            }
        ],
    }

    endpoint = f"{args.url.rstrip('/')}/v1/chat/completions"
    try:
        resp = httpx.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120.0,
        )
    except httpx.ConnectError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return 1

    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 1

    data = resp.json()
    msg = data.get("choices", [{}])[0].get("message", {})
    reply = msg.get("content", "")
    usage = data.get("usage", {})

    print(reply)
    if usage:
        print(f"\n[usage: {usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
