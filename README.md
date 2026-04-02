# OrangeD

**Hybrid Intelligent PDF-to-Markdown Pipeline**

Native-first extraction with smart OCR/VLM fallback routing, 5-dimensional quality judge, and semantic document classification.

> "Don't OCR what you can read natively. Don't VLM what OCR can handle. Route intelligently."

---

## Why OrangeD?

Most PDF extraction tools take a one-size-fits-all approach: PaddleOCR runs full OCR on every page, GLM-4V sends everything through a heavy VLM, MinerU applies uniform rule+model pipelines.

OrangeD takes a different approach: **inspect each page first, then choose the cheapest strategy that works.**

```
PDF Input → Strategy Sniffing (per-page)
  ├─ NATIVE           → PyMuPDF vector extraction (zero GPU, milliseconds)
  ├─ TABLE_RESCUE     → Crop table region → Local VLM repair
  ├─ ICON_SNIPER      → Icon-dense pages → Vision model
  ├─ SMART_REDUCE     → Image + text index → Extract text, tag image
  ├─ SPATIAL_TOPOLOGY → Structural diagrams → VLM spatial analysis
  └─ FULL_VLM         → Scanned/image-only → Full OCR/VLM pipeline
```

For digital-born PDFs, the majority of pages can be extracted natively without any GPU. Only pages that genuinely need vision-based processing are routed to OCR/VLM adapters.

---

## Design Comparison

| Feature | **OrangeD** | PaddleOCR | GLM-4V | MinerU |
|:---|:---|:---|:---|:---|
| **Strategy** | Hybrid per-page routing | Full OCR | Full VLM | Rule + model |
| **Digital PDF** | Native extraction (zero GPU) | Full OCR | Full VLM | Has native path |
| **Scanned PDF** | Pluggable OCR/VLM adapters | Native OCR | Native VLM | Native |
| **Heading recovery** | Font-size hierarchy + breadcrumb | None | Limited | Rule-based |
| **Dual-column** | Auto-detect + reorder | No | VLM-dependent | Yes |
| **Table reconstruction** | Zipper algorithm + VLM rescue | Table model | VLM direct | Rule + model |
| **Quality judge** | 5-dimensional + partition-aware | None | None | Limited |
| **Section classification** | 9-category, CN/EN/JP | None | None | None |
| **Core dependency** | pymupdf (~30MB) | ~1.5GB | ~10GB+ | ~500MB |

> **Note:** Speed comparisons are not included in this table because we have not yet run side-by-side benchmarks with PaddleOCR, GLM-4V, or MinerU under identical conditions. Cross-tool comparison is planned for v0.2.0.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 5: Quality Gate                                        │
│  5-D Judge (format / heading / content / structure / table)   │
│  Partition-aware weights per section type                     │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: Semantic Analysis                                   │
│  9-category classifier (Safety / Install / Operation / ...)   │
│  Figure registry + cross-reference binding                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Post-Processing                                     │
│  Garbage filter · Line dedup · Zipper tables · Parts tagging  │
│  Run-on heading merger · Anti-watermark                       │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Strategy Router                                     │
│  NATIVE / TABLE_RESCUE / ICON_SNIPER / SMART_REDUCE /        │
│  SPATIAL_TOPOLOGY / FULL_VLM                                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Extraction Engine                                   │
│  PyMuPDF native · StructureBuilder · FigureRegistry           │
│  Dual-column detector · TOC extractor (bookmark + font-infer) │
│  Pluggable OCR adapters: PaddleOCR / Qwen-VL / Gemini / GLM  │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Install

```bash
# Core (native extraction only, ~30MB)
pip install orangeD

# With PaddleOCR for scanned pages
pip install orangeD[paddle]

# With local Qwen-VL (needs CUDA GPU)
pip install orangeD[qwen]

# With Gemini cloud VLM
pip install orangeD[gemini]

# Everything
pip install orangeD[all]
```

### Python API

