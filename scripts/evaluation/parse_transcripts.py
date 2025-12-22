#!/usr/bin/env python3
"""
Parse interview transcripts from CSV into evaluation pairs.

Each pair contains:
- context: the conversation history up to the current answer
- current_answer: the user's most recent response
- original_question: the interviewer's next follow-up question
"""

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path
from typing import Optional


def parse_dialogue(text: str) -> list[dict]:
    """Parse a transcript text into dialogue turns."""
    turns = []

    # Split on speaker prefixes (Assistant:, User:, AI:)
    # The pattern captures the speaker and the content
    pattern = r"(Assistant|User|AI):\s*"

    # Find all matches with positions
    parts = re.split(pattern, text)

    # parts will be: ['', 'Assistant', 'content', 'User', 'content', ...]
    i = 1
    while i < len(parts) - 1:
        speaker = parts[i]
        content = parts[i + 1].strip()
        if content:
            # Normalize speaker: 'Assistant' and 'AI' both represent the interviewer
            role = "interviewer" if speaker in ("Assistant", "AI") else "user"
            turns.append({"speaker": speaker, "role": role, "content": content})
        i += 2

    return turns


def build_pairs(transcript_id: str, turns: list[dict]) -> list[dict]:
    """Build Q&A evaluation pairs from dialogue turns.

    For each user answer followed by an interviewer question, create a pair:
    - context: all turns up to but not including the current answer
    - current_answer: the user's response
    - original_question: the interviewer's follow-up question
    """
    pairs = []
    pair_id = 0

    for i, turn in enumerate(turns):
        # Look for pattern: user answer followed by interviewer question
        if turn["role"] == "user" and i + 1 < len(turns):
            next_turn = turns[i + 1]
            if next_turn["role"] == "interviewer":
                # Build context from all previous turns
                context_parts = []
                for prev_turn in turns[:i]:
                    prefix = "Q" if prev_turn["role"] == "interviewer" else "A"
                    context_parts.append(f"{prefix}: {prev_turn['content']}")

                pair = {
                    "eval_id": f"{transcript_id}_pair_{pair_id}",
                    "transcript_id": transcript_id,
                    "pair_id": pair_id,
                    "context": "\n".join(context_parts) if context_parts else "",
                    "current_answer": turn["content"],
                    "original_question": next_turn["content"],
                }
                pairs.append(pair)
                pair_id += 1

    return pairs


def parse_transcripts(
    csv_path: Path,
    sample_size: Optional[int] = None,
    min_pair_index: Optional[int] = None,
    max_pair_index: Optional[int] = None,
) -> dict:
    """Parse all transcripts from a CSV file.

    Args:
        csv_path: Path to the CSV file
        sample_size: If set, randomly sample this many pairs
        min_pair_index: If set, only include pairs with pair_id >= min_pair_index
                       (excludes early intro/warm-up exchanges)
        max_pair_index: If set, only include pairs with pair_id < max_pair_index
                       (excludes late-stage "goodbye" exchanges)
    """
    # Extract dataset name from filename (e.g., 'creatives' from 'creatives_transcripts.csv')
    dataset_name = csv_path.stem.replace("_transcripts", "")

    all_pairs = []
    transcript_count = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transcript_id = row["transcript_id"]
            text = row["text"]

            turns = parse_dialogue(text)
            pairs = build_pairs(transcript_id, turns)

            # Filter pairs by index range (substantive middle portion)
            if min_pair_index is not None:
                pairs = [p for p in pairs if p["pair_id"] >= min_pair_index]
            if max_pair_index is not None:
                pairs = [p for p in pairs if p["pair_id"] < max_pair_index]

            all_pairs.extend(pairs)
            transcript_count += 1

    # Sample if requested
    sampled = False
    if sample_size and sample_size < len(all_pairs):
        random.seed(42)  # Reproducible sampling
        all_pairs = random.sample(all_pairs, sample_size)
        sampled = True
        # Re-sort by eval_id for consistent ordering
        all_pairs.sort(key=lambda x: x["eval_id"])

    return {
        "dataset": dataset_name,
        "total_transcripts": transcript_count,
        "total_pairs": len(all_pairs),
        "sampled": sampled,
        "sample_size": sample_size if sampled else None,
        "min_pair_index": min_pair_index,
        "max_pair_index": max_pair_index,
        "pairs": all_pairs,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse interview transcripts into evaluation pairs")
    parser.add_argument("--dataset", "-d", default="creatives", help="Dataset name (creatives, scientists, workforce)")
    parser.add_argument("--sample", "-s", type=int, default=None, help="Sample N pairs for testing")
    parser.add_argument(
        "--min-pair", type=int, default=None, help="Only include pairs with index >= N (excludes early intro exchanges)"
    )
    parser.add_argument(
        "--max-pair",
        "-m",
        type=int,
        default=None,
        help='Only include pairs with index < N (excludes late "bye" exchanges)',
    )
    parser.add_argument("--input-dir", default="random", help="Directory containing CSV files")
    parser.add_argument("--output-dir", default="results/parsed", help="Directory for output JSON files")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    args = parser.parse_args()

    # Find the CSV file
    script_dir = Path(__file__).parent.parent.parent
    csv_path = script_dir / args.input_dir / f"{args.dataset}_transcripts.csv"

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Parsing {csv_path}...", file=sys.stderr)

    # Parse transcripts
    result = parse_transcripts(csv_path, args.sample, args.min_pair, args.max_pair)

    # Write output
    output_dir = script_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{args.dataset}_pairs.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    if not args.quiet:
        print(f"Parsed {result['total_transcripts']} transcripts", file=sys.stderr)
        print(f"Generated {result['total_pairs']} evaluation pairs", file=sys.stderr)
        min_idx = result["min_pair_index"] or 0
        max_idx = result["max_pair_index"]
        if result["min_pair_index"] or result["max_pair_index"]:
            range_str = f"{min_idx}-{max_idx - 1 if max_idx else 'end'}"
            print(f"Filtered to pairs {range_str} per transcript", file=sys.stderr)
        if result["sampled"]:
            print(f"Sampled {result['sample_size']} pairs", file=sys.stderr)
        print(f"Output: {output_path}", file=sys.stderr)

    # Print path to stdout for scripting
    print(output_path)


if __name__ == "__main__":
    main()
