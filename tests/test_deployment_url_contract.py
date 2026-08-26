#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDeploymentUrlContract(unittest.TestCase):
    def test_workflow_uses_deployment_url_not_canonical_site_url(self):
        text = (ROOT / ".github" / "workflows" / "deployment-verification.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_URL", text)
        self.assertNotIn('SITE_URL: "https://vikings1984.github.io/insureai"', text)

    def test_workflow_verifies_after_successful_cloudflare_deploy(self):
        text = (ROOT / ".github" / "workflows" / "deployment-verification.yml").read_text(encoding="utf-8")
        self.assertIn('workflow_run:', text)
        self.assertIn('workflows: ["Deploy to Cloudflare Workers"]', text)
        self.assertIn('types: [completed]', text)
        self.assertIn("github.event.workflow_run.head_sha", text)
        self.assertIn("github.event.workflow_run.head_branch", text)

    def test_probe_main_reads_deployment_url(self):
        text = (ROOT / "deployment_verification.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("DEPLOYMENT_URL", "")', text)
        self.assertNotIn('os.environ.get("SITE_URL", "")', text)


if __name__ == "__main__":
    unittest.main()
