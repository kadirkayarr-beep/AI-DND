"""Player-safe incident annotation. Not a quest, journal, or mission marker."""

from __future__ import annotations


def scene_annotation(world):
    """Return what the player may see about incidents at the current scene.

    Until awareness evidence exists, the player sees nothing.
    """
    return []
