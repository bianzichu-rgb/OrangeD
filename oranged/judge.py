"""
orangeD — 5-Dimensional Quality Judge

Evaluates extraction quality across 5 dimensions with partition-aware weights.
Ported from CognoLiving 2.0 Judge V5.

Dimensions:
  1. format_compliance    — Markdown syntax validity
  2. heading_hierarchy    — No skipped levels, no orphan nodes
  3. content_accuracy     — Information preservation from source
  4. structural_consistency — Cross-refs intact, reading order correct
  5. table_integrity      — Row/column logical closure
"""

import re
from typing import Dict, Any, Optional
from dataclasses import dataclass

from oranged.analyse import analyse_markdown, AnalysisResult


# ─── Partition-Aware Weights ──────────────────────────────────────────────────
# Different section types have different quality priorities.

PARTITION_WEIGHTS = {
    "SAFETY":          {"format": 0.15, "heading": 0.10, "content": 0.40, "structure": 0.20, "table": 0.15},
    "TECHNICAL_SPEC":  {"format": 0.15, "heading": 0.10, "content": 0.35, "structure": 0.25, "table": 0.15},
    "INSTALLATION":    {"format": 0.15, "heading": 0.25, "content": 0.30, "structure": 0.20, "table": 0.10},
    "OPERATION":       {"format": 0.15, "heading": 0.20, "content": 0.30, "structure": 0.20, "table": 0.15},
    "MAINTENANCE":     {"format": 0.10, "heading": 0.10, "content": 0.35, "structure": 0.30, "table": 0.15},
    "TROUBLESHOOTING": {"format": 0.10, "heading": 0.15, "content": 0.35, "structure": 0.25, "table": 0.15},
    "FAQ":             {"format": 0.15, "heading": 0.15, "content": 0.30, "structure": 0.20, "table": 0.20},
    "PARTS":           {"format": 0.20, "heading": 0.10, "content": 0.30, "structure": 0.25, "table": 0.15},
    "RECIPE":          {"format": 0.15, "heading": 0.15, "content": 0.30, "structure": 0.20, "table": 0.20},
}
DEFAULT_WEIGHTS = {"format": 0.20, "heading": 0.15, "content": 0.30, "structure": 0.20, "table": 0.15}

PASS_THRESHOLD = 0.70


# ─── Scoring Functions ────────────────────────────────────────────────────────

def _score_format_compliance(md: str) -> float:
    """Check Markdown syntax validity."""
    score = 1.0
    lines = md.split('\n')

    # Unclosed code blocks
    fence_count = sum(1 for l in lines if l.strip().startswith('```'))
    if fence_count % 2 != 0:
        score -= 0.2

    # Broken table rows (pipes don't match header)
    in_table = False
    expected_pipes = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            pipes = stripped.count('|')
            if not in_table:
                in_table = True
                expected_pipes = pipes
            elif pipes != expected_pipes:
                score -= 0.05
        else:
            in_table = False

    # Orphan list markers
    orphan_lists = sum(1 for l in lines if re.match(r'^\s*[-*+]\s*$', l))
    score -= orphan_lists * 0.02

    return max(0.0, min(1.0, score))


def _score_heading_hierarchy(md: str) -> float:
    """Check heading levels don't skip (e.g., # -> ### without ##)."""
    score = 1.0
    levels = []
    for line in md.split('\n'):
        m = re.match(r'^(#{1,6})\s+', line)
        if m:
            levels.append(len(m.group(1)))

    if not levels:
        return 0.5  # No headings = uncertain

    # Check for skipped levels
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            score -= 0.1  # Skipped a level

    # Check first heading is H1
    if levels and levels[0] > 1:
        score -= 0.1

    return max(0.0, min(1.0, score))


def _score_content_accuracy(md: str, page_count: int = 0) -> float:
    """Estimate content preservation. Higher text density = better."""
    score = 1.0

    # Garbage residue check
    garbage_pattern = re.compile(r'[@?]{3,}|[\x00-\x08]')
    garbage_hits = len(garbage_pattern.findall(md))
    score -= garbage_hits * 0.05

    # Very short output for multi-page docs is suspicious
    if page_count > 5 and len(md) < page_count * 100:
        score -= 0.3

    # CID character residue
    cid_hits = len(re.findall(r'\(cid:\d+\)', md))
    score -= cid_hits * 0.02

    return max(0.0, min(1.0, score))


