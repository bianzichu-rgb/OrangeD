"""
orangeD Quick Start — Extract, Analyse, Judge in 10 lines.
"""

from oranged import extract_pdf, analyse_markdown, Judge5D

# 1. Extract PDF to Markdown
md = extract_pdf("manual.pdf")
print(f"Extracted {len(md)} chars")

# 2. Classify sections
analysis = analyse_markdown(md)
for section in analysis.sections:
    print(f"  [{section.category}] {section.title} (confidence: {section.confidence:.0%})")

# 3. Quality check
judge = Judge5D()
report = judge.evaluate(md, page_count=42)
print(f"\nQuality: {report.overall_score:.3f} ({'PASS' if report.passed else 'FAIL'})")
for dim, score in report.dimensions.items():
    print(f"  {dim}: {score:.3f}")
