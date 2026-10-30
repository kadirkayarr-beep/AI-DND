"""Class-specific progression, one module per class, behind a small registry. `character_progression` keeps the shared flow.

To add a class: write `class_progression/<class>.py` with a `ClassProgression` subclass overriding the hooks it needs and a module
level `HANDLER`, then add one line to `CLASS_MODULES`. Unregistered classes get the `ClassProgression` defaults.
"""
from __future__ import annotations

import importlib
from typing import Any

from class_progression.base import ClassProgression

CLASS_MODULES = (
    "barbarian",
    "fighter",
    "rogue",
    "sorcerer",
)

_DEFAULT = ClassProgression()
_REGISTRY: dict[str, ClassProgression] = {}


def for_class(class_name: Any) -> ClassProgression:
    return _REGISTRY.get(class_name, _DEFAULT) if isinstance(class_name, str) else _DEFAULT


def registered() -> tuple[ClassProgression, ...]:
    return tuple(_REGISTRY.values())


def _register(handler: ClassProgression) -> None:
    """A class name is one non-empty string, registered once: a duplicate would silently replace the earlier handler."""
    if type(handler.name) is not str or not handler.name or handler.name in _REGISTRY:
        raise ValueError(f"Invalid or duplicate class handler name: {handler.name!r}")
    _REGISTRY[handler.name] = handler


# The class modules import character_progression, which re-exports names from them: whichever side is imported first, that
# module has to reach this point with the two functions above defined and character_progression loaded before the loop.
import character_progression  # noqa: E402,F401

for _module in CLASS_MODULES:
    _register(importlib.import_module(f"{__name__}.{_module}").HANDLER)
