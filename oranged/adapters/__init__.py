"""
OCR/VLM adapter registry.

Each adapter implements a common interface:
  - recognize(image_path: str, prompt: str = "") -> str
  - is_available() -> bool
"""

from oranged.adapters.base import BaseAdapter, AdapterRegistry

__all__ = ["BaseAdapter", "AdapterRegistry"]
