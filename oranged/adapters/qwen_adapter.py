"""
orangeD — Qwen2.5-VL / Qwen3-VL local VLM adapter.

Runs locally on GPU via HuggingFace Transformers.
Supports both Qwen2.5-VL and Qwen3-VL model families.

Install: pip install orangeD[qwen]
"""

import tempfile
import os
from typing import Optional

from oranged.adapters.base import BaseAdapter


class QwenAdapter(BaseAdapter):
    name = "qwen"

    def __init__(self, model_id: str = "Qwen/Qwen2.5-VL-3B-Instruct"):
        self._model_id = model_id
        self._model = None
        self._processor = None

    def _init_model(self):
        if self._model is not None:
            return
        import torch
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self._model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )
        self._processor = AutoProcessor.from_pretrained(self._model_id)

    def is_available(self) -> bool:
        try:
            import torch
            import transformers  # noqa: F401
            return torch.cuda.is_available()
        except ImportError:
            return False

    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        self._init_model()
        import torch
        from qwen_vl_utils import process_vision_info

        # Write image to temp file for Qwen VL utils
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name

        try:
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": tmp_path},
                    {"type": "text", "text": prompt or
                     "Extract all text from this image. Output in clean Markdown format."},
                ]
            }]

            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self._processor(
                text=[text], images=image_inputs, videos=video_inputs,
                padding=True, return_tensors="pt"
            ).to("cuda")

            with torch.no_grad():
                generated_ids = self._model.generate(**inputs, max_new_tokens=2048)

            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = self._processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            return output_text.strip()
        finally:
            os.unlink(tmp_path)
