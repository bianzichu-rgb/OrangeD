"""
orangeD — Command-line interface.

Usage:
  oranged extract input.pdf                    # Extract to stdout
  oranged extract input.pdf -o output.md       # Extract to file
  oranged extract input.pdf --toc-only         # TOC only
  oranged analyse output.md                    # Classify sections
  oranged analyse output.md --json             # JSON output
  oranged route input.pdf                      # Show routing decisions
  oranged judge output.md                      # 5D quality score
  oranged benchmark input.pdf                  # Run benchmark
"""

import sys
import argparse
import time
import json
from pathlib import Path


def _fix_encoding():
    """Force UTF-8 on Windows console."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)


def cmd_extract(args):
    from oranged.extract import extract_pdf
    result = extract_pdf(str(args.input), toc_only=args.toc_only)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Written to: {args.output}", file=sys.stderr)
    else:
        print(result)


def cmd_analyse(args):
    from oranged.analyse import analyse_markdown, AnalysisResult
    text = Path(args.input).read_text(encoding="utf-8")
    result = analyse_markdown(text)

    if args.filter:
        result = result.filter_by(args.filter)

    if args.json:
        print(result.to_json())
    else:
        _print_analysis(result)


def _print_analysis(result):
    EMOJI = {
        "SAFETY": "[!]", "TECHNICAL_SPEC": "[S]", "INSTALLATION": "[I]",
        "OPERATION": "[O]", "PARTS": "[P]", "MAINTENANCE": "[M]",
        "TROUBLESHOOTING": "[T]", "FAQ": "[F]", "RECIPE": "[R]", "GENERAL": "[G]",
    }
    print("Document Structure Analysis")
    print("=" * 50)
    for s in result.sections:
        tag = EMOJI.get(s.category, "[?]")
        conf = f"{s.confidence:.0%}"
        print(f"  {tag} {s.category:<18} {s.title}  (L{s.start_line}-{s.end_line}, {conf})")
    print(f"\nFigures: {len(result.figures)}  |  Cross-refs: {len(result.cross_refs)}")


def cmd_route(args):
    from oranged.router import route_pdf, extract_page_features
    import fitz

    strategies = route_pdf(str(args.input))
    doc = fitz.open(str(args.input))

    stats = {}
    for page_num, strategy in sorted(strategies.items()):
        stats[strategy.value] = stats.get(strategy.value, 0) + 1
        if args.verbose:
            features = extract_page_features(doc[page_num])
            print(f"  Page {page_num + 1:>3}: {strategy.value:<20} "
                  f"density={features['text_density']:>6.1f}  "
                  f"icons={features['icon_density']:.3f}  "
                  f"imgs={features['image_count']}")

    doc.close()
    print(f"\nRouting Summary ({len(strategies)} pages):")
    for strategy, count in sorted(stats.items(), key=lambda x: -x[1]):
        pct = count / len(strategies) * 100
        bar = "#" * int(pct / 2)
        print(f"  {strategy:<20} {count:>4} ({pct:5.1f}%)  {bar}")


def cmd_judge(args):
    from oranged.judge import Judge5D
    text = Path(args.input).read_text(encoding="utf-8")
    judge = Judge5D()
    report = judge.evaluate(text, page_count=args.pages or 0)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"Quality Report: {status}  (score: {report.overall_score:.3f})")
        print(f"Dominant category: {report.dominant_category}")
        print(f"Sections: {report.section_count}  |  Figures: {report.figure_count}  |  Cross-refs: {report.crossref_count}")
        print(f"\nDimensions (weighted by {report.dominant_category}):")
        for dim, score in report.dimensions.items():
            bar = "#" * int(score * 20)
            print(f"  {dim:<28} {score:.3f}  {bar}")


def cmd_benchmark(args):
    from oranged.benchmark import run_benchmark
    run_benchmark(str(args.input), args.output)


def main():
    _fix_encoding()

    parser = argparse.ArgumentParser(
        prog="oranged",
        description="orangeD — Hybrid Intelligent PDF-to-Markdown Pipeline",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # extract
    p_ext = sub.add_parser("extract", help="Extract PDF to Markdown")
    p_ext.add_argument("input", help="Path to PDF file")
    p_ext.add_argument("-o", "--output", help="Output Markdown file")
    p_ext.add_argument("--toc-only", action="store_true", help="Extract TOC only")

    # analyse
    p_ana = sub.add_parser("analyse", help="Classify document sections")
    p_ana.add_argument("input", help="Path to Markdown file")
    p_ana.add_argument("-f", "--filter", help="Filter by category")
    p_ana.add_argument("--json", action="store_true", help="JSON output")

    # route
    p_route = sub.add_parser("route", help="Show per-page routing decisions")
    p_route.add_argument("input", help="Path to PDF file")
    p_route.add_argument("-v", "--verbose", action="store_true", help="Show per-page features")

    # judge
    p_judge = sub.add_parser("judge", help="5D quality evaluation")
    p_judge.add_argument("input", help="Path to Markdown file")
    p_judge.add_argument("--pages", type=int, help="Original PDF page count")
    p_judge.add_argument("--json", action="store_true", help="JSON output")

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Run extraction benchmark")
    p_bench.add_argument("input", help="Path to PDF file")
    p_bench.add_argument("-o", "--output", help="Output JSON results file")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "extract": cmd_extract,
        "analyse": cmd_analyse,
        "route": cmd_route,
        "judge": cmd_judge,
        "benchmark": cmd_benchmark,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
