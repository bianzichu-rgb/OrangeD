"""
orangeD — Base adapter interface and registry.

All OCR/VLM adapters implement BaseAdapter so they can be plugged into
the extraction pipeline interchangeably.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Type


class BaseAdapter(ABC):
    """Base class for all OCR/VLM adapters."""

    name: str = "base"

    @abstractmethod
    def recognize(self, image_bytes: bytes, prompt: str = "") -> str:
        """
        Run OCR/VLM on an image and return extracted text.

        Args:
            image_bytes: PNG image bytes.
            prompt: Optional prompt for VLM-based adapters.

        Returns:
            Extracted text as a string.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter's dependencies are installed and configured."""
        ...

    def recognize_table(self, image_bytes: bytes) -> str:
        """Specialized table extraction. Defaults to generic recognize."""
        return self.recognize(
            image_bytes,
            prompt="Extract the table from this image. Output in clean Markdown format."
        )


class AdapterRegistry:
    """
    Registry of available OCR/VLM adapters.

    Usage:
        registry = AdapterRegistry()
        registry.register(PaddleAdapter)
        adapter = registry.get("paddle")
        text = adapter.recognize(image_bytes)
    """

    def __init__(self):
        self._adapters: Dict[str, BaseAdapter] = {}
        self._classes: Dict[str, Type[BaseAdapter]] = {}

    def register(self, adapter_class: Type[BaseAdapter]):
        """Register an adapter class (lazy instantiation)."""
        self._classes[adapter_class.name] = adapter_class

    def get(self, name: str) -> Optional[BaseAdapter]:
        """Get an adapter instance by name. Instantiates on first access."""
        if name in self._adapters:
            return self._adapters[name]
        if name in self._classes:
            instance = self._classes[name]()
            if instance.is_available():
                self._adapters[name] = instance
                return instance
        return None

    def list_available(self) -> list:
        """Return names of all adapters whose dependencies are met."""
        available = []
        for name, cls in self._classes.items():
            try:
                inst = cls()
                if inst.is_available():
                    available.append(name)
            except Exception:
                pass
        return available

    def get_best(self) -> Optional[BaseAdapter]:
        """Return the first available adapter in priority order."""
        for name in self._classes:
            adapter = self.get(name)
            if adapter:
                return adapter
        return None


# Global registry instance
_global_registry = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    return _global_registry
