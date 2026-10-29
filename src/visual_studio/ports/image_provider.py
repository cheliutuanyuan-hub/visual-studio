"""Ports (hexagonal architecture): the image-generation abstraction.

The service depends on this interface, never on a concrete backend. Real and
mock providers live behind it, so the rest of the system is fully decoupled and
testable offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from visual_studio.domain.models import GenerationResult, GenerationTask


class ImageProvider(ABC):
    """Port for anything that can turn a :class:`GenerationTask` into a result.

    Concrete adapters: ``MockProvider`` (default, writes real SVG files),
    ``SeedreamProvider`` and ``GptImageProvider`` (structured stubs).
    """

    #: Stable provider name used in task metadata and routing.
    name: str = "abstract"

    @abstractmethod
    def generate(self, task: GenerationTask) -> GenerationResult:
        """Produce an artifact for ``task``.

        Implementations must return a :class:`GenerationResult`. A ``None``
        ``image_path`` signals failure (the scheduler will mark the task
        failed).
        """
        raise NotImplementedError
