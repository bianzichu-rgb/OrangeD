"""
orangeD — Layout-aware PDF to structured Markdown converter.

Native-first approach: extracts vector text directly from digital-born PDFs
without OCR. Falls back to pluggable OCR/VLM adapters for scanned pages.

Ported from CognoLiving 2.0 (hams_visual_assembler, hybrid_parser,
fusion_pipeline, hams_post_processor).

Requires only: pymupdf (pip install pymupdf)
"""

import re
import collections
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import fitz  # pymupdf

# ─── Constants ────────────────────────────────────────────────────────────────
H1_THRESHOLD = 14.0
H2_THRESHOLD = 11.0
HEADER_FOOTER_MARGIN = 0.06  # top/bottom 6% of page height


# ─── Garbage Text Filter ─────────────────────────────────────────────────────

def is_garbage_text(text: str) -> bool:
    """Detect CID encoding artifacts, watermark residue, and tracking noise."""
    if not text.strip():
        return True
    garbage_chars = {'?', '@'}
    count = sum(1 for c in text if c in garbage_chars)
    if len(text) > 0 and (count / len(text) > 0.2):
        return True
    if re.search(r'[@?]{3,}', text):
        return True
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
    if has_chinese:
        return False
    if re.search(r'[a-zA-Z0-9]', text):
        if ' ' not in text and len(text) > 10 and not text.startswith('http'):
            if any(c in text for c in ['@', '?']):
                return True
    return False


# ─── Anti-Watermark / Anti-Trojan Filter ─────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove draft/confidential watermarks and hidden tracking links."""
    if not isinstance(text, str):
        return text
    text = re.sub(r"(?i)\b(DRAFT|CONFIDENTIAL|INTERNAL USE ONLY)\b", "", text)
    text = re.sub(r"https?://(?:www\.)?(?:click\.ly|track-this\.com|clickserve)[^\s]+", "", text)
    return text.strip()


# ─── Structure Builder ───────────────────────────────────────────────────────

class StructureBuilder:
    """Tracks heading hierarchy via font sizes and builds breadcrumb paths."""

    def __init__(self):
        self.stack: List[Tuple[str, int]] = []
        self.last_breadcrumb: Optional[str] = None

    def ingest_block(self, block_text: str, avg_size: float) -> Optional[int]:
        """Returns heading level (1 or 2) if block looks like a heading, else None."""
        level = self._size_to_level(avg_size)
        if level > 0:
            stripped = block_text.strip()
            if re.match(r'^\d+$', stripped):
                level = 0
            elif re.search(r'[。.!?！？]\s*\S', stripped):
                level = 0
            elif re.search(r'[^.]\.["\']?\s*$', stripped) and len(stripped) > 15:
                level = 0
            elif re.match(r'^[a-z]', stripped):
                level = 0
            elif re.match(r'^[■●•▪▸►▶→]', stripped):
                level = 0
            elif re.search(r'\b(or|and|but|the|a|an|of|in|is|are|to|for|with|from|that|which|not|as|at|also|be|by|on)\s*$', stripped, re.IGNORECASE):
                level = 0
            elif level == 1 and len(stripped) > 60:
                level = 0
            elif level == 2 and len(stripped) > 80:
                level = 0
            else:
                words = stripped.split()
                is_all_caps = stripped == stripped.upper() and bool(re.search(r'[A-Z]', stripped))
                if level == 1 and len(words) > 7 and not is_all_caps:
                    level = 0
                elif level == 2 and len(words) > 9:
                    level = 0
        if level > 0:
            self._push(block_text, level)
            return level
        return None

    def get_breadcrumb(self) -> str:
        return " > ".join(t[0] for t in self.stack)

    def inject_breadcrumb(self, text: str) -> str:
        bc = self.get_breadcrumb()
        if not bc:
            return text
        if bc != self.last_breadcrumb:
            self.last_breadcrumb = bc
            return f"<!-- {bc} -->\n{text}"
        return text

    def _push(self, title: str, level: int):
        while self.stack and self.stack[-1][1] >= level:
            self.stack.pop()
        self.stack.append((title.strip(), level))

    def _size_to_level(self, size: float) -> int:
        if size >= H1_THRESHOLD:
            return 1
        if size >= H2_THRESHOLD:
            return 2
        return 0


# ─── Figure Registry ─────────────────────────────────────────────────────────

