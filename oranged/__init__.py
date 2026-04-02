"""
orangeD — Hybrid Intelligent PDF-to-Markdown Pipeline

Native-first extraction with smart OCR/VLM fallback routing,
5-dimensional quality judge, and semantic document classification.
"""

__version__ = "0.1.0"

from oranged.extract import extract_pdf
from oranged.analyse import analyse_markdown
from oranged.router import route_page, Strategy
from oranged.judge import Judge5D

__all__ = ["extract_pdf", "analyse_markdown", "route_page", "Strategy", "Judge5D"]
