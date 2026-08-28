"""Guard rails for import-time hygiene.

Background: the repository once shipped a top-level `signal.py`. It shadowed
the Python standard library `signal` module, so `from signal import
extract_signals` resolved to whichever came first on `sys.path`. On CI the
repository root happened to win; in any environment where it did not, nine
test modules failed at import time. Import correctness must not depend on
path ordering luck, so no module may be named after a stdlib module.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("", "scripts")


class ModuleHygieneTests(unittest.TestCase):
    def test_no_module_shadows_the_standard_library(self):
        stdlib = getattr(sys, "stdlib_module_names", None)
        if not stdlib:
            self.skipTest("sys.stdlib_module_names is unavailable")

        offenders = []
        for relative in SCAN_DIRS:
            directory = ROOT / relative if relative else ROOT
            for path in sorted(directory.glob("*.py")):
                if path.stem in stdlib:
                    offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual(
            offenders,
            [],
            "modules named after stdlib modules break imports when the "
            "repository root is not ahead of the stdlib on sys.path; "
            "rename them instead of relying on path ordering",
        )

    def test_intelligence_signal_is_importable_by_name(self):
        spec = importlib.util.find_spec("intelligence_signal")
        self.assertIsNotNone(spec, "intelligence_signal must be importable")
        assert spec is not None
        self.assertEqual(Path(spec.origin).resolve(), (ROOT / "intelligence_signal.py").resolve())

    def test_stdlib_signal_is_not_masked(self):
        """The stdlib `signal` module must resolve to the stdlib, not to us."""
        spec = importlib.util.find_spec("signal")
        self.assertIsNotNone(spec)
        assert spec is not None and spec.origin is not None
        self.assertNotIn("insureai", spec.origin)
        self.assertNotEqual(Path(spec.origin).resolve(), (ROOT / "intelligence_signal.py").resolve())


if __name__ == "__main__":
    unittest.main()
