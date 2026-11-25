"""Old name of the root module `model_phase`; both names are one module object (shim, removed after wave 1)."""
import sys

import model_phase as _m

sys.modules[__name__] = _m
