"""Old name of the root module `core_resolution`; both names are one module object (shim, removed after wave 1)."""
import sys

import core_resolution as _m

sys.modules[__name__] = _m
