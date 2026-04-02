"""
orangeD — PaddleOCR adapter.

Wraps PaddleOCR (PP-OCRv4) for text recognition on scanned / image-only pages.
Supports both CPU and GPU modes.

Install: pip install orangeD[paddle]
"""

import tempfile
import os
from typing import Optional

from oranged.adapters.base import BaseAdapter


class PaddleAdapter(BaseAdapter):
    name = "paddle"

    def __init__(self, lang: str = "ch", use_angle_cls: bool = True,
                 use_gpu: bool = True):
        self._lang = lang
        self._use_angle_cls = use_angle_cls
        self._use_gpu = use_gpu
        self._ocr = None

    def _init_ocr(self):
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(
            use_angle_cls=self._use_angle_cls,
            lang=self._lang,
            use_gpu=self._use_gpu,
            show_log=False,
        )

    def is_available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        self._init_ocr()

        # PaddleOCR needs a file path, write to temp
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name

        try:
            result = self._ocr.ocr(tmp_path, cls=self._use_angle_cls)
            if not result or not result[0]:
                return ""
            lines = [line[1][0] for line in result[0]]
            return "\n".join(lines)
        finally:
            os.unlink(tmp_path)

    def recognize_table(self, image_bytes: bytes) -> str:
        """PaddleOCR table extraction with structural grouping."""
        self._init_ocr()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name

        try:
            result = self._ocr.ocr(tmp_path, cls=self._use_angle_cls)
            if not result or not result[0]:
                return ""

            # Sort by Y coordinate then X for reading order
            boxes = []
            for line in result[0]:
                coords = line[0]
                text = line[1][0]
                y_center = (coords[0][1] + coords[2][1]) / 2
                x_center = (coords[0][0] + coords[2][0]) / 2
                boxes.append((y_center, x_center, text))

            boxes.sort(key=lambda b: (round(b[0] / 15) * 15, b[1]))

            # Group into rows by Y proximity
            rows = []
            current_row = []
            last_y = -999
            for y, x, text in boxes:
                if abs(y - last_y) > 15:
                    if current_row:
                        rows.append(current_row)
                    current_row = [text]
                else:
                    current_row.append(text)
                last_y = y
            if current_row:
                rows.append(current_row)

            if len(rows) < 2:
                return "\n".join(" | ".join(r) for r in rows)

            # Format as Markdown table
            max_cols = max(len(r) for r in rows)
            lines = []
            for i, row in enumerate(rows):
                padded = row + [""] * (max_cols - len(row))
                lines.append("| " + " | ".join(padded) + " |")
                if i == 0:
                    lines.append("| " + " | ".join(["---"] * max_cols) + " |")

            return "\n".join(lines)
        finally:
            os.unlink(tmp_path)
