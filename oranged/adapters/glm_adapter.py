"""
orangeD — GLM-4V / Zhipu AI adapter.

Cloud-based VLM for table rescue and complex page extraction.

Install: pip install zhipuai
Requires: ZHIPU_API_KEY environment variable.
"""

import os
import base64
from typing import Optional

from oranged.adapters.base import BaseAdapter


class GLMAdapter(BaseAdapter):
    name = "glm"

    def __init__(self, model: str = "glm-4v-flash",
                 api_key: Optional[str] = None):
        self._model = model
        self._api_key = api_key or os.getenv("ZHIPU_API_KEY")
        self._client = None

    def _init_client(self):
        if self._client is not None:
            return
        from zhipuai import ZhipuAI
        self._client = ZhipuAI(api_key=self._api_key)

    def is_available(self) -> bool:
        try:
            import zhipuai  # noqa: F401
            return bool(self._api_key or os.getenv("ZHIPU_API_KEY"))
        except ImportError:
            return False

    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        self._init_client()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        full_prompt = prompt or (
            "请将此图片中的内容提取为干净的 Markdown 格式。"
            "不要包含任何多余解释，只需输出 Markdown。"
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {"type": "image_url", "image_url": {"url": b64}},
                    ]
                }],
                timeout=120.0,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return ""
