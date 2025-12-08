#!/usr/bin/env python3
"""
Compare token streams between two captured OpenAI payloads to locate the first divergence.

Example:
    python compare_payload_tokens.py payload_03.json payload_04.json --model gpt-4o

The script uses tiktoken to mirror OpenAI's model-specific tokenization. Make sure the
required encoding files have been downloaded (tiktoken will fetch them automatically and
caches the result). Run in an environment with network access the first time.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import tiktoken


@dataclass
class TokenDiff:
    shared_tokens: int
    first_diff_index: int
    a_extra_tokens: int
    b_extra_tokens: int


def load_payload(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse JSON payload at {path}: {exc}") from exc


def flatten_messages(payload: dict) -> str:
    messages = payload.get("messages")
    if messages is None:
        raise SystemExit("Payload does not contain a 'messages' field.")
    # Preserve ordering and avoid unnecessary whitespace so token offsets line up.
    return json.dumps(messages, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def load_encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except Exception as exc:  # noqa: BLE001 - want full context
        raise SystemExit(
            f"Failed to load tiktoken encoding for model '{model}'. "
            "Run once with network access or pre-download the encoding.\n"
            f"Original error: {exc}"
        ) from exc


def encode_text(enc: tiktoken.Encoding, text: str) -> Sequence[int]:
    return enc.encode(text)


def compare_tokens(tokens_a: Sequence[int], tokens_b: Sequence[int]) -> TokenDiff:
    limit = min(len(tokens_a), len(tokens_b))
    first_diff = limit
    for idx in range(limit):
        if tokens_a[idx] != tokens_b[idx]:
            first_diff = idx
            break
    shared = first_diff
    return TokenDiff(
        shared_tokens=shared,
        first_diff_index=first_diff,
        a_extra_tokens=len(tokens_a) - shared,
        b_extra_tokens=len(tokens_b) - shared,
    )


def display_results(
    diff: TokenDiff,
    tokens_a: Sequence[int],
    tokens_b: Sequence[int],
    enc: tiktoken.Encoding,
    labels: Tuple[str, str],
) -> None:
    a_label, b_label = labels
    print(f"Shared prefix tokens: {diff.shared_tokens}")
    if diff.first_diff_index >= min(len(tokens_a), len(tokens_b)):
        if len(tokens_a) == len(tokens_b):
            print("Token sequences are identical.")
        else:
            winner = a_label if len(tokens_a) > len(tokens_b) else b_label
            print(f"Sequences identical up to min length; {winner} has additional tokens.")
        return

    print(f"First differing token index: {diff.first_diff_index}")
    print(f"{a_label} remaining tokens after divergence: {diff.a_extra_tokens}")
    print(f"{b_label} remaining tokens after divergence: {diff.b_extra_tokens}")

    # Show human-readable snippets around the divergence.
    window = 10
    start = max(diff.first_diff_index - window, 0)
    end = diff.first_diff_index + window

    snippet_a = enc.decode(tokens_a[start:end])
    snippet_b = enc.decode(tokens_b[start:end])
    print("--- Context window (decoded) ---")
    print(f"{a_label}: {snippet_a}")
    print(f"{b_label}: {snippet_b}")

    prefix_text = enc.decode(tokens_a[:diff.first_diff_index])
    print("--- Prefix summary ---")
    print(f"Prefix length (chars): {len(prefix_text)}")
    print(f"Prefix tail: {prefix_text[-200:]}")  # last 200 chars for orientation


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare tokenized OpenAI payload messages and find the first divergence."
    )
    parser.add_argument("payload_a", type=Path, help="First payload JSON file.")
    parser.add_argument("payload_b", type=Path, help="Second payload JSON file.")
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model name whose tokenizer should be used (default: gpt-4o).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    payload_a = load_payload(args.payload_a)
    payload_b = load_payload(args.payload_b)

    text_a = flatten_messages(payload_a)
    text_b = flatten_messages(payload_b)

    enc = load_encoding(args.model)

    tokens_a = encode_text(enc, text_a)
    tokens_b = encode_text(enc, text_b)

    diff = compare_tokens(tokens_a, tokens_b)
    display_results(
        diff,
        tokens_a,
        tokens_b,
        enc,
        labels=(args.payload_a.name, args.payload_b.name),
    )


if __name__ == "__main__":
    main(sys.argv[1:])