```python
from oranged import extract_pdf, analyse_markdown, Judge5D

# Extract
md = extract_pdf("manual.pdf")

# Classify sections
analysis = analyse_markdown(md)
for s in analysis.sections:
    print(f"[{s.category}] {s.title}")

# Quality check
report = Judge5D().evaluate(md, page_count=80)
print(f"Score: {report.overall_score:.3f} ({'PASS' if report.passed else 'FAIL'})")
```

### With OCR Adapter

```python
from oranged import extract_pdf
from oranged.adapters.paddle_adapter import PaddleAdapter

# Scanned PDF: native pages extracted normally, scanned pages use PaddleOCR
md = extract_pdf("scanned_manual.pdf", ocr_adapter=PaddleAdapter(lang="ch"))
```

### CLI

```bash
# Extract PDF to Markdown
oranged extract manual.pdf -o output.md

# Show routing decisions per page
oranged route manual.pdf -v

# Classify document sections
oranged analyse output.md

# 5D quality evaluation
oranged judge output.md

# Run benchmark
oranged benchmark manual.pdf -o results.json
```

---

## Strategy Router

The router inspects each page and decides the optimal extraction path:

| Strategy | Trigger | GPU | Method |
|:---|:---|:---|:---|
| `NATIVE` | High text density, digital-born | No | PyMuPDF direct extraction |
| `TABLE_RESCUE` | Complex tables detected | Yes | Crop region → VLM table repair |
| `ICON_SNIPER` | Icon-dense (panels, buttons) | Yes | Vision model icon→text |
| `SMART_REDUCE` | Image + adjacent index table | Minimal | Extract text table, tag image |
| `SPATIAL_TOPOLOGY` | Structural diagram with callouts | Yes | VLM spatial position analysis |
| `FULL_VLM` | Scanned / image-only page | Yes | Full OCR or VLM inference |

```python
from oranged.router import route_pdf

strategies = route_pdf("manual.pdf")
# {0: Strategy.NATIVE, 1: Strategy.NATIVE, 2: Strategy.TABLE_RESCUE, ...}
```

---

## 5-Dimensional Quality Judge

Every extraction is scored across 5 dimensions with **partition-aware weights** — a troubleshooting section prioritizes table integrity, while a safety section prioritizes content accuracy:

| Dimension | What it measures |
|:---|:---|
| `format_compliance` | Markdown syntax validity (code fences, table structure) |
| `heading_hierarchy` | No skipped levels, starts with H1, no orphan nodes |
| `content_accuracy` | Information preservation, garbage residue, CID artifacts |
| `structural_consistency` | Cross-refs valid, section coverage, reading order |
| `table_integrity` | Column counts match, separator rows present |

The judge evaluates **structural and syntactic quality**, not semantic accuracy against a ground truth. A high score means the output Markdown is well-formed and internally consistent. See [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) for full scoring details.

```python
from oranged.judge import Judge5D

report = Judge5D().evaluate(markdown_text, page_count=80)
# report.overall_score = 0.892
# report.dimensions = {"format_compliance": 0.95, ...}
# report.passed = True
```

---

## OCR Adapter System

OrangeD's adapter system lets you plug in any OCR/VLM backend:

| Adapter | Backend | GPU Required | Install |
|:---|:---|:---|:---|
| `PaddleAdapter` | PaddleOCR PP-OCRv4 | Optional | `pip install orangeD[paddle]` |
| `QwenAdapter` | Qwen2.5-VL / Qwen3-VL | Yes (CUDA) | `pip install orangeD[qwen]` |
| `GeminiAdapter` | Gemini 2.0 Flash | No (cloud) | `pip install orangeD[gemini]` |
| `GLMAdapter` | GLM-4V (Zhipu AI) | No (cloud) | `pip install zhipuai` |

### Custom Adapter

