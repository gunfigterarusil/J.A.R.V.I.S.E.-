"""core/module_base.py — CognitiveModule base class.

All cognitive modules inherit from CognitiveModule.  The kernel calls:
  1. initialize(kernel)  — once at registration time
  2. tick(dt)            — every kernel tick (async, preferred)
  3. update(dt)          — legacy sync fallback
  4. on_event(event)     — for every subscribed event type
  5. shutdown()          — on kernel stop

Modules must NOT import from other modules directly.
They communicate only through the kernel's event_bus.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.kernel import Kernel
    from core.event_bus import CognitiveEvent


class CognitiveModule:
    """Base class for all cognitive modules."""

    # Subclasses should override these class-level defaults
    MODULE_ID: str = "base_module"
    MODULE_DESCRIPTION: str = ""
    MODULE_VERSION: str = "0.1.0"

    def __init__(self, module_id: str, cost: dict) -> None:
        self.module_id = module_id
        # cost: {"cpu": float, "gpu": float, "ram": float}  — 0..1 fractions
        self.cost = cost
        self.kernel: Optional["Kernel"] = None
        self.enabled: bool = True
        self.module_metadata: dict = {
            "description": self.MODULE_DESCRIPTION,
            "version": self.MODULE_VERSION,
        }

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def initialize(self, kernel: "Kernel") -> None:
        """Called once by the kernel when the module is registered.
        Subclasses should subscribe to events here via:
          kernel.event_bus.register_consumer(self.module_id, [...])
        """
        self.kernel = kernel

    async def tick(self, dt: float) -> None:
        """Async per-tick update. Prefer this over update() for new modules."""
        self.update(dt)

    def update(self, dt: float) -> None:
        """Sync per-tick update. Kept for simple modules that don't need async."""
        pass

    async def on_event(self, event: "CognitiveEvent") -> None:
        """Called for every subscribed event type."""
        pass

    def shutdown(self) -> None:
        """Called on kernel stop. Save state here via kernel.persistence."""
        pass

    # ------------------------------------------------------------------
    # Serialisation (for web UI / debugging)
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "enabled": self.enabled,
            "cost": self.cost,
            "metadata": self.module_metadata,
        }
