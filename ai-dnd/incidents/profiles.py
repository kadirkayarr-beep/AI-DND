"""Settlement and scene profiles for the Reality Envelope.

A location without a reviewed profile generates nothing. Missing review is
not permission to invent.
"""

from __future__ import annotations


def resolve(world, location_id):
    """Return the active profile for ``location_id`` or None."""
    return None