```python
from oranged.adapters.base import BaseAdapter

class MyOCRAdapter(BaseAdapter):
    name = "my_ocr"

    def is_available(self) -> bool:
        return True

    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        # Your OCR logic here
        return extracted_text
```

---

## Benchmark Results (v0.1.0)

Tested on 5 real-world appliance manuals. **Native extraction only** — no OCR adapter active, zero GPU usage.

| Document | Pages | Type | Time | Pages/s | Output | Sections | Quality |
|:---|:---|:---|:---|:---|:---|:---|:---|
| LG Washer | 24 | Digital-born | 7.15s | 3.4 | 45,543 chars | 177 | **0.985** |
| Bambu Lab A1 (3D Printer) | 24 | Image-only | 1.82s | 13.2 | 3,319 chars | 2 | **0.970** |
| Bosch Climate 5000 AC | 24 | Digital-born | 0.76s | 31.6 | 74,346 chars | 12 | **0.895** |
| Dyson TP07 Purifier | 10 | Digital-born | 2.23s | 4.5 | 75,386 chars | 19 | **0.990** |
| Samsung AR9500T AC | 42 | Digital-born | 5.82s | 7.2 | 50,652 chars | 54 | **0.955** |

**Environment:** AMD Ryzen 7 3700X, 32GB RAM, Windows 11, Python 3.13, PyMuPDF 1.27.1. See [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) for full details.

**Reading the results:**

- All 5 documents pass the quality gate (threshold: 0.70). Quality scores measure structural correctness (Markdown validity, heading hierarchy, table integrity), not semantic completeness.
- **Bambu Lab** scores high (0.970) despite only 3,319 chars because it's an image-only PDF — 21 of 24 pages have zero native text. The score reflects that the extracted content, though minimal, is well-formed. With an OCR adapter enabled, these pages would produce actual content.
- Speed varies from 3.4 to 31.6 pages/s depending on document complexity. Bosch is fastest because its pages are dense, uniform text blocks. LG is slowest because it has many mixed text+image pages requiring more layout analysis.
- Section classification recovered up to 7 distinct categories per document.

**Full artifacts** (extracted Markdown, route logs, judge reports) for LG, Bosch, and Bambu Lab are available in [`benchmarks/results/`](benchmarks/results/).

---

## Known Limitations

- **Native path only in v0.1.0.** Pages routed to `FULL_VLM` or `ICON_SNIPER` produce placeholder output unless an OCR adapter is configured. The benchmark results reflect native extraction floor, not full pipeline output.
- **No ground truth comparison.** Quality scores are structural (syntax, hierarchy, table format), not semantic (was every sentence captured correctly). Human evaluation has not been conducted.
- **No cross-tool benchmark yet.** We have not run side-by-side comparisons with PaddleOCR, MinerU, or GLM-OCR under identical conditions.
- **Appliance manual focus.** The 9-category taxonomy and post-processing heuristics (parts tagging, spec table Zipper) are tuned for appliance manuals. Performance on other document types (academic papers, legal contracts, etc.) is untested.
- **English/multilingual tested only.** The classifier supports Chinese, English, and Japanese keywords, but the benchmark set contains only English/multilingual documents.

---

## Roadmap

| Version | Focus |
|:---|:---|
| **v0.1.1** | Benchmark reproducibility: add `oranged benchmark --compare` for cross-tool runs |
| **v0.2.0** | End-to-end scanned PDF pipeline with PaddleOCR + Qwen-VL adapters benchmarked |
| **v0.3.0** | Layout visualization / debug mode: visual diff between source PDF and extracted Markdown |
| **v0.4.0** | Multilingual evaluation set (CN/JP/DE documents) |
| **v0.5.0** | Self-learning: brand heuristic auto-generation from extraction failures |

---

## Origin

OrangeD's extraction engine is ported from CognoLiving 2.0, a document intelligence system designed for appliance manual processing. The parent system includes additional capabilities (self-learning heuristic engine, brand-specific correction scripts, neural routing, knowledge database) that are not part of this open-source release.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
