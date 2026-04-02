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

The judge evaluates **structural and syntactic quality**, not semantic accuracy against a ground truth. See [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) for full scoring details.

### How to interpret scores

| Score Range | Meaning | Recommended Action |
|:---|:---|:---|
| **0.90+** | Structurally solid — clean headings, valid tables, consistent cross-refs | Safe for downstream consumption (RAG, search indexing, LLM context) |
| **0.70 – 0.90** | Usable but imperfect — some table structure issues or heading gaps | Spot-check tables and heading hierarchy before production use |
| **< 0.70** | Needs attention — significant structural problems detected | Enable stronger OCR adapter or inspect specific failing dimensions |

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

**Visual examples** showing original PDF pages, routing decisions, and extracted Markdown side-by-side: [examples/VISUAL_EXAMPLES.md](examples/VISUAL_EXAMPLES.md)

**Full artifacts** for LG, Bosch, and Bambu Lab:

| Document | Extracted Markdown | Route Log | Judge Report | Section Analysis |
|:---|:---|:---|:---|:---|
| LG Washer | [output.md](benchmarks/results/lg_washer_output.md) | [route_log.json](benchmarks/results/lg_washer_route_log.json) | [judge_report.json](benchmarks/results/lg_washer_judge_report.json) | [analysis.json](benchmarks/results/lg_washer_analysis.json) |
| Bosch AC | [output.md](benchmarks/results/bosch_ac_output.md) | [route_log.json](benchmarks/results/bosch_ac_route_log.json) | [judge_report.json](benchmarks/results/bosch_ac_judge_report.json) | [analysis.json](benchmarks/results/bosch_ac_analysis.json) |
| Bambu Lab | [output.md](benchmarks/results/bambu_3d_output.md) | [route_log.json](benchmarks/results/bambu_3d_route_log.json) | [judge_report.json](benchmarks/results/bambu_3d_judge_report.json) | [analysis.json](benchmarks/results/bambu_3d_analysis.json) |

---

## Token & Cost Analysis

A key advantage of native-first extraction: **you don't pay per-page API costs for pages that don't need OCR/VLM.**

### How tokens are consumed

| Approach | Input Tokens | Output Tokens | Per-Page Cost |
|:---|:---|:---|:---|
| **Full VLM** (send every page as image) | ~1,100 tokens/page (image) | ~300 tokens/page | Varies by API |
| **Full OCR** (PaddleOCR local) | 0 (local GPU) | 0 | GPU time only |
| **OrangeD native** | 0 | 0 | CPU time only |
| **OrangeD hybrid** (native + VLM for ~20% pages) | ~220 tokens/page avg | ~60 tokens/page avg | 80% reduction |

### Cost comparison at scale

Estimated costs for processing 10,000 pages of appliance manuals:

| Approach | Gemini 2.0 Flash | GPT-4o | Claude Sonnet |
|:---|:---|:---|:---|
| **Full VLM** (all pages) | $2.30 | $57.50 | $78.00 |
| **OrangeD hybrid** (20% pages to VLM) | $0.46 | $11.50 | $15.60 |
| **OrangeD native only** | $0.00 | $0.00 | $0.00 |

**Assumptions:** ~1,100 input tokens per page image, ~300 output tokens per page. Gemini 2.0 Flash: $0.10/$0.40 per 1M input/output tokens. GPT-4o: $2.50/$10.00. Claude Sonnet: $3.00/$15.00. "20% pages need VLM" is based on our benchmark routing data where ~80% of digital-born manual pages are extractable natively.

### Downstream token consumption

OrangeD's output is structured Markdown, which is significantly more token-efficient than raw OCR text when fed into downstream LLMs (for RAG, Q&A, summarization):

- Native Markdown with headings, tables, and cross-references compresses better in LLM context windows
- Section classification lets you feed only the relevant section (e.g., just "TROUBLESHOOTING") instead of the entire document
- A 42-page Samsung manual produces ~50,000 chars (~20,000 tokens) of structured Markdown — compared to ~46,000 tokens of raw image input if sent page-by-page to a VLM

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

---

<details>
<summary><b>中文说明 (Chinese)</b></summary>

# OrangeD — 混合智能 PDF 转 Markdown 管线

**原生优先提取 + 智能 OCR/VLM 兜底路由 + 五维质量评分 + 语义文档分类**

## 核心理念

> 能原生提取的不跑 OCR，能 OCR 搞定的不上 VLM，按页智能路由。

大多数 PDF 提取工具采用"一刀切"策略：PaddleOCR 对每一页都跑全量 OCR，GLM-4V 把所有页面都送进大模型。
OrangeD 的做法是：**先检查每页内容特征，再选择最省算力的策略。**

对于数字原生 PDF（非扫描件），大部分页面可以直接通过 PyMuPDF 原生提取，零 GPU、毫秒级完成。只有真正需要视觉理解的页面才会调用 OCR/VLM。

## 六种路由策略

| 策略 | 触发条件 | GPU | 方法 |
|:---|:---|:---|:---|
| `NATIVE` | 文字密度高，数字原生 | 无 | PyMuPDF 直接提取 |
| `TABLE_RESCUE` | 检测到复杂表格 | 是 | 裁剪表格区域 → VLM 修复 |
| `ICON_SNIPER` | 图标密集（控制面板、按钮） | 是 | 视觉模型图标→文字 |
| `SMART_REDUCE` | 图片 + 相邻文字索引表 | 少量 | 提取文字表，标记图片 |
| `SPATIAL_TOPOLOGY` | 结构图 + 编号标注 | 是 | VLM 空间位置分析 |
| `FULL_VLM` | 扫描件 / 纯图片页面 | 是 | 全量 OCR 或 VLM 推理 |

## 五维质量评分（Judge5D）

| 维度 | 评测内容 |
|:---|:---|
| `format_compliance` | Markdown 语法有效性 |
| `heading_hierarchy` | 标题层级完整，无跳级 |
| `content_accuracy` | 信息保留度，垃圾字符残留 |
| `structural_consistency` | 交叉引用有效性，章节覆盖率 |
| `table_integrity` | 表格列数一致，分隔行完整 |

评分采用**分区感知权重**：故障排查章节侧重表格完整度，安全警告章节侧重内容准确率。

## Token 消耗对比

| 方案 | 10,000 页成本 (Gemini Flash) | 10,000 页成本 (GPT-4o) |
|:---|:---|:---|
| 全量 VLM（所有页发图片） | $2.30 | $57.50 |
| OrangeD 混合（20% 页面走 VLM） | $0.46 | $11.50 |
| OrangeD 纯原生 | $0.00 | $0.00 |

## 适配器系统

支持插拔式 OCR/VLM 后端：PaddleOCR、Qwen-VL（本地 GPU）、Gemini（云端）、GLM-4V（智谱 AI）。

## 已知局限

- v0.1.0 仅验证了原生提取路径，OCR 适配器尚未端到端跑通基准测试
- 质量评分衡量结构完整性，不是语义准确率
- 主要针对家电说明书场景优化，其他文档类型未测试
- 基准测试目前仅包含英文/多语言文档

## 起源

OrangeD 的提取引擎移植自 CognoLiving 2.0——一个面向家电说明书大规模处理的文档智能系统。母系统包含自学习启发式引擎、品牌修正脚本、神经路由等更多能力，未包含在本次开源中。

</details>
