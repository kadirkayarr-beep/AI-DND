"""The 2024 rules module lives in the engine (D-583); this path stays importable and patchable as the same module object."""
import sys
from typing import TYPE_CHECKING

import dnd_2024_rules

if TYPE_CHECKING:  # the alias below hides the names from a type checker; this makes them visible without changing runtime
    from dnd_2024_rules import *

sys.modules[__name__] = dnd_2024_rules
