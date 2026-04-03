"""
Smoke tests for orangeD core modules.

These tests verify basic functionality without requiring external PDFs,
GPU, or OCR/VLM dependencies. They run on stdlib + pymupdf only.
"""

import re
import pytest


# ─── extract.py ──────────────────────────────────────────────────────────────

class TestGarbageFilter:
    def test_empty_string(self):
        from oranged.extract import is_garbage_text
        assert is_garbage_text("") is True
        assert is_garbage_text("   ") is True

    def test_normal_text(self):
        from oranged.extract import is_garbage_text
        assert is_garbage_text("Safety instructions for your appliance") is False

    def test_garbage_chars(self):
        from oranged.extract import is_garbage_text
        assert is_garbage_text("@@@???@@@") is True

    def test_chinese_text_preserved(self):
        from oranged.extract import is_garbage_text
        assert is_garbage_text("安全注意事项") is False


class TestCleanText:
    def test_removes_watermark(self):
        from oranged.extract import clean_text
        assert "DRAFT" not in clean_text("DRAFT Some content here")
        assert "CONFIDENTIAL" not in clean_text("CONFIDENTIAL report")

    def test_preserves_normal_text(self):
        from oranged.extract import clean_text
        assert clean_text("Normal text here") == "Normal text here"

    def test_non_string_passthrough(self):
        from oranged.extract import clean_text
        assert clean_text(123) == 123


class TestStructureBuilder:
    def test_heading_detection(self):
        from oranged.extract import StructureBuilder
        sb = StructureBuilder()
        level = sb.ingest_block("SAFETY WARNINGS", 16.0)
        assert level == 1

    def test_body_text_not_heading(self):
        from oranged.extract import StructureBuilder
        sb = StructureBuilder()
        level = sb.ingest_block("this is a normal sentence that should not be a heading", 10.0)
        assert level is None

    def test_breadcrumb(self):
        from oranged.extract import StructureBuilder
        sb = StructureBuilder()
        sb.ingest_block("CHAPTER ONE", 16.0)
        bc = sb.get_breadcrumb()
        assert "CHAPTER ONE" in bc

    def test_number_only_not_heading(self):
        from oranged.extract import StructureBuilder
        sb = StructureBuilder()
        level = sb.ingest_block("42", 16.0)
        assert level is None or level == 0


class TestFigureRegistry:
    def test_register_and_count(self):
        from oranged.extract import FigureRegistry
        fr = FigureRegistry()
        assert fr.count == 0
        fr.register(page_num=3, bbox=[0, 0, 100, 100], xref=1)
        assert fr.count == 1

    def test_placeholder(self):
        from oranged.extract import FigureRegistry
        fr = FigureRegistry()
        p = fr.placeholder(page_num=0, y_center=50, page_height=300)
        assert "page 1" in p
        assert "top" in p

    def test_summary_empty(self):
        from oranged.extract import FigureRegistry
        fr = FigureRegistry()
        assert fr.summary() == ""


# ─── analyse.py ──────────────────────────────────────────────────────────────

class TestAnalyse:
    def test_classify_safety(self):
        from oranged.analyse import analyse_markdown
        md = "# Safety Warnings\n\nDo not use near water.\n\n# Installation\n\nPlug in the device."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "SAFETY" in cats

    def test_classify_installation(self):
        from oranged.analyse import analyse_markdown
        md = "# Installation Guide\n\nStep 1: Unpack the unit.\n\nStep 2: Level the appliance."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "INSTALLATION" in cats

    def test_filter_by(self):
        from oranged.analyse import analyse_markdown
        md = "# Safety\n\nWarning.\n\n# Operation\n\nPress start."
        result = analyse_markdown(md)
        safety_only = result.filter_by("SAFETY")
        assert all("SAFETY" in s.category.upper() for s in safety_only.sections)

    def test_to_json(self):
        from oranged.analyse import analyse_markdown
        md = "# Troubleshooting\n\nError E1: check filter."
        result = analyse_markdown(md)
        j = result.to_json()
        assert "TROUBLESHOOTING" in j

    def test_empty_input(self):
        from oranged.analyse import analyse_markdown
        result = analyse_markdown("")
        assert result.total_lines == 0 or result.total_lines >= 0

    # ─── New document type categories ────────────────────────────────────────

    def test_classify_abstract(self):
        from oranged.analyse import analyse_markdown
        md = "# Abstract\n\nThis paper presents a novel approach to document extraction."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "ABSTRACT" in cats

    def test_classify_methodology(self):
        from oranged.analyse import analyse_markdown
        md = "# Methodology\n\nWe collected a dataset of 500 PDFs.\n\n# Results\n\nOur model achieves 95% accuracy."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "METHODOLOGY" in cats

    def test_classify_math(self):
        from oranged.analyse import analyse_markdown
        md = "# Theorem 3.1\n\nLet f(x) be a continuous function on [a,b]."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "MATH_FORMULA" in cats

    def test_classify_teaching(self):
        from oranged.analyse import analyse_markdown
        md = "# Syllabus\n\nThis course covers linear algebra.\n\n# Assessment\n\nHomework 40%, exam 60%."
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "TEACHING" in cats

    def test_classify_teaching_zh(self):
        from oranged.analyse import analyse_markdown
        md = "# 教学目标\n\n掌握微积分基本概念。\n\n# 教学过程\n\n第一课时：极限。"
        result = analyse_markdown(md)
        cats = [s.category for s in result.sections]
        assert "TEACHING" in cats


