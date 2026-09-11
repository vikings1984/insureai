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
        # F-03：Workers 只上传精简后的 dist/（前端 + 首屏分片），
        # 体积最大的分析产物已外置到 Pages CDN，不再进 Workers。
        self.assertEqual(config["assets"]["directory"], "./dist")
        self.assertEqual(config["assets"]["not_found_handling"], "single-page-application")

    def test_assets_ignore_excludes_internal_and_python_files(self):
        root = Path(__file__).resolve().parents[1]
        ignore = (root / ".assetsignore").read_text(encoding="utf-8")
        for item in ("*.py", "tests/", ".github/", "audit_ledger.json", "release_provenance.json", "decision_credibility.json"):
            self.assertIn(item, ignore)


if __name__ == "__main__":
    unittest.main()
