[English](#oranged) | [中文](#oranged--中文)

---

# OrangeD

**Native-first PDF → Structured Markdown** — with smart OCR/VLM fallback routing, 5D quality judge, and semantic section classification.

> "Don't OCR what you can read natively. Don't VLM what OCR can handle. Route intelligently."

## Current Status

| Component | Status | Notes |
|:---|:---|:---|
| Native extraction (digital-born PDF) | **Stable** | Tested on 5 real manuals, 124 total pages |
| Strategy router (per-page decision) | **Stable** | 6 strategies, deterministic rules |
| Judge5D (structural quality scoring) | **Stable** | Structural/syntactic only — not semantic accuracy |
| Section classifier (9-category) | **Stable** | CN/EN/JP keywords, appliance manuals |
| OCR/VLM adapters (PaddleOCR, Qwen, Gemini, GLM) | **Experimental** | Interfaces defined, not end-to-end benchmarked |

**Verified scope:** Appliance manuals (digital-born). Other document types (academic papers, legal, etc.) are untested.

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

The table below shows **design choices**, not benchmarked outcomes. We have not run side-by-side comparisons with these tools under identical conditions. Each tool has different design goals and strengths.

| Feature | **OrangeD** | PaddleOCR | GLM-4V | MinerU |
|:---|:---|:---|:---|:---|
| **Strategy** | Hybrid per-page routing | Full OCR | Full VLM | Rule + model |
| **Digital PDF** | Native extraction (zero GPU) | Full OCR | Full VLM | Has native path |
| **Scanned PDF** | Pluggable adapters (experimental) | Native OCR | Native VLM | Native |
| **Heading recovery** | Font-size hierarchy + breadcrumb | None | Limited | Rule-based |
| **Quality judge** | 5D structural scoring | None | None | Limited |
| **Section classification** | 9-category, CN/EN/JP | None | None | None |
| **Core dependency** | pymupdf (~30MB) | ~1.5GB | ~10GB+ | ~500MB |

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

# Everything
pip install orangeD[all]
```

### Minimal Reproducible Demo

```bash
# 1. Install
pip install pymupdf

# 2. Clone and run on any digital-born PDF you have
git clone https://github.com/bianzichu-rgb/orangeD.git
cd orangeD

# 3. Extract
python -m oranged extract your_manual.pdf -o output.md

# 4. Inspect routing decisions
python -m oranged route your_manual.pdf -v

# 5. Classify sections
python -m oranged analyse output.md

# 6. Quality check
python -m oranged judge output.md
```

Expected: steps 3-6 produce Markdown output, a per-page route log, section categories, and a 5D quality score respectively. Any digital-born PDF with selectable text will work.

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

### With OCR Adapter (Experimental)

```python
from oranged import extract_pdf
from oranged.adapters.paddle_adapter import PaddleAdapter

# Scanned PDF: native pages extracted normally, scanned pages use PaddleOCR
md = extract_pdf("scanned_manual.pdf", ocr_adapter=PaddleAdapter(lang="ch"))
```

### CLI

```bash
oranged extract manual.pdf -o output.md     # Extract PDF to Markdown
oranged route manual.pdf -v                  # Show routing decisions per page
oranged analyse output.md                    # Classify document sections
oranged judge output.md                      # 5D quality evaluation
oranged benchmark manual.pdf -o results.json # Run benchmark
```

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

> **Important:** Judge5D measures **structural and syntactic quality** (valid Markdown, heading hierarchy, table formatting), **not** semantic accuracy against a ground truth. A score of 0.95 means "well-formed output," not "95% of content was captured correctly." See [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md) for full scoring details.

Every extraction is scored across 5 dimensions with **partition-aware weights** — a troubleshooting section prioritizes table integrity, while a safety section prioritizes content accuracy:

| Dimension | What it measures |
|:---|:---|
| `format_compliance` | Markdown syntax validity (code fences, table structure) |
| `heading_hierarchy` | No skipped levels, starts with H1, no orphan nodes |
| `content_accuracy` | Information preservation, garbage residue, CID artifacts |
| `structural_consistency` | Cross-refs valid, section coverage, reading order |
| `table_integrity` | Column counts match, separator rows present |

### How to interpret scores

| Score Range | Meaning |
|:---|:---|
| **0.90+** | Structurally solid — clean headings, valid tables, consistent cross-refs |
| **0.70 – 0.90** | Usable but imperfect — some table structure issues or heading gaps |
| **< 0.70** | Needs attention — significant structural problems detected |

```python
from oranged.judge import Judge5D

report = Judge5D().evaluate(markdown_text, page_count=80)
# report.overall_score = 0.892
# report.dimensions = {"format_compliance": 0.95, ...}
# report.passed = True
```

---

## OCR Adapter System

OrangeD's adapter system lets you plug in any OCR/VLM backend. **Adapter interfaces are defined; end-to-end benchmark with adapters is planned.**

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

| Document | Pages | Type | Time | Pages/s | Output | Sections | Quality* |
|:---|:---|:---|:---|:---|:---|:---|:---|
| LG Washer | 24 | Digital-born | 7.15s | 3.4 | 45,543 chars | 177 | **0.985** |
| Bambu Lab A1 (3D Printer) | 24 | Image-only | 1.82s | 13.2 | 3,319 chars | 2 | **0.970** |
| Bosch Climate 5000 AC | 24 | Digital-born | 0.76s | 31.6 | 74,346 chars | 12 | **0.895** |
| Dyson TP07 Purifier | 10 | Digital-born | 2.23s | 4.5 | 75,386 chars | 19 | **0.990** |
| Samsung AR9500T AC | 42 | Digital-born | 5.82s | 7.2 | 50,652 chars | 54 | **0.955** |

\* Quality scores are **structural** (Markdown validity, heading hierarchy, table integrity), not semantic completeness. See [benchmarks/METHODOLOGY.md](benchmarks/METHODOLOGY.md).

**Environment:** AMD Ryzen 7 3700X, 32GB RAM, Windows 11, Python 3.13, PyMuPDF 1.27.1.

**Reading the results:**
- **Bambu Lab** scores high (0.970) despite only 3,319 chars because it's an image-only PDF — 21 of 24 pages have zero native text. The score reflects that the minimal output is well-formed. With an OCR adapter, these pages would produce actual content.
- Speed varies from 3.4 to 31.6 pages/s depending on document complexity.

**Visual examples:** [examples/VISUAL_EXAMPLES.md](examples/VISUAL_EXAMPLES.md) — original PDF pages, routing decisions, and extracted Markdown side-by-side.

<details>
<summary><b>Full benchmark artifacts</b></summary>

| Document | Extracted Markdown | Route Log | Judge Report | Section Analysis |
|:---|:---|:---|:---|:---|
| LG Washer | [output.md](benchmarks/results/lg_washer_output.md) | [route_log.json](benchmarks/results/lg_washer_route_log.json) | [judge_report.json](benchmarks/results/lg_washer_judge_report.json) | [analysis.json](benchmarks/results/lg_washer_analysis.json) |
| Bosch AC | [output.md](benchmarks/results/bosch_ac_output.md) | [route_log.json](benchmarks/results/bosch_ac_route_log.json) | [judge_report.json](benchmarks/results/bosch_ac_judge_report.json) | [analysis.json](benchmarks/results/bosch_ac_analysis.json) |
| Bambu Lab | [output.md](benchmarks/results/bambu_3d_output.md) | [route_log.json](benchmarks/results/bambu_3d_route_log.json) | [judge_report.json](benchmarks/results/bambu_3d_judge_report.json) | [analysis.json](benchmarks/results/bambu_3d_analysis.json) |

</details>

---

## Token & Cost Analysis

A key advantage of native-first extraction: **you don't pay per-page API costs for pages that don't need OCR/VLM.**

| Approach | Input Tokens | Output Tokens | Per-Page Cost |
|:---|:---|:---|:---|
| **Full VLM** (send every page as image) | ~1,100 tokens/page | ~300 tokens/page | Varies by API |
| **Full OCR** (PaddleOCR local) | 0 (local GPU) | 0 | GPU time only |
| **OrangeD native** | 0 | 0 | CPU time only |
| **OrangeD hybrid** (native + VLM for ~20% pages) | ~220 tokens/page avg | ~60 tokens/page avg | ~80% reduction |

<details>
<summary><b>Cost at scale (10,000 pages)</b></summary>

| Approach | Gemini 2.0 Flash | GPT-4o | Claude Sonnet |
|:---|:---|:---|:---|
| **Full VLM** (all pages) | $2.30 | $57.50 | $78.00 |
| **OrangeD hybrid** (20% pages to VLM) | $0.46 | $11.50 | $15.60 |
| **OrangeD native only** | $0.00 | $0.00 | $0.00 |

**Assumptions:** ~1,100 input tokens per page image, ~300 output tokens per page. "20% pages need VLM" is based on routing data where ~80% of digital-born manual pages are extractable natively.

</details>

---

## Known Limitations

- **Native path only in v0.1.0.** Pages routed to `FULL_VLM` or `ICON_SNIPER` produce placeholder output unless an OCR adapter is configured.
- **No ground truth comparison.** Quality scores are structural, not semantic. Human evaluation has not been conducted.
- **No cross-tool benchmark yet.** Side-by-side comparisons with PaddleOCR, MinerU, or GLM-OCR under identical conditions are planned.
- **Appliance manual focus.** The 9-category taxonomy and heuristics are tuned for appliance manuals. Other document types (academic papers, legal contracts, etc.) are untested.
- **Benchmark set is English-only.** The classifier supports CN/EN/JP keywords, but benchmark documents are English/multilingual only.

---

## Roadmap

**Near-term**
- [ ] Benchmark reproducibility: `oranged benchmark --compare` for cross-tool runs
- [ ] End-to-end scanned PDF pipeline with PaddleOCR + Qwen-VL adapters benchmarked
- [ ] CI with smoke tests on every PR

**Medium-term**
- [ ] Layout visualization / debug mode: visual diff between source PDF and extracted Markdown
- [ ] Multilingual evaluation set (CN/JP/DE documents)
- [ ] Broader document types: academic papers, formulas/math, teaching materials

**Ideas / Contributions Welcome**
- [ ] Self-learning brand heuristic auto-generation from extraction failures
- [ ] Web UI for interactive extraction + quality review
- [ ] ONNX-based lightweight table detector to replace VLM for simple tables

---

## Origin

OrangeD's extraction engine is ported from CognoLiving 2.0, a document intelligence system for appliance manual processing. The parent system includes additional capabilities (self-learning heuristic engine, brand-specific correction scripts, neural routing, knowledge database) not included in this open-source release.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

<a id="oranged--中文"></a>

[English](#oranged) | [中文](#oranged--中文)

---

# OrangeD — 混合智能 PDF 转 Markdown 管线

**原生优先提取 + 智能 OCR/VLM 兜底路由 + 五维质量评分 + 语义文档分类**

## 当前状态

| 组件 | 状态 | 说明 |
|:---|:---|:---|
| 原生提取（数字原生 PDF） | **稳定** | 已在 5 份真实说明书（共 124 页）上验证 |
| 策略路由（逐页决策） | **稳定** | 6 种策略，确定性规则 |
| Judge5D（结构质量评分） | **稳定** | 仅评估结构/语法质量，非语义准确率 |
| 章节分类器（9 类） | **稳定** | 中/英/日关键词，家电说明书场景 |
| OCR/VLM 适配器（PaddleOCR、Qwen、Gemini、GLM） | **实验性** | 接口已定义，尚未端到端基准测试 |

**已验证范围：** 家电说明书（数字原生）。其他文档类型（论文、法律文件等）未测试。

## 核心理念

> 能原生提取的不跑 OCR，能 OCR 搞定的不上 VLM，按页智能路由。

大多数 PDF 提取工具采用"一刀切"策略：PaddleOCR 对每一页都跑全量 OCR，GLM-4V 把所有页面都送进大模型。OrangeD 的做法是：**先检查每页内容特征，再选择最省算力的策略。**

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

> **重要：** Judge5D 衡量的是**结构和语法质量**（Markdown 有效性、标题层级、表格格式），**不是**语义准确率。0.95 分意味着"输出格式良好"，而非"95% 的内容被正确提取"。

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

## 已知局限

- v0.1.0 仅验证了原生提取路径，OCR 适配器尚未端到端跑通基准测试
- 质量评分衡量结构完整性，不是语义准确率
- 主要针对家电说明书场景优化，其他文档类型未测试
- 基准测试目前仅包含英文/多语言文档

## 起源

OrangeD 的提取引擎移植自 CognoLiving 2.0——一个面向家电说明书大规模处理的文档智能系统。母系统包含自学习启发式引擎、品牌修正脚本、神经路由等更多能力，未包含在本次开源中。

## 许可证

Apache 2.0 — 见 [LICENSE](LICENSE)。
