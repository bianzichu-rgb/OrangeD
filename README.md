# orangeD

**Hybrid Intelligent PDF-to-Markdown Pipeline**

Native-first extraction with smart OCR/VLM fallback routing, 5-dimensional quality judge, and semantic document classification.

> "Don't OCR what you can read natively. Don't VLM what OCR can handle. Route intelligently."

---

## Why orangeD?

Most PDF extraction tools take a one-size-fits-all approach: PaddleOCR runs full OCR on every page, GLM-4V sends everything through a heavy VLM, MinerU applies uniform rule+model pipelines. This wastes compute on pages that don't need it and misses quality on pages that do.

**orangeD routes intelligently at the block level:**

```
PDF Input → Strategy Sniffing (per-page)
  ├─ NATIVE           → PyMuPDF vector extraction (zero GPU, milliseconds)
  ├─ TABLE_RESCUE     → Crop table region → Local VLM repair
  ├─ ICON_SNIPER      → Icon-dense pages → Vision model
  ├─ SMART_REDUCE     → Image + text index → Extract text, tag image
  ├─ SPATIAL_TOPOLOGY → Structural diagrams → VLM spatial analysis
  └─ FULL_VLM         → Scanned/image-only → Full OCR/VLM pipeline
```

For a typical 80-page appliance manual, **~70% of pages go through the native path** (zero GPU), and only the remaining complex pages trigger OCR/VLM — resulting in 10-50x speedup over full-OCR approaches.

---

## Comparison

| Feature | **orangeD** | PaddleOCR | GLM-4V | MinerU |
|:---|:---|:---|:---|:---|
| **Strategy** | Hybrid intelligent routing | Full OCR | Full VLM | Rule + model |
| **Digital PDF** | Native extraction (zero GPU) | Full OCR (wasteful) | Full VLM (overkill) | Has native path |
| **Scanned PDF** | Pluggable OCR/VLM adapters | Native OCR | Native VLM | Native |
| **GPU for digital PDFs** | **0%** | 100% | 100% | Partial |
| **Speed (digital)** | **50-200 pages/s** | 2-5 pages/s | 0.5-2 pages/s | 5-15 pages/s |
| **Heading recovery** | Font-size hierarchy + breadcrumb | None | Limited | Rule-based |
| **Dual-column** | Auto-detect + reorder | No | VLM-dependent | Yes |
| **Table reconstruction** | Zipper algorithm + VLM rescue | Table model | VLM direct | Rule + model |
| **Quality judge** | **5-dimensional + partition-aware** | None | None | Limited |
| **Section classification** | **9-category, CN/EN/JP** | None | None | None |
| **Self-learning** | Brand heuristics + distillation | None | None | None |
| **Core dependency** | pymupdf (~30MB) | ~1.5GB | ~10GB+ | ~500MB |

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

# Benchmark against PaddleOCR
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

```python
from oranged.judge import Judge5D

report = Judge5D().evaluate(markdown_text, page_count=80)
# report.overall_score = 0.892
# report.dimensions = {"format_compliance": 0.95, "heading_hierarchy": 0.90, ...}
# report.passed = True
# report.dominant_category = "OPERATION"
```

---

## OCR Adapter System

orangeD's adapter system lets you plug in any OCR/VLM backend:

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

## Origin

orangeD is extracted from [CognoLiving 2.0](https://github.com/cogno-living), a 5-layer self-learning document intelligence system built for appliance manual processing at scale (100K+ documents). The core extraction pipeline has been battle-tested across 68+ brands (Bosch, Miele, Dyson, Siemens, LG, Samsung, ...) and 8,114 taxonomy mappings.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