class FigureRegistry:
    """Tracks images across pages and generates cross-reference placeholders."""

    def __init__(self):
        self._items: List[Dict] = []

    def register(self, page_num: int, bbox: List[float], xref: int):
        self._items.append({"page": page_num, "bbox": bbox, "xref": xref})

    def placeholder(self, page_num: int, y_center: float, page_height: float) -> str:
        if page_height > 0:
            rel = y_center / page_height
            pos = "top" if rel < 0.33 else ("bottom" if rel > 0.67 else "middle")
        else:
            pos = "middle"
        return f"[Image on page {page_num + 1}, position: {pos}]"

    def summary(self) -> str:
        if not self._items:
            return ""
        lines = [f"\n## Figures ({len(self._items)} total)\n"]
        for i, item in enumerate(self._items):
            lines.append(f"- Figure {i + 1}: page {item['page'] + 1}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._items)


# ─── TOC Extraction ──────────────────────────────────────────────────────────

def extract_toc(doc: fitz.Document) -> List[Dict]:
    """Extract TOC from bookmarks; fall back to font-size inference."""
    toc = doc.get_toc()
    total = len(doc)
    chapters = []

    if toc:
        for i, (level, title, page) in enumerate(toc):
            start = max(0, page - 1)
            end = total - 1
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    end = max(0, toc[j][2] - 2)
                    break
            chapters.append({"title": title, "level": level,
                             "start_page": start, "end_page": end})
    else:
        chapters = _infer_chapters_from_fonts(doc)

    return chapters


def _infer_chapters_from_fonts(doc: fitz.Document) -> List[Dict]:
    """Font-size jump detection as TOC fallback."""
    chapters = []
    body_size = 10.0
    prev_start = 0
    prev_title = "Document"

    for i, page in enumerate(doc):
        blocks = page.get_text("dict").get("blocks", [])
        found = False
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    sz = span.get("size", 0)
                    text = span.get("text", "").strip()
                    if sz >= body_size * 1.4 and len(text) > 3:
                        if i > prev_start:
                            chapters.append({"title": prev_title, "level": 1,
                                             "start_page": prev_start, "end_page": i - 1})
                        prev_start = i
                        prev_title = text[:80]
                        found = True
                        break
                if found:
                    break
            if found:
                break

    chapters.append({"title": prev_title, "level": 1,
                     "start_page": prev_start, "end_page": len(doc) - 1})
    return chapters


def format_toc(chapters: List[Dict]) -> str:
    if not chapters:
        return ""
    lines = ["## Table of Contents\n"]
    for ch in chapters:
        indent = "  " * (ch["level"] - 1)
        lines.append(f"{indent}- {ch['title']} (p.{ch['start_page'] + 1})")
    return "\n".join(lines) + "\n"


# ─── Heading Enhancement ─────────────────────────────────────────────────────

def enhance_headings(page: fitz.Page, md: str) -> str:
    """Dynamically infer headings from font size distribution and inject # markers."""
    if not md.strip():
        return md

    sizes = []
    blocks = page.get_text("dict").get("blocks", [])
    for b in blocks:
        if b.get("type") == 0:
            for line in b.get("lines", []):
                for s in line.get("spans", []):
                    if s["size"] > 5:
                        sizes.append(round(s["size"], 1))
    if not sizes:
        return md

    cnt = collections.Counter(sizes)
    body_sz = cnt.most_common(1)[0][0]
    h1_sz = max(sizes)
    if h1_sz < body_sz * 1.2:
        return md

    SENTENCE_END_MID = re.compile(r'[。.!?！？…]\s*\S')
    ENDS_WITH_PERIOD = re.compile(r'[^.]\.["\']?\s*$')
    LOWERCASE_START = re.compile(r'^[a-z]')

    def _is_body_text(t: str, max_len: int) -> bool:
        if len(t) > max_len:
            return True
        if SENTENCE_END_MID.search(t):
            return True
        if ENDS_WITH_PERIOD.search(t) and len(t) > 15:
            return True
        if LOWERCASE_START.match(t):
            return True
        return False

    for b in blocks:
        if b.get("type") == 0:
            for line in b.get("lines", []):
                max_sz = max([s["size"] for s in line.get("spans", [])] + [0])
                text = "".join(s["text"] for s in line.get("spans", [])).strip()
                if len(text) > 2 and "\n" not in text:
                    if max_sz >= h1_sz * 0.95:
                        if _is_body_text(text, 60):
                            continue
                        if not re.search(rf"^#+\s+{re.escape(text)}$", md, re.MULTILINE):
                            md = re.sub(rf"^{re.escape(text)}$", f"# {text}", md, flags=re.MULTILINE)
                    elif max_sz >= body_sz * 1.2:
                        if _is_body_text(text, 80):
                            continue
                        if not re.search(rf"^#+\s+{re.escape(text)}$", md, re.MULTILINE):
                            md = re.sub(rf"^{re.escape(text)}$", f"## {text}", md, flags=re.MULTILINE)
    return md


# ─── Dual-Column Detector ────────────────────────────────────────────────────

def sort_blocks_reading_order(blocks: List[Dict], page_width: float) -> List[Dict]:
    """Detect dual-column layout and reorder to left-col then right-col."""
    if not blocks:
        return blocks

    mid = page_width / 2
    left_col = [b for b in blocks if b.get("x0", 0) < mid - 20]
    right_col = [b for b in blocks if b.get("x0", 0) >= mid - 20]

    if len(left_col) >= 2 and len(right_col) >= 2:
        left_col.sort(key=lambda b: b.get("y0", 0))
        right_col.sort(key=lambda b: b.get("y0", 0))
        return left_col + right_col

    return sorted(blocks, key=lambda b: b.get("y0", 0))


# ─── Markdown Post-Processor ─────────────────────────────────────────────────

class MarkdownPostProcessor:
    """Deduplication, spec-table reconstruction (Zipper algorithm), parts tagging."""

    def __init__(self):
        self.seen_lines: set = set()

    def process(self, text: str) -> str:
        if not text:
            return ""
        lines = text.split('\n')
        out_lines = []
        kv_buffer: List[str] = []

        for line in lines:
            line = line.strip()
            if self._is_garbage(line):
                continue
            line = self._phrase_dedup(line)
            if self._is_line_dup(line):
                continue
            line = self._tag_parts(line)

            if self._is_spec_line(line):
                kv_buffer.append(line)
            else:
                if kv_buffer:
                    out_lines.append(self._zipper_table(kv_buffer))
                    kv_buffer = []
                out_lines.append(line)

        if kv_buffer:
            out_lines.append(self._zipper_table(kv_buffer))

        return "\n".join(out_lines)

    def _is_garbage(self, text: str) -> bool:
        if not text:
            return True
        if len(text) < 2:
            return True
        garbage_chars = {'?', '@', '&', '$', '%'}
        count = sum(1 for c in text if c in garbage_chars)
        if len(text) > 5 and (count / len(text) > 0.3):
            return True
        if len(text) > 15 and ' ' not in text and not text.startswith('http'):
            if any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
                return True
        return False

    def _phrase_dedup(self, text: str) -> str:
        p = re.compile(r"\b(\w+(?:\s+\w+){0,3})\s+\1\b", re.IGNORECASE)
        for _ in range(5):
            new = p.sub(r"\1", text)
            if new == text:
                break
            text = new
        return text

    def _is_line_dup(self, line: str) -> bool:
        key = re.sub(r'\s+', '', line).lower()
        if len(key) < 5:
            return False
        if key in self.seen_lines:
            return True
        self.seen_lines.add(key)
        return False

    def _tag_parts(self, line: str) -> str:
        m = re.match(r"^([A-Z]\d{1,2})\s*[\.:]?\s+(.+)$", line)
        if m:
            idx, desc = m.group(1), m.group(2)
            if re.match(r'^(error|fault|code|err|problem|issue)', desc, re.IGNORECASE):
                return line
            if 3 < len(desc) < 100:
                return f"> **[Related Parts]** {idx}: {desc}"
        return line

    def _is_spec_line(self, line: str) -> bool:
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2 and self._has_units(parts[1].strip()):
                return True
        if (line.startswith('- ') or line.startswith('* ')) and self._has_units(line):
            return True
        if ' ' in line and self._has_units(line) and len(line) < 60 and not line.endswith('.'):
            return True
        return False

    def _has_units(self, text: str) -> bool:
        return bool(re.search(r'\d+\s*(W|V|Hz|mm|cm|kg|g|ml|L|min)', text, re.IGNORECASE))

    def _zipper_table(self, buffer: List[str]) -> str:
        if not buffer:
            return ""
        if len(buffer) < 2:
            return buffer[0]
        rows = []
        for line in buffer:
            clean = line.lstrip('-* ')
            if ':' in clean:
                k, v = clean.split(':', 1)
                rows.append((k.strip(), v.strip()))
            else:
                m = re.search(r'(\d+\s*(?:W|V|Hz|mm|cm|kg|g|ml|L|min))', clean, re.IGNORECASE)
                if m:
                    k = clean[:m.start()].strip()
                    v = clean[m.start():].strip()
                    rows.append((k, v))
                else:
                    rows.append((clean, ""))

        if not any(r[1] for r in rows):
            return "\n".join(buffer)

        lines = ["| Feature | Specification |", "| :--- | :--- |"]
        for k, v in rows:
            lines.append(f"| **{k}** | {v} |")
        return "\n".join(lines)


# ─── Run-on Heading Merger ────────────────────────────────────────────────────

def _merge_runon_headings(md: str) -> str:
    """Demote ## headings that are actually sentence continuations."""
    lines = md.split('\n')
    out = []
    SENTENCE_END = re.compile(r'[。.!?！？…、,，:：;；]\s*$')
    HEADING2 = re.compile(r'^(##)\s+(.+)$')

    for i, line in enumerate(lines):
        if i == 0:
            out.append(line)
            continue
        m = HEADING2.match(line)
        if m:
            prev = out[-1].rstrip() if out else ""
            if prev and not SENTENCE_END.search(prev) and not prev.startswith('#'):
                out.append(m.group(2))
                continue
        out.append(line)
    return '\n'.join(out)


# ─── Core Extraction ─────────────────────────────────────────────────────────

def extract_pdf(pdf_path: str, toc_only: bool = False,
                ocr_adapter=None) -> str:
    """
    Main extraction function.

    Args:
        pdf_path: Path to PDF file.
        toc_only: If True, only extract TOC.
        ocr_adapter: Optional OCR adapter for scanned/image-only pages.
                     Must implement recognize(image_bytes, prompt) -> str.

    Returns:
        Structured Markdown string.
    """
    doc = fitz.open(pdf_path)
    pdf_name = Path(pdf_path).stem

    chapters = extract_toc(doc)
    toc_md = format_toc(chapters)

    if toc_only:
        doc.close()
        return toc_md

    structure = StructureBuilder()
    figures = FigureRegistry()
    post = MarkdownPostProcessor()

    page_outputs: List[str] = []

    for page_num, page in enumerate(doc):
        page_height = page.rect.height
        page_width = page.rect.width

        raw_blocks = []
        page_dict = page.get_text("dict")

        for block in page_dict.get("blocks", []):
            if block.get("type") == 0:
                lines_text = []
                block_max_size = 0.0
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        lines_text.append(span.get("text", ""))
                        block_max_size = max(block_max_size, span.get("size", 0))

                text = "".join(lines_text).strip()
                if not text or is_garbage_text(text):
                    continue

                bbox = block.get("bbox", [0, 0, 0, page_height])
                by0, by1 = bbox[1], bbox[3]

                if by1 < page_height * HEADER_FOOTER_MARGIN or by0 > page_height * (1 - HEADER_FOOTER_MARGIN):
                    if text.isdigit() or len(text) < 5:
                        continue

                raw_blocks.append({
                    "text": text, "size": block_max_size,
                    "x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]
                })

            elif block.get("type") == 1:
                bbox = block.get("bbox", [0, 0, 0, 0])
                xref = block.get("number", 0)
                y_center = (bbox[1] + bbox[3]) / 2
                figures.register(page_num, list(bbox), xref)
                raw_blocks.append({
                    "text": figures.placeholder(page_num, y_center, page_height),
                    "size": 0, "is_image": True,
                    "x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]
                })

        # Check if page is image-only (no text blocks) and we have an OCR adapter
        text_blocks = [b for b in raw_blocks if not b.get("is_image")]
        if not text_blocks and ocr_adapter and raw_blocks:
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            ocr_text = ocr_adapter.recognize(img_bytes)
            if ocr_text:
                page_outputs.append(f"<!-- Page {page_num + 1} [OCR] -->\n{ocr_text}")
                continue

        ordered = sort_blocks_reading_order(raw_blocks, page_width)

        page_lines: List[str] = []
        for blk in ordered:
            text = blk["text"]
            size = blk.get("size", 0)

            if blk.get("is_image"):
                page_lines.append(f"\n{text}\n")
                continue

            level = structure.ingest_block(text, size)
            if level:
                page_lines.append(f"\n{'#' * level} {text}\n")
            else:
                annotated = structure.inject_breadcrumb(text)
                page_lines.append(annotated)

        raw_page_md = "\n".join(page_lines)
        raw_page_md = enhance_headings(page, raw_page_md)
        raw_page_md = _merge_runon_headings(raw_page_md)
        raw_page_md = clean_text(raw_page_md)
        clean_page_md = post.process(raw_page_md)

        if clean_page_md.strip():
            page_outputs.append(clean_page_md)

    doc.close()

    parts = [f"# {pdf_name}\n\n"]
    if toc_md:
        parts.append(toc_md + "\n\n---\n\n")
    parts.append("\n\n---\n\n".join(page_outputs))
    if figures.count:
        parts.append(figures.summary())

    return "".join(parts)
