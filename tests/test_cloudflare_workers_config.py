#!/usr/bin/env python3
import json
import unittest
from pathlib import Path


class TestCloudflareWorkersConfig(unittest.TestCase):
    def test_static_spa_config_is_explicit(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "wrangler.jsonc").read_text(encoding="utf-8"))
        self.assertEqual(config["name"], "insureai")
        self.assertEqual(config["compatibility_date"], "2026-08-22")
        self.assertEqual(config["assets"]["directory"], ".")
        self.assertEqual(config["assets"]["not_found_handling"], "single-page-application")

    def test_assets_ignore_excludes_internal_and_python_files(self):
        root = Path(__file__).resolve().parents[1]
        ignore = (root / ".assetsignore").read_text(encoding="utf-8")
        for item in ("*.py", "tests/", ".github/", "audit_ledger.json", "release_provenance.json", "decision_credibility.json"):
            self.assertIn(item, ignore)


if __name__ == "__main__":
    unittest.main()
