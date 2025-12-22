#!/usr/bin/env python3
"""
Analyze evaluation results from the question evaluation pipeline.

Features:
- Win rate calculation and breakdown
- Timing statistics
- Failure analysis
- Multi-run comparison
"""

import argparse
import json
import sys
from pathlib import Path


def load_results(filepath: Path) -> dict:
    """Load evaluation results from JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def is_humanness_evaluation(metadata: dict) -> bool:
    """Check if this is a humanness evaluation (vs question evaluation)."""
    return "human_wins" in metadata or "human_detection_rate" in metadata


def analyze_humanness(results: dict, verbose: bool = False) -> dict:
    """Analyze a humanness evaluation run."""
    metadata = results["metadata"]
    evaluations = results["evaluations"]
    failures = results.get("failures", [])

    total = metadata["total_evaluations"]
    human_wins = metadata.get("human_wins", 0)
    agent_wins = metadata.get("agent_wins", 0)
    failure_count = metadata.get("failures", len(failures))

    # Calculate rates
    detection_rate = human_wins / total if total > 0 else 0
    agent_rate = agent_wins / total if total > 0 else 0

    # Timing statistics
    collect_times = [e["collection_time_ms"] for e in evaluations if "collection_time_ms" in e]
    eval_times = [e["evaluation_time_ms"] for e in evaluations if "evaluation_time_ms" in e]

    def calc_stats(times):
        if not times:
            return {"avg": 0, "min": 0, "max": 0, "total": 0}
        return {"avg": sum(times) / len(times), "min": min(times), "max": max(times), "total": sum(times)}

    collect_stats = calc_stats(collect_times)
    eval_stats = calc_stats(eval_times)

    # Analyze which agents were most often chosen as "most human"
    agent_chosen_counts: dict[str, int] = {}
    for e in evaluations:
        source = e.get("most_human_source", "unknown")
        agent_chosen_counts[source] = agent_chosen_counts.get(source, 0) + 1

    analysis = {
        "evaluation_type": "humanness",
        "dataset": metadata.get("dataset", "unknown"),
        "batch_id": metadata.get("batch_id", "unknown"),
        "agents": metadata.get("agents", "unknown"),
        "include_human": metadata.get("include_human", True),
        "total_evaluations": total,
        "human_wins": human_wins,
        "agent_wins": agent_wins,
        "failures": failure_count,
        "human_detection_rate": detection_rate,
        "agent_rate": agent_rate,
        "agent_chosen_breakdown": agent_chosen_counts,
        "collection_time_stats": collect_stats,
        "evaluation_time_stats": eval_stats,
        "start_time": metadata.get("start_time"),
        "end_time": metadata.get("end_time"),
    }

    if verbose and failures:
        analysis["failure_details"] = failures

    return analysis


def analyze_questions(results: dict, verbose: bool = False) -> dict:
    """Analyze a question evaluation run."""
    metadata = results["metadata"]
    evaluations = results["evaluations"]
    failures = results.get("failures", [])

    # Basic stats from metadata
    total = metadata["total_evaluations"]
    jane_wins = metadata["jane_wins"]
    original_wins = metadata["original_wins"]
    ties = metadata["ties"]
    failure_count = metadata.get("failures", len(failures))

    # Calculate rates
    win_rate = jane_wins / total if total > 0 else 0
    loss_rate = original_wins / total if total > 0 else 0
    tie_rate = ties / total if total > 0 else 0

    # Timing statistics
    gen_times = [e["generation_time_ms"] for e in evaluations if "generation_time_ms" in e]
    eval_times = [e["evaluation_time_ms"] for e in evaluations if "evaluation_time_ms" in e]

    def calc_stats(times):
        if not times:
            return {"avg": 0, "min": 0, "max": 0, "total": 0}
        return {"avg": sum(times) / len(times), "min": min(times), "max": max(times), "total": sum(times)}

    gen_stats = calc_stats(gen_times)
    eval_stats = calc_stats(eval_times)

    # Analyze judgment distribution
    judgment_counts = {0: 0, 1: 0, 2: 0, -1: 0}
    for e in evaluations:
        j = e.get("judgment", -1)
        judgment_counts[j] = judgment_counts.get(j, 0) + 1

    analysis = {
        "evaluation_type": "questions",
        "dataset": metadata.get("dataset", "unknown"),
        "batch_id": metadata.get("batch_id", "unknown"),
        "total_evaluations": total,
        "jane_wins": jane_wins,
        "original_wins": original_wins,
        "ties": ties,
        "failures": failure_count,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "tie_rate": tie_rate,
        "generation_time_stats": gen_stats,
        "evaluation_time_stats": eval_stats,
        "start_time": metadata.get("start_time"),
        "end_time": metadata.get("end_time"),
    }

    if verbose and failures:
        analysis["failure_details"] = failures

    return analysis


def analyze_single(results: dict, verbose: bool = False) -> dict:
    """Analyze a single evaluation run (auto-detect type)."""
    metadata = results["metadata"]

    if is_humanness_evaluation(metadata):
        return analyze_humanness(results, verbose)
    else:
        return analyze_questions(results, verbose)


def print_humanness_analysis(analysis: dict, filepath: str = None):
    """Print humanness evaluation analysis results."""
    print()
    print("=" * 60)
    if filepath:
        print(f"Results: {filepath}")
    print(f"Dataset: {analysis['dataset']}")
    print(f"Agents:  {analysis['agents']}")
    print(f"Batch ID: {analysis['batch_id']}")
    print("=" * 60)
    print()

    # Humanness Summary
    total = analysis["total_evaluations"]
    print("HUMANNESS EVALUATION SUMMARY")
    print("-" * 40)
    print(f"Total evaluations: {total}")
    print(f"Include human:     {analysis['include_human']}")
    print()

    human_wins = analysis["human_wins"]
    agent_wins = analysis["agent_wins"]
    fails = analysis["failures"]

    # Visual bar
    if total > 0:
        bar_width = 40
        human_bar = int(human_wins / total * bar_width)
        agent_bar = bar_width - human_bar

        print(f"Human wins:  {human_wins:4d} ({analysis['human_detection_rate'] * 100:5.1f}%) {'█' * human_bar}")
        print(f"Agent wins:  {agent_wins:4d} ({analysis['agent_rate'] * 100:5.1f}%) {'█' * agent_bar}")
        if fails > 0:
            print(f"Failures:    {fails:4d}")
    print()

    # Agent breakdown
    breakdown = analysis.get("agent_chosen_breakdown", {})
    if breakdown:
        print("WHO WAS CHOSEN AS MOST HUMAN")
        print("-" * 40)
        for agent, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            pct = count / total * 100 if total > 0 else 0
            print(f"  {agent:<20} {count:4d} ({pct:5.1f}%)")
        print()

    # Timing Stats
    print("TIMING STATISTICS")
    print("-" * 40)
    collect = analysis["collection_time_stats"]
    eva = analysis["evaluation_time_stats"]

    print("Answer Collection:")
    print(
        f"  Average: {collect['avg'] / 1000:.2f}s | Min: {collect['min'] / 1000:.2f}s | Max: {collect['max'] / 1000:.2f}s"
    )
    print("Evaluation (Judge):")
    print(f"  Average: {eva['avg'] / 1000:.2f}s | Min: {eva['min'] / 1000:.2f}s | Max: {eva['max'] / 1000:.2f}s")
    print(f"Total processing time: {(collect['total'] + eva['total']) / 1000 / 60:.1f} minutes")
    print()

    # Timestamps
    if analysis.get("start_time") and analysis.get("end_time"):
        print(f"Start: {analysis['start_time']}")
        print(f"End:   {analysis['end_time']}")
        print()

    # Failure details
    if "failure_details" in analysis and analysis["failure_details"]:
        print("FAILURES")
        print("-" * 40)
        for f in analysis["failure_details"]:
            print(f"  {f.get('eval_id', 'unknown')}: {f.get('error', 'unknown error')}")
        print()


def print_questions_analysis(analysis: dict, filepath: str = None):
    """Print question evaluation analysis results."""
    print()
    print("=" * 60)
    if filepath:
        print(f"Results: {filepath}")
    print(f"Dataset: {analysis['dataset']}")
    print(f"Batch ID: {analysis['batch_id']}")
    print("=" * 60)
    print()

    # Win/Loss Summary
    total = analysis["total_evaluations"]
    print("QUESTION EVALUATION SUMMARY")
    print("-" * 40)
    print(f"Total evaluations: {total}")
    print()

    jane = analysis["jane_wins"]
    orig = analysis["original_wins"]
    ties = analysis["ties"]
    fails = analysis["failures"]

    # Visual bar
    if total > 0:
        bar_width = 40
        jane_bar = int(jane / total * bar_width)
        orig_bar = int(orig / total * bar_width)
        tie_bar = bar_width - jane_bar - orig_bar

        print(f"Jane wins:     {jane:4d} ({analysis['win_rate'] * 100:5.1f}%) {'█' * jane_bar}")
        print(f"Original wins: {orig:4d} ({analysis['loss_rate'] * 100:5.1f}%) {'█' * orig_bar}")
        print(f"Ties:          {ties:4d} ({analysis['tie_rate'] * 100:5.1f}%) {'█' * tie_bar}")
        if fails > 0:
            print(f"Failures:      {fails:4d}")
    print()

    # Timing Stats
    print("TIMING STATISTICS")
    print("-" * 40)
    gen = analysis["generation_time_stats"]
    eva = analysis["evaluation_time_stats"]

    print("Generation (Jane):")
    print(f"  Average: {gen['avg'] / 1000:.2f}s | Min: {gen['min'] / 1000:.2f}s | Max: {gen['max'] / 1000:.2f}s")
    print("Evaluation (Judge):")
    print(f"  Average: {eva['avg'] / 1000:.2f}s | Min: {eva['min'] / 1000:.2f}s | Max: {eva['max'] / 1000:.2f}s")
    print(f"Total processing time: {(gen['total'] + eva['total']) / 1000 / 60:.1f} minutes")
    print()

    # Timestamps
    if analysis.get("start_time") and analysis.get("end_time"):
        print(f"Start: {analysis['start_time']}")
        print(f"End:   {analysis['end_time']}")
        print()

    # Failure details
    if "failure_details" in analysis and analysis["failure_details"]:
        print("FAILURES")
        print("-" * 40)
        for f in analysis["failure_details"]:
            print(f"  [{f.get('stage', 'unknown')}] {f.get('eval_id', 'unknown')}: {f.get('error', 'unknown error')}")
        print()


def print_analysis(analysis: dict, filepath: str = None):
    """Print analysis results in a formatted way (auto-detect type)."""
    eval_type = analysis.get("evaluation_type", "questions")

    if eval_type == "humanness":
        print_humanness_analysis(analysis, filepath)
    else:
        print_questions_analysis(analysis, filepath)


def compare_runs(results_list: list[tuple[str, dict]]):
    """Compare multiple evaluation runs."""
    print()
    print("=" * 80)
    print("COMPARISON ACROSS RUNS")
    print("=" * 80)
    print()

    # Check if all are humanness or all are questions
    analyses = [(filepath, analyze_single(results)) for filepath, results in results_list]
    humanness_runs = [a for a in analyses if a[1].get("evaluation_type") == "humanness"]
    question_runs = [a for a in analyses if a[1].get("evaluation_type") == "questions"]

    # Print humanness comparisons
    if humanness_runs:
        print("HUMANNESS EVALUATIONS")
        print(f"{'Run':<30} {'Total':>8} {'Human':>8} {'Agent':>8} {'Detect%':>8}")
        print("-" * 80)

        for filepath, analysis in humanness_runs:
            name = Path(filepath).stem[:28]
            print(
                f"{name:<30} {analysis['total_evaluations']:>8} {analysis['human_wins']:>8} "
                f"{analysis['agent_wins']:>8} {analysis['human_detection_rate'] * 100:>7.1f}%"
            )
        print()

        if len(humanness_runs) > 1:
            rates = [a["human_detection_rate"] for _, a in humanness_runs]
            avg_rate = sum(rates) / len(rates)
            print(f"Average human detection rate: {avg_rate * 100:.1f}%")
            print(f"Range: {min(rates) * 100:.1f}% - {max(rates) * 100:.1f}%")
            print()

    # Print question comparisons
    if question_runs:
        print("QUESTION EVALUATIONS")
        print(f"{'Run':<30} {'Total':>8} {'Jane':>8} {'Orig':>8} {'Tie':>6} {'Win %':>8}")
        print("-" * 80)

        for filepath, analysis in question_runs:
            name = Path(filepath).stem[:28]
            print(
                f"{name:<30} {analysis['total_evaluations']:>8} {analysis['jane_wins']:>8} "
                f"{analysis['original_wins']:>8} {analysis['ties']:>6} {analysis['win_rate'] * 100:>7.1f}%"
            )
        print()

        if len(question_runs) > 1:
            win_rates = [a["win_rate"] for _, a in question_runs]
            avg_rate = sum(win_rates) / len(win_rates)
            print(f"Average win rate across runs: {avg_rate * 100:.1f}%")
            print(f"Range: {min(win_rates) * 100:.1f}% - {max(win_rates) * 100:.1f}%")
            print()


def export_summary(analysis: dict, output_path: Path):
    """Export analysis summary to JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"Summary exported to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze question evaluation results")
    parser.add_argument("files", nargs="+", help="JSON result files to analyze")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed failure information")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON instead of formatted text")
    parser.add_argument("--export", "-e", type=str, help="Export summary to specified JSON file")
    parser.add_argument("--compare", "-c", action="store_true", help="Compare multiple runs side by side")

    args = parser.parse_args()

    # Load all result files
    results_list = []
    for filepath in args.files:
        # Skip empty paths
        if not filepath or not filepath.strip():
            print("Warning: Empty file path provided, skipping", file=sys.stderr)
            continue

        path = Path(filepath)

        # Skip directories
        if path.is_dir():
            print(f"Warning: Path is a directory, not a file: {filepath}", file=sys.stderr)
            continue

        if not path.exists():
            # Try adding project root
            project_root = Path(__file__).parent.parent.parent
            path = project_root / filepath

        if not path.exists():
            print(f"Warning: File not found: {filepath}", file=sys.stderr)
            continue

        if path.is_dir():
            print(f"Warning: Path is a directory, not a file: {filepath}", file=sys.stderr)
            continue

        try:
            results = load_results(path)
            results_list.append((str(path), results))
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {filepath}: {e}", file=sys.stderr)
            continue

    if not results_list:
        print("Error: No valid result files found", file=sys.stderr)
        sys.exit(1)

    # Compare mode
    if args.compare and len(results_list) > 1:
        compare_runs(results_list)
        return

    # Analyze each file
    for filepath, results in results_list:
        analysis = analyze_single(results, verbose=args.verbose)

        if args.json:
            print(json.dumps(analysis, indent=2, ensure_ascii=False))
        else:
            print_analysis(analysis, filepath)

        if args.export:
            export_path = Path(args.export)
            if len(results_list) > 1:
                # Multiple files - add suffix
                export_path = export_path.parent / f"{export_path.stem}_{Path(filepath).stem}.json"
            export_summary(analysis, export_path)


if __name__ == "__main__":
    main()
