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
