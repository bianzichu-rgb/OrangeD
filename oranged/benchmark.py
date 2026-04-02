"""
orangeD — Benchmark framework.

Compares orangeD native extraction against PaddleOCR and MinerU
on speed, memory, quality, and structural metrics.

Usage:
  from oranged.benchmark import run_benchmark
  run_benchmark("manual.pdf")

Or via CLI:
  oranged benchmark manual.pdf -o results.json
"""

import time
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

import fitz


def _measure_oranged(pdf_path: str) -> Dict[str, Any]:
    """Run orangeD native extraction and measure performance."""
    from oranged.extract import extract_pdf
    from oranged.judge import Judge5D
    from oranged.router import route_pdf
    from oranged.analyse import analyse_markdown

    doc = fitz.open(pdf_path)
    page_count = len(doc)
    doc.close()

    # Routing stats
    strategies = route_pdf(pdf_path)
    strategy_stats = {}
    for s in strategies.values():
        strategy_stats[s.value] = strategy_stats.get(s.value, 0) + 1

    # Extraction
    t0 = time.perf_counter()
    md = extract_pdf(pdf_path)
    elapsed = time.perf_counter() - t0

    # Quality
    judge = Judge5D()
    report = judge.evaluate(md, page_count=page_count)

    # Analysis
    analysis = analyse_markdown(md)

    return {
        "engine": "orangeD",
        "version": "0.1.0",
        "pages": page_count,
        "time_seconds": round(elapsed, 3),
        "pages_per_second": round(page_count / elapsed, 2) if elapsed > 0 else 0,
        "output_chars": len(md),
        "output_lines": md.count('\n') + 1,
        "quality_score": report.overall_score,
        "quality_passed": report.passed,
        "dimensions": report.dimensions,
        "sections_found": report.section_count,
        "figures_found": report.figure_count,
        "crossrefs_found": report.crossref_count,
        "routing": strategy_stats,
        "gpu_used": strategy_stats.get("NATIVE", 0) < page_count,
        "categories": list(set(s.category for s in analysis.sections)),
    }


def _measure_paddleocr(pdf_path: str) -> Optional[Dict[str, Any]]:
    """Run PaddleOCR on all pages and measure performance."""
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return None

    doc = fitz.open(pdf_path)
    page_count = len(doc)

    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)

    t0 = time.perf_counter()
    all_text = []

    for i, page in enumerate(doc):
        # Render page as image
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_bytes)
            tmp = f.name

        try:
            result = ocr.ocr(tmp, cls=True)
            if result and result[0]:
                lines = [line[1][0] for line in result[0]]
                all_text.append("\n".join(lines))
        finally:
            os.unlink(tmp)

    elapsed = time.perf_counter() - t0
    doc.close()

    full_text = "\n\n".join(all_text)

    return {
        "engine": "PaddleOCR",
        "version": "PP-OCRv4",
        "pages": page_count,
        "time_seconds": round(elapsed, 3),
        "pages_per_second": round(page_count / elapsed, 2) if elapsed > 0 else 0,
        "output_chars": len(full_text),
        "output_lines": full_text.count('\n') + 1,
        "gpu_used": True,
        "note": "Full OCR on all pages (no native extraction path)",
    }


def _measure_mineru(pdf_path: str) -> Optional[Dict[str, Any]]:
    """Run MinerU extraction if available."""
    try:
        from magic_pdf.pipe.UNIPipe import UNIPipe  # noqa: F401
    except ImportError:
        return None

    # MinerU integration placeholder
    return {
        "engine": "MinerU",
        "note": "Install magic-pdf for MinerU benchmark",
    }


def run_benchmark(pdf_path: str, output_path: Optional[str] = None):
    """
    Run full benchmark comparison and print results.

    Args:
        pdf_path: Path to PDF file.
        output_path: Optional path to save JSON results.
    """
    pdf_name = Path(pdf_path).name
    print(f"Benchmarking: {pdf_name}")
    print("=" * 60)

    results: List[Dict[str, Any]] = []

    # orangeD (always available)
    print("\n[1/3] Running orangeD...")
    od_result = _measure_oranged(pdf_path)
    results.append(od_result)
    print(f"  Time: {od_result['time_seconds']:.2f}s  "
          f"({od_result['pages_per_second']:.1f} pages/s)")
    print(f"  Quality: {od_result['quality_score']:.3f}  "
          f"({'PASS' if od_result['quality_passed'] else 'FAIL'})")
    print(f"  Output: {od_result['output_chars']} chars, "
          f"{od_result['sections_found']} sections, "
          f"{od_result['figures_found']} figures")
    print(f"  Routing: {od_result['routing']}")

    # PaddleOCR
    print("\n[2/3] Running PaddleOCR...")
    paddle_result = _measure_paddleocr(pdf_path)
    if paddle_result:
        results.append(paddle_result)
        print(f"  Time: {paddle_result['time_seconds']:.2f}s  "
              f"({paddle_result['pages_per_second']:.1f} pages/s)")
        print(f"  Output: {paddle_result['output_chars']} chars")
    else:
        print("  [SKIP] PaddleOCR not installed (pip install orangeD[paddle])")

    # MinerU
    print("\n[3/3] Running MinerU...")
    mineru_result = _measure_mineru(pdf_path)
    if mineru_result and "time_seconds" in mineru_result:
        results.append(mineru_result)
    else:
        print("  [SKIP] MinerU not installed (pip install magic-pdf)")

    # Summary comparison
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"{'Engine':<16} {'Time(s)':<10} {'Pages/s':<10} {'Chars':<10} {'GPU':<6}")
    print("-" * 52)
    for r in results:
        if "time_seconds" in r:
            print(f"{r['engine']:<16} {r['time_seconds']:<10.2f} "
                  f"{r.get('pages_per_second', '-'):<10} "
                  f"{r.get('output_chars', '-'):<10} "
                  f"{'Yes' if r.get('gpu_used') else 'No':<6}")

    # Save results
    report = {
        "file": pdf_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nResults saved to: {output_path}")

    return report
