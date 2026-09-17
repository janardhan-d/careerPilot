# Root conftest.py — adds the project root to sys.path so pytest
# can resolve 'agents', 'core', 'tools', 'models', etc. without PYTHONPATH.
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
