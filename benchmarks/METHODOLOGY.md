# Benchmark Methodology

This document explains how OrangeD benchmarks are conducted, what the numbers mean,
and what they don't mean.

---

## Test Environment

| Component | Specification |
|:---|:---|
| CPU | AMD Ryzen 7 3700X 8-Core (3.6 GHz base, 4.4 GHz boost) |
| RAM | 32 GB DDR4 |
| GPU | NVIDIA GeForce RTX 3060 12GB (not used in native benchmarks) |
| OS | Windows 11 Pro 10.0.22000 |
| Python | 3.13.3 (MSC v.1943 64 bit) |
| PyMuPDF | 1.27.1 |
| Disk | NVMe SSD |

**GPU note:** The benchmark results in v0.1.0 measure **native extraction only** —
no OCR or VLM adapter is active. GPU is available but unused. Pages routed to
`ICON_SNIPER`, `FULL_VLM`, or `TABLE_RESCUE` are still processed via the native
PyMuPDF path (extracting whatever vector text exists), but their output may be
incomplete for image-heavy or scanned content.

---

## Test Documents

| Document | Pages | Type | Language | Layout | Key Content |
|:---|:---|:---|:---|:---|:---|
| LG 3828ER3052K (Washer) | 24 | Digital-born | English | Mixed: text + diagrams | Safety, installation, operations, troubleshooting, specs |
| Bambu Lab A1 (3D Printer) | 24 | **Image-only** | English | Almost entirely images | Visual assembly guide, minimal native text |
| Bosch Climate 5000 (AC) | 24 | Digital-born | English/multilingual | Dense text, some tables | Multi-language manual, troubleshooting tables |
| Dyson TP07 (Air Purifier) | 10 | Digital-born | Multilingual | Icon-heavy, structured | Visual icons with multilingual text blocks |
| Samsung AR9500T (AC) | 42 | Digital-born | English/Korean | Dual-column, tables | Installation diagrams, specs, error codes |

### Why these 5?

They represent common real-world manual types:
- **LG**: Standard text-heavy manual — the "easy case" for native extraction.
- **Bambu Lab**: The adversarial case — almost no extractable native text (21 of 24 pages have 0 characters). This document intentionally shows where native-only extraction hits its limit.
- **Bosch**: Multi-language document with repeated content in different languages. Tests deduplication and heading recovery across language blocks.
- **Dyson**: Short, icon-heavy document with multilingual content embedded as text blocks. Tests the router's icon density detection.
- **Samsung**: Longest document (42 pages) with dual-column layout. Tests column detection and reading order.

---

## What Is Measured

### Timing (`time_s`, `pages_per_second`)

- **Scope:** Measures `extract_pdf()` call only — from PDF open to final Markdown string.
- **Includes:** TOC extraction, per-page block parsing, structure building, heading enhancement, post-processing (dedup, zipper tables, garbage filtering), figure registry.
- **Excludes:** File I/O for writing output, section analysis (`analyse_markdown`), quality evaluation (`Judge5D`), routing analysis. These are run separately and not included in the timing.
- **Method:** `time.perf_counter()` wall-clock measurement.
- **Warm-up:** No warm-up runs. First-run times include PyMuPDF internal initialization.

### Output Metrics

- **`output_chars`**: Total characters in the output Markdown string.
- **`output_lines`**: Newline count + 1.
- **`sections`**: Number of heading-based sections detected by `analyse_markdown()`.
- **`figures`**: Number of `[Image on page N]` placeholders registered.
- **`categories`**: Distinct section categories identified (from the 9-quadrant taxonomy).

---

## Quality Score: Judge5D

### The 5 Dimensions

| Dimension | What It Measures | How It's Scored |
|:---|:---|:---|
| `format_compliance` | Markdown syntax validity | Deducts for: unclosed code fences (-0.2), mismatched table columns (-0.05 each), orphan list markers (-0.02 each). Starts at 1.0. |
| `heading_hierarchy` | Heading level consistency | Deducts for: skipped levels, e.g. H1→H3 without H2 (-0.1 each), document not starting with H1 (-0.1). Returns 0.5 if no headings found. |
| `content_accuracy` | Information preservation | Deducts for: garbage character residue (`@@@`, `???`) at -0.05 each, CID encoding artifacts at -0.02 each, suspiciously short output for multi-page docs (-0.3). |
| `structural_consistency` | Cross-reference validity + coverage | Deducts for: orphan cross-references pointing to non-existent figures (-0.05 each), fewer than 2 distinct section categories (-0.15), fewer than 3 categories (-0.05). |
| `table_integrity` | Table structure correctness | Deducts for: tables without separator rows (-0.1 each), column count mismatches within a table (-0.05 each). |

### Partition-Aware Weights

The overall score is a weighted sum of the 5 dimensions. Weights vary based on the
**dominant section category** in the document:

- A document dominated by **TROUBLESHOOTING** sections weights `table_integrity` higher (error code tables are critical).
- A document dominated by **SAFETY** sections weights `content_accuracy` higher (safety information must not be lost).
- A document dominated by **OPERATION** sections weights `structural_consistency` higher (button references must not break).

