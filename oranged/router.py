"""
orangeD — Strategy Router (Strategy Sniffing)

Decides per-page processing strategy based on content characteristics:
  - NATIVE:           Digital-born text, high density -> direct extraction (zero GPU)
  - TABLE_RESCUE:     Complex tables needing VLM repair
  - ICON_SNIPER:      Icon-dense pages (control panels, button layouts)
  - SMART_REDUCE:     Image + adjacent text index table
  - SPATIAL_TOPOLOGY: Isolated structural diagrams with numbered callouts
  - FULL_VLM:         Image-only / scanned pages -> full VLM inference

Ported from CognoLiving 2.0 (hybrid_parser._route_page, fusion_pipeline).
"""

import re
from enum import Enum
from typing import Optional, Dict, Any

import fitz


class Strategy(Enum):
    NATIVE = "NATIVE"
    TABLE_RESCUE = "TABLE_RESCUE"
    ICON_SNIPER = "ICON_SNIPER"
    SMART_REDUCE = "SMART_REDUCE"
    SPATIAL_TOPOLOGY = "SPATIAL_TOPOLOGY"
    FULL_VLM = "FULL_VLM"


# ─── Page Feature Extractors ─────────────────────────────────────────────────

def _text_density(page: fitz.Page) -> float:
    """Characters per KB of page content stream."""
    text = page.get_text()
    raw_size = len(page.read_contents()) / 1024 + 1
    return len(text) / raw_size


def _icon_density(page: fitz.Page) -> float:
    """Ratio of total image area to page area."""
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return 0.0
    img_list = page.get_images()
    if not img_list:
        return 0.0
    img_area = 0.0
    for img in img_list:
        xref = img[0]
        try:
            rects = page.get_image_rects(xref)
            for r in rects:
                img_area += r.width * r.height
        except Exception:
            img_area += page_area * 0.05
    return min(1.0, img_area / page_area)


def _line_variance(page: fitz.Page) -> float:
    """Variance of line lengths — high variance signals dual-column layout."""
    text = page.get_text()
    lines = [len(l.strip()) for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return 0.0
    avg = sum(lines) / len(lines)
    return sum((l - avg) ** 2 for l in lines) / len(lines)


def _has_adjacent_index_table(text: str) -> bool:
    """Detect circled-number or (1)(2)(3) style index lists."""
    patterns = [
        r'[\u2460-\u2473]',   # circled numbers ①②③...
        r'\([1-9]\)\s*\w+',
        r'\d+\.\s+\w+.*\n\d+\.\s+\w+',
    ]
    return any(re.search(p, text) for p in patterns)


def _is_isolated_structural_diagram(page: fitz.Page) -> bool:
    """Page is mostly image with minimal text and numbered callouts."""
    text = page.get_text().strip()
    has_circles = bool(re.search(r'[\u2460-\u2473]', text))
    return len(text) < 80 and len(page.get_images()) >= 1 and has_circles


def _has_complex_tables(page: fitz.Page) -> bool:
    """Detect tables that native extraction may struggle with."""
    text = page.get_text()
    # Multiple pipe characters suggest table rows
    pipe_lines = sum(1 for line in text.splitlines() if line.count('|') >= 2)
    # Tab-separated columns
    tab_lines = sum(1 for line in text.splitlines() if line.count('\t') >= 2)
    # Many short lines with alignment (spec-like)
    short_aligned = sum(1 for line in text.splitlines()
                        if 5 < len(line.strip()) < 40)
    total_lines = max(1, len(text.splitlines()))
    return (pipe_lines > 3 or tab_lines > 3 or
            short_aligned / total_lines > 0.5)


# ─── Feature Snapshot ────────────────────────────────────────────────────────

def extract_page_features(page: fitz.Page) -> Dict[str, Any]:
    """Extract all routing features for a page. Useful for benchmarking."""
    text = page.get_text()
    return {
        "text_len": len(text),
        "text_density": round(_text_density(page), 2),
        "icon_density": round(_icon_density(page), 4),
        "line_variance": round(_line_variance(page), 2),
        "image_count": len(page.get_images()),
        "has_index_table": _has_adjacent_index_table(text),
        "is_structural_diagram": _is_isolated_structural_diagram(page),
        "has_complex_tables": _has_complex_tables(page),
    }


# ─── Main Router ─────────────────────────────────────────────────────────────

# Thresholds
DENSITY_THRESHOLD = 50       # chars/KB — below this, text is too sparse for native
ICON_RATIO_THRESHOLD = 0.05  # image area / page area
ISOLATED_DIAG_MAX_TEXT = 80  # chars: below this, page is diagram-dominant


def route_page(page: fitz.Page) -> Strategy:
    """
    Determine the optimal extraction strategy for a single page.

    Decision tree:
      1. No text at all + has images -> FULL_VLM (scanned page)
      2. Isolated structural diagram  -> SPATIAL_TOPOLOGY
      3. Image + adjacent index table -> SMART_REDUCE
      4. Complex tables detected      -> TABLE_RESCUE
      5. Icon-dense / low-density     -> ICON_SNIPER
      6. High line variance (dual-col)-> ICON_SNIPER
      7. Default high-density text     -> NATIVE
    """
    text = page.get_text().strip()
    img_count = len(page.get_images())

    # Scanned / image-only page
    if len(text) < 10 and img_count > 0:
        return Strategy.FULL_VLM

    density = _text_density(page)
    icon_dens = _icon_density(page)
    variance = _line_variance(page)

    # Isolated structural diagram with callout numbers
    if _is_isolated_structural_diagram(page):
        return Strategy.SPATIAL_TOPOLOGY

    # Image + adjacent text index table
    if _has_adjacent_index_table(text) and img_count >= 1:
        return Strategy.SMART_REDUCE

    # Complex tables that native fitz can't handle well
    if _has_complex_tables(page) and icon_dens < ICON_RATIO_THRESHOLD:
        return Strategy.TABLE_RESCUE

    # Icon-dense pages (panels, button layouts)
    if icon_dens >= ICON_RATIO_THRESHOLD or (img_count > 0 and density < DENSITY_THRESHOLD * 1.5):
        return Strategy.ICON_SNIPER

    # Dual-column high variance
    if variance > 400:
        return Strategy.ICON_SNIPER

    # Low density with no special pattern
    if density < DENSITY_THRESHOLD:
        return Strategy.ICON_SNIPER

    return Strategy.NATIVE


def route_pdf(pdf_path: str) -> Dict[int, Strategy]:
    """Route all pages in a PDF. Returns {page_num: Strategy}."""
    doc = fitz.open(pdf_path)
    result = {}
    for i, page in enumerate(doc):
        result[i] = route_page(page)
    doc.close()
    return result
