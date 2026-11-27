"""The 2024 rules module lives in the engine (D-583); this path stays importable and patchable as the same module object."""
import sys

import dnd_2024_rules

sys.modules[__name__] = dnd_2024_rules
