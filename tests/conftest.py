"""Load the HA-independent modules without importing Home Assistant."""

import importlib.util
from pathlib import Path
import sys
import types

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "luxpower_lxp"

pkg = types.ModuleType("luxpower_lxp")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["luxpower_lxp"] = pkg

for name in ("protocol", "client"):
    spec = importlib.util.spec_from_file_location(f"luxpower_lxp.{name}", PKG_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
