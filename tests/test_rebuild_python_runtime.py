import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_python_runtime.py"
SPEC = importlib.util.spec_from_file_location("rebuild_python_runtime", MODULE_PATH)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RebuildPythonRuntimeTests(unittest.TestCase):
    def test_probe_reports_missing_executable(self):
        result = runtime.probe(Path("/definitely/missing/python"), ["json"])
        self.assertFalse(result["healthy"])

    def test_healthy_runtime_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as temporary:
            venv = Path(temporary) / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python3").symlink_to(sys.executable)
            result = runtime.rebuild(venv, ["unused-package"], ["json"])
            self.assertFalse(result["changed"])
            self.assertTrue(result["after"]["healthy"])