def _score_structural_consistency(md: str, analysis: AnalysisResult) -> float:
    """Check cross-references are valid, images have context."""
    score = 1.0

    # Orphan cross-references (pointing to figures that don't exist)
    figure_numbers = set()
    for fig in analysis.figures:
        m = re.search(r'(\d+)', fig.label)
        if m:
            figure_numbers.add(m.group(1))

    for ref in analysis.cross_refs:
        if ref["target"] not in figure_numbers:
            score -= 0.05

    # Section coverage: a well-extracted doc should have >= 3 categories
    categories = set(s.category for s in analysis.sections if s.category != "GENERAL")
    if len(categories) < 2:
        score -= 0.15
    elif len(categories) < 3:
        score -= 0.05

    return max(0.0, min(1.0, score))


def _score_table_integrity(md: str) -> float:
    """Check tables have consistent columns and separator rows."""
    score = 1.0
    lines = md.split('\n')

    in_table = False
    header_cols = 0
    has_separator = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            cols = stripped.count('|') - 1
            if not in_table:
                in_table = True
                header_cols = cols
                has_separator = False
            elif re.match(r'^\|[\s:-]+\|$', stripped):
                has_separator = True
            elif cols != header_cols:
                score -= 0.05  # Column count mismatch
        else:
            if in_table and not has_separator:
                score -= 0.1  # Table without separator
            in_table = False
            has_separator = False

    return max(0.0, min(1.0, score))


# ─── Main Judge ──────────────────────────────────────────────────────────────

@dataclass
class JudgeReport:
    overall_score: float
    dimensions: Dict[str, float]
    passed: bool
    dominant_category: str
    weights_used: Dict[str, float]
    section_count: int
    figure_count: int
    crossref_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "dimensions": self.dimensions,
            "passed": self.passed,
            "dominant_category": self.dominant_category,
            "weights_used": self.weights_used,
            "section_count": self.section_count,
            "figure_count": self.figure_count,
            "crossref_count": self.crossref_count,
        }


class Judge5D:
    """
    5-Dimensional quality evaluation with partition-aware weights.

    Usage:
        judge = Judge5D()
        report = judge.evaluate(markdown_text, page_count=42)
        print(report.overall_score, report.passed)
    """

    def __init__(self, pass_threshold: float = PASS_THRESHOLD):
        self.pass_threshold = pass_threshold

    def evaluate(self, md: str, page_count: int = 0) -> JudgeReport:
        """Evaluate extraction quality and return a JudgeReport."""
        analysis = analyse_markdown(md)

        dimensions = {
            "format_compliance": _score_format_compliance(md),
            "heading_hierarchy": _score_heading_hierarchy(md),
            "content_accuracy": _score_content_accuracy(md, page_count),
            "structural_consistency": _score_structural_consistency(md, analysis),
            "table_integrity": _score_table_integrity(md),
        }

        # Determine dominant category for weight selection
        cat_counts: Dict[str, int] = {}
        for s in analysis.sections:
            cat_counts[s.category] = cat_counts.get(s.category, 0) + 1
        dominant = max(cat_counts, key=cat_counts.get) if cat_counts else "GENERAL"

        weights = PARTITION_WEIGHTS.get(dominant, DEFAULT_WEIGHTS)

        # Map dimension names to weight keys
        dim_to_weight = {
            "format_compliance": "format",
            "heading_hierarchy": "heading",
            "content_accuracy": "content",
            "structural_consistency": "structure",
            "table_integrity": "table",
        }

        overall = sum(dimensions[d] * weights[dim_to_weight[d]] for d in dimensions)
        overall = round(max(0.0, min(1.0, overall)), 3)

        return JudgeReport(
            overall_score=overall,
            dimensions={k: round(v, 3) for k, v in dimensions.items()},
            passed=overall >= self.pass_threshold,
            dominant_category=dominant,
            weights_used=weights,
            section_count=len(analysis.sections),
            figure_count=len(analysis.figures),
            crossref_count=len(analysis.cross_refs),
        )
