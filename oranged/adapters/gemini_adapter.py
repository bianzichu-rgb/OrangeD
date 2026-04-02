"""
orangeD — Google Gemini Vision adapter.

Cloud-based VLM for complex pages, gold render generation, and distillation.

Install: pip install orangeD[gemini]
Requires: GOOGLE_API_KEY environment variable.
"""

import os
import time
from typing import Optional

from oranged.adapters.base import BaseAdapter


class GeminiAdapter(BaseAdapter):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash-001",
                 api_key: Optional[str] = None, max_retries: int = 3):
        self._model = model
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._max_retries = max_retries
        self._client = None

    def _init_client(self):
        if self._client is not None:
            return
        import google.genai as genai
        self._client = genai.Client(api_key=self._api_key)

    def is_available(self) -> bool:
        try:
            import google.genai  # noqa: F401
            return bool(self._api_key or os.getenv("GOOGLE_API_KEY"))
        except ImportError:
            return False

    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        self._init_client()
        from google.genai import types as gtypes

        full_prompt = prompt or (
            "Extract all text and tables from this image. "
            "Output in clean Markdown format. No explanations."
        )

        for attempt in range(self._max_retries):
            try:
                resp = self._client.models.generate_content(
                    model=self._model,
                    contents=[
                        gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        full_prompt,
                    ],
                )
                if resp and resp.text:
                    return resp.text.strip()
                return ""
            except Exception as e:
                if "429" in str(e):
                    wait = (attempt + 1) * 15
                    time.sleep(wait)
                else:
                    return ""
        return ""
