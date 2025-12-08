#!/usr/bin/env python3
"""
Replay captured OpenAI payloads to inspect cache behaviour.

Usage:
    OPENAI_API_KEY=sk-... python replay_openai_payloads.py payload_00.json payload_01.json

If no payload paths are supplied, every *.json file in the payload directory
is replayed in lexical order.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List
import uuid
import time
import os

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "The openai package is required. Install it with `pip install openai`."
    ) from exc


def load_payload(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse JSON payload at {path}: {exc}") from exc


def iter_payload_paths(args: argparse.Namespace) -> Iterable[Path]:
    if args.payloads:
        for name in args.payloads:
            yield (args.directory / name).resolve() if not Path(name).is_absolute() else Path(name)
        return

    for path in sorted(args.directory.glob("payload_*.json")):
        yield path.resolve()


def to_responses_payload(chat_payload: dict) -> dict:
    """Convert a Chat Completions payload into a Responses API payload.

    - messages -> input (flatten text; preserves role labels inline)
    - max_tokens -> max_output_tokens
    - tools.function{name,description,parameters} -> top-level tool {type,function,name,...}
    - drop unsupported fields like parallel_tool_calls
    """
    def _message_content_to_text(content):
        if isinstance(content, str):
            return content
        try:
            parts = []
            for part in content or []:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    if 'text' in part:
                        parts.append(part['text'])
                    elif part.get('type') == 'text' and 'text' in part:
                        parts.append(part['text'])
                    elif 'content' in part and isinstance(part['content'], str):
                        parts.append(part['content'])
            return "\n".join([p for p in parts if p])
        except Exception:
            return ""

    # 1) Build input string from messages
    lines = []
    for m in chat_payload.get('messages', []):
        role = m.get('role', 'user')
        text = _message_content_to_text(m.get('content', ''))
        lines.append(f"{role}: {text}")
    input_text = "\n".join(lines)

    # 2) Base payload: copy everything except fields we remap/remove
    out = {k: v for k, v in chat_payload.items() if k not in {'messages', 'max_tokens', 'tools', 'parallel_tool_calls'}}
    out['input'] = input_text
    if 'max_tokens' in chat_payload and 'max_output_tokens' not in out:
        out['max_output_tokens'] = chat_payload['max_tokens']

    # 3) Tools: function nested -> top-level name
    tools = []
    for t in chat_payload.get('tools', []):
        if isinstance(t, dict) and t.get('type') == 'function' and isinstance(t.get('function'), dict):
            fn = t['function']
            new_tool = {
                'type': 'function',
                'name': fn.get('name'),
            }
            if 'description' in fn:
                new_tool['description'] = fn['description']
            if 'parameters' in fn:
                new_tool['parameters'] = fn['parameters']
            tools.append(new_tool)
        else:
            tools.append(t)
    if tools:
        out['tools'] = tools

    return out


def print_usage(index: int, path: Path, usage) -> None:
    # Support both Chat Completions and Responses usage schemas
    prompt_tokens = getattr(usage, 'prompt_tokens', None)
    #print(f'usage: {usage}')
    if prompt_tokens is None:
        prompt_tokens = getattr(usage, 'input_tokens', None)

    completion_tokens = getattr(usage, 'completion_tokens', None)
    if completion_tokens is None:
        completion_tokens = getattr(usage, 'output_tokens', None)

    total_tokens = getattr(usage, 'total_tokens', None)
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        try:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        except Exception:
            total_tokens = None

    # Extract cached tokens from either prompt_tokens_details or input_tokens_details
    cached_tokens = None
    details = getattr(usage, 'prompt_tokens_details', None)
    if details is not None:
        cached_tokens = getattr(details, 'cached_tokens', None)
    if cached_tokens is None:
        details = getattr(usage, 'input_tokens_details', None)
        if details is not None:
            cached_tokens = getattr(details, 'cached_tokens', None)
    if cached_tokens is None:
        cached_tokens = getattr(usage, 'cached_tokens', None)

    print(
        f"[{index}] {path.name}: total={total_tokens}, prompt={prompt_tokens}, "
        f"completion={completion_tokens}, cached={cached_tokens}"
    )


def replay(payload_paths: List[Path], prompt_cache_key: str | None = None, wait_seconds: float = 1.0) -> None:
    organization = os.environ.get("OPENAI_ORGANIZATION") or os.environ.get("OPENAI_ORG") or "org-HAWXAYFFbrfLFAvEXDTtbhki"
    client = OpenAI(organization=organization)
    for idx, payload_path in enumerate(payload_paths, start=1):
        payload = load_payload(payload_path)
        # Route by shape: send Chat payloads untouched to Chat Completions; use Responses only for Responses-shaped payloads
        if 'messages' in payload:
            print('chat completions used')
            response = client.chat.completions.create(**payload)
        else:
            if prompt_cache_key:
                payload['prompt_cache_key'] = prompt_cache_key
            response = client.responses.create(**payload)
        usage = response.usage
        #print(f'usage: {usage}')
        if usage is None:
            print(f"[{idx}] {payload_path.name}: no usage field present", file=sys.stderr)
            continue
        print_usage(idx, payload_path, usage)
        # Allow cache write to land before the next request
        if idx < len(payload_paths) and wait_seconds and wait_seconds > 0:
            print(f'waiting for {wait_seconds} seconds')
            time.sleep(wait_seconds)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay OpenAI payloads to inspect caching metadata.")
    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing payload JSON files (default: script directory).",
    )
    parser.add_argument(
        "payloads",
        nargs="*",
        help="Specific payload file names to replay (default: every payload_*.json in the directory).",
    )
    parser.add_argument(
        "-k",
        "--prompt-cache-key",
        dest="prompt_cache_key",
        help="Responses API prompt_cache_key to influence routing and cache hits. If omitted, a random key is generated per run.",
    )
    parser.add_argument(
        "-w",
        "--wait-seconds",
        dest="wait_seconds",
        type=float,
        default=0.0,
        help="Seconds to wait between requests to allow cache writes to settle (default: 0.0).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    payload_paths = list(iter_payload_paths(args))
    if not payload_paths:
        raise SystemExit("No payload files found to replay.")
    run_key = args.prompt_cache_key or f"run-{uuid.uuid4().hex}"
    print(f"prompt_cache_key: {run_key}", file=sys.stderr)
    print(f"payload_paths: {payload_paths}", file=sys.stderr)
    replay(payload_paths, run_key, args.wait_seconds)


if __name__ == "__main__":
    main(sys.argv[1:])
