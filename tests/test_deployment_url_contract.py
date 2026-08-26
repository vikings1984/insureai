#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDeploymentUrlContract(unittest.TestCase):
    def test_fallback_workflow_uses_deployment_url(self):
        text = (ROOT / ".github" / "workflows" / "deployment-verification.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_URL", text)
        self.assertNotIn("workflow_run:", text)
        self.assertNotIn('SITE_URL: "https://vikings1984.github.io/insureai"', text)

    def test_primary_cloudflare_workflow_verifies_live_site(self):
        text = (ROOT / ".github" / "workflows" / "deploy-cloudflare.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_URL", text)
        self.assertIn("Verify live deployment", text)
        self.assertIn("deployment_verification.py", text)
        self.assertIn("deployment_state_transition.py", text)
        self.assertIn("attach_deployment_verification", text)
        self.assertIn("contents: write", text)

    def test_probe_main_reads_deployment_url(self):
        text = (ROOT / "deployment_verification.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("DEPLOYMENT_URL", "")', text)
        self.assertNotIn('os.environ.get("SITE_URL", "")', text)


if __name__ == "__main__":
    unittest.main()