See `oranged/judge.py` `PARTITION_WEIGHTS` for the exact weight matrix.

### Pass Threshold

A document **passes** if its weighted overall score is >= **0.70**.

This threshold is deliberately conservative. It means: "the extraction produced
structurally valid, mostly complete Markdown with no major corruption." It does NOT
mean "every piece of information was perfectly extracted."

### What the Score Does NOT Measure

- **Semantic accuracy against ground truth.** There is no human-annotated reference Markdown for these documents. The judge evaluates structural and syntactic quality, not whether every sentence was captured.
- **OCR/VLM output quality.** In v0.1.0, no OCR adapter is active, so pages that need VLM repair are scored on whatever native text exists (which may be nothing).
- **Completeness.** A high score means the extracted content is well-formed, not that all content was extracted. The Bambu Lab result (0.970 with only 3,319 chars from 24 pages) demonstrates this: the format is clean, but most content is locked in images.

---

## Explaining the Results

### Why Bambu Lab has only 3,319 chars and 2 sections

The Bambu Lab A1 manual is an **image-only PDF** — 21 of 24 pages contain zero native text characters. The embedded text consists only of brief labels ("Bambu Lab", page numbers). The actual assembly instructions are rendered as images.

This is intentionally included to show:
1. The router correctly identifies these pages as `FULL_VLM` (4 pages) and `ICON_SNIPER` (19 pages).
2. Native extraction honestly reports minimal output rather than hallucinating content.
3. With an OCR adapter enabled (e.g., PaddleOCR or Qwen-VL), these pages would produce actual text.

**This is not a failure — it's the system working as designed.** The native path extracts what's natively extractable. The adapter system handles the rest.

### Why Dyson (10 pages) produces more text than LG (24 pages)

The Dyson TP07 manual packs dense multilingual text blocks into each page. Despite having fewer pages, each page contains substantial structured text content. The LG manual has more pages but includes many diagram-heavy pages with less extractable text per page.

### Why average speed is 12 pages/s, not 50-200 pages/s

The **50-200 pages/s** figure (removed from README in this version) referred to peak throughput on simple, text-only digital-native pages measured in isolation. Real document averages include:

- Pages with complex block structures requiring layout analysis
- Post-processing overhead (deduplication, heading enhancement, garbage filtering)
- Mixed content pages where native extraction still processes image blocks

The honest, reproducible number for end-to-end extraction on real manuals is **3-32 pages/s** depending on document complexity, as shown in the benchmark.

### How routing decisions are verified

The route log (`*_route_log.json`) records per-page features and the chosen strategy.
You can inspect these to verify that:

- Pages with `text_len == 0` and images → routed to `FULL_VLM`
- Pages with high `text_density` → routed to `NATIVE`
- Pages with `has_complex_tables == true` → routed to `TABLE_RESCUE`
- Pages with high `icon_density` → routed to `ICON_SNIPER`

The routing is deterministic and based on measurable page features, not heuristic guessing.

---

## Reproducibility

### Running the benchmark yourself

```bash
cd OrangeD
pip install pymupdf psutil

# Single document
python -m oranged.cli benchmark your_manual.pdf -o results.json

# Or use the Python API
from oranged.benchmark import run_benchmark
run_benchmark("your_manual.pdf", output_path="results.json")
```

### Artifacts included in this repository

For each of the 3 detailed samples (LG, Bosch, Bambu Lab):

| File | Description |
|:---|:---|
| `*_output.md` | Full extracted Markdown output |
| `*_judge_report.json` | 5D quality scores with dimension breakdown |
| `*_route_log.json` | Per-page routing decisions with feature values |
| `*_analysis.json` | Section classification with category and confidence |

These artifacts allow you to:
1. Read the actual output and judge quality yourself.
2. Verify routing decisions against page characteristics.
3. Cross-check the judge scores against the Markdown content.
4. Compare with your own extraction pipeline on the same documents.

---

## Known Limitations of This Benchmark

1. **No ground truth comparison.** Quality scores are structural, not semantic. A human review of extraction accuracy has not been conducted for this benchmark set.

2. **Native path only.** OCR/VLM adapters are not active. Pages that require vision-based extraction produce minimal or no output. This benchmark measures the native extraction floor, not the full pipeline ceiling.

3. **Small sample size.** 5 documents across 4 brands. Results should not be generalized to all PDF types (e.g., scanned books, academic papers, handwritten documents).

4. **English/multilingual only.** No Chinese-only or Japanese-only documents in this benchmark set, despite the classifier supporting these languages.

5. **Single-run timing.** No statistical averaging across multiple runs. Times may vary by ±10% depending on system load and disk cache state.

6. **No competitor comparison yet.** PaddleOCR, MinerU, and GLM-OCR results are not included in v0.1.0 because the adapter-based benchmark pipeline requires separate dependency installation. Cross-tool comparison is planned for v0.2.0.
