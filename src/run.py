import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location("__main__", os.path.join(os.path.dirname(os.path.abspath(__file__)), "selector.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["__main__"] = mod
spec.loader.exec_module(mod)
