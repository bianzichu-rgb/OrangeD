"""
orangeD — Using OCR adapters for scanned PDFs.

Shows how to plug in PaddleOCR, Qwen-VL, or Gemini for
pages that can't be extracted natively.
"""

from oranged import extract_pdf
from oranged.router import route_pdf, Strategy

# 1. Check routing — see which pages need OCR
strategies = route_pdf("scanned_manual.pdf")
native_pages = sum(1 for s in strategies.values() if s == Strategy.NATIVE)
ocr_pages = len(strategies) - native_pages
print(f"Pages: {len(strategies)} total, {native_pages} native, {ocr_pages} need OCR")

# 2. Use PaddleOCR adapter for scanned pages
from oranged.adapters.paddle_adapter import PaddleAdapter

adapter = PaddleAdapter(lang="ch", use_gpu=True)
if adapter.is_available():
    md = extract_pdf("scanned_manual.pdf", ocr_adapter=adapter)
    print(f"Extracted with PaddleOCR fallback: {len(md)} chars")

# 3. Or use Qwen-VL for higher quality (needs GPU)
# from oranged.adapters.qwen_adapter import QwenAdapter
# adapter = QwenAdapter(model_id="Qwen/Qwen2.5-VL-3B-Instruct")

# 4. Or use Gemini for cloud-based extraction
# from oranged.adapters.gemini_adapter import GeminiAdapter
# adapter = GeminiAdapter()  # needs GOOGLE_API_KEY env var
