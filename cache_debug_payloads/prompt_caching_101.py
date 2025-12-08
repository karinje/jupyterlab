#!/usr/bin/env python3
"""
Prompt Caching 101 script (Responses API)

Runs two sequential requests with the same prompt_cache_key to demonstrate
input-side caching. Uses your organization ID and OPENAI_API_KEY from env.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from typing import Optional

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "The openai package is required. Install it with `pip install openai`."
    ) from exc


DEFAULT_ORG = "org-HAWXAYFFbrfLFAvEXDTtbhki"


def make_long_context(min_chars: int = 12000) -> str:
    base = (
        "You are a meticulous, efficient assistant. Follow instructions exactly. "
        "This block is static and intended to be cached across calls. "
        "It contains repeated guidance, examples, and policies. "
    )
    # Repeat until comfortably above the cache threshold (tokenization varies)
    chunks = []
    while sum(len(c) for c in chunks) < min_chars:
        chunks.append(base)
    return "".join(chunks)


def create_client(organization: Optional[str]) -> OpenAI:
    org = organization or os.environ.get("OPENAI_ORGANIZATION") or os.environ.get("OPENAI_ORG") or DEFAULT_ORG
    return OpenAI(organization=org)


def run_once(client: OpenAI, model: str, system_text: str, user_text: str, key: Optional[str], max_output_tokens: int = 64):
    # Build Responses API input with a cacheable system part
    inp = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": system_text}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_text}
            ],
        },
    ]

    payload = {
        "model": model,
        "input": inp,
        "max_output_tokens": max_output_tokens,
    }
    if key:
        payload["prompt_cache_key"] = key

    resp = client.responses.create(**payload)
    usage = resp.usage
    # Print compact metrics
    cached = None
    if hasattr(usage, "input_tokens_details") and usage.input_tokens_details:
        cached = getattr(usage.input_tokens_details, "cached_tokens", None)
    print(
        f"tokens: total={getattr(usage,'total_tokens',None)}, "
        f"input={getattr(usage,'input_tokens',None)}, output={getattr(usage,'output_tokens',None)}, "
        f"cached={cached}"
    )


def parse_args(argv):
    p = argparse.ArgumentParser(description="Prompt Caching 101 demo (Responses API)")
    p.add_argument("--model", default="gpt-4o", help="Model to use (default: gpt-4o)")
    p.add_argument("--organization", default=None, help="OpenAI organization ID (defaults to your org)")
    p.add_argument("--prompt", default="Say 'ok'.", help="User prompt text")
    p.add_argument("--wait-seconds", type=float, default=0.0, help="Optional delay between runs")
    p.add_argument("--max-output-tokens", type=int, default=64, help="Max output tokens")
    p.add_argument("--prompt-cache-key", default=None, help="If omitted, a random key is generated per run")
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    client = create_client(args.organization)
    key = args.prompt_cache_key or f"run-{uuid.uuid4().hex}"
    print(f"prompt_cache_key: {key}", file=sys.stderr)

    system_text = make_long_context()
    # First run (seeds cache)
    run_once(client, args.model, system_text, args.prompt, key, args.max_output_tokens)
    if args.wait_seconds and args.wait_seconds > 0:
        time.sleep(args.wait_seconds)
    # Second run (should show cached input tokens if identical and within TTL)
    run_once(client, args.model, system_text, args.prompt, key, args.max_output_tokens)


if __name__ == "__main__":
    main(sys.argv[1:])