# ─── extract.py: Math formula preservation ───────────────────────────────────

class TestMathPreservation:
    def test_has_math_content(self):
        from oranged.extract import _has_math_content
        assert _has_math_content("f(x) = ∫ g(x) dx")
        assert _has_math_content("α + β = γ")
        assert not _has_math_content("Normal text without math")

    def test_preserve_math_symbols(self):
        from oranged.extract import _preserve_math_symbols
        result = _preserve_math_symbols("α + β = γ")
        assert r"\alpha" in result
        assert r"\beta" in result
        assert r"\gamma" in result

    def test_existing_latex_unchanged(self):
        from oranged.extract import _preserve_math_symbols
        original = "The equation $E = mc^2$ is famous"
        result = _preserve_math_symbols(original)
        assert result == original

    def test_no_math_unchanged(self):
        from oranged.extract import _preserve_math_symbols
        original = "This is plain text without any formulas"
        result = _preserve_math_symbols(original)
        assert result == original


# ─── router.py ───────────────────────────────────────────────────────────────

class TestStrategy:
    def test_enum_values(self):
        from oranged.router import Strategy
        assert Strategy.NATIVE.value == "NATIVE"
        assert Strategy.FULL_VLM.value == "FULL_VLM"
        assert len(Strategy) == 6


# ─── judge.py ────────────────────────────────────────────────────────────────

class TestJudge5D:
    def test_clean_markdown(self):
        from oranged.judge import Judge5D
        md = (
            "# Product Manual\n\n"
            "## Safety\n\nDo not immerse in water.\n\n"
            "## Installation\n\nPlace on flat surface.\n\n"
            "## Operation\n\nPress the power button.\n\n"
            "| Feature | Value |\n|:---|:---|\n| Power | 1200W |\n| Voltage | 220V |\n"
        )
        report = Judge5D().evaluate(md, page_count=5)
        assert report.overall_score >= 0.7
        assert report.passed is True

    def test_broken_markdown(self):
        from oranged.judge import Judge5D
        md = (
            "### Bad Start\n\n"
            "##### Skipped Levels\n\n"
            "```\nunclosed fence\n"
            "| a | b |\n| c |\n"
            "@@@garbage@@@\n"
        )
        report = Judge5D().evaluate(md, page_count=20)
        assert report.overall_score < 0.9

    def test_pass_threshold(self):
        from oranged.judge import PASS_THRESHOLD
        assert PASS_THRESHOLD == 0.70

    def test_academic_paper_scoring(self):
        from oranged.judge import Judge5D
        md = (
            "# Abstract\n\nThis paper presents a novel method.\n\n"
            "## Introduction\n\nPrior work has shown...\n\n"
            "## Methodology\n\nWe collected 500 samples.\n\n"
            "## Results\n\nOur approach achieves 95% accuracy.\n\n"
            "## Conclusion\n\nWe demonstrated that...\n"
        )
        report = Judge5D().evaluate(md, page_count=8)
        assert report.overall_score >= 0.7
        assert report.passed is True

    def test_new_partition_weights_exist(self):
        from oranged.judge import PARTITION_WEIGHTS
        for cat in ("ABSTRACT", "METHODOLOGY", "MATH_FORMULA", "TEACHING"):
            assert cat in PARTITION_WEIGHTS, f"Missing weight for {cat}"
            w = PARTITION_WEIGHTS[cat]
            total = sum(w.values())
            assert abs(total - 1.0) < 0.01, f"Weights for {cat} sum to {total}, expected 1.0"


# ─── adapters ────────────────────────────────────────────────────────────────

class TestAdapterRegistry:
    def test_register_and_list(self):
        from oranged.adapters.base import AdapterRegistry, BaseAdapter

        class DummyAdapter(BaseAdapter):
            name = "dummy"
            def recognize(self, image_bytes, prompt=""):
                return "test"
            def is_available(self):
                return True

        reg = AdapterRegistry()
        reg.register(DummyAdapter)
        assert "dummy" in reg.list_available()

    def test_get_unavailable(self):
        from oranged.adapters.base import AdapterRegistry, BaseAdapter

        class UnavailableAdapter(BaseAdapter):
            name = "unavail"
            def recognize(self, image_bytes, prompt=""):
                return ""
            def is_available(self):
                return False

        reg = AdapterRegistry()
        reg.register(UnavailableAdapter)
        assert reg.get("unavail") is None
        assert "unavail" not in reg.list_available()
