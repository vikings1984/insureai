#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDeploymentUrlContract(unittest.TestCase):
    def test_fallback_workflow_uses_deployment_url(self):
        text = (ROOT / ".github" / "workflows" / "deployment-verification.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_URL", text)
        # The fallback must stay decoupled from the deploy chain: its job is to
        # catch drift between deploys (outage, rollback, manual edit), so it has
        # to keep running even when no deploy fired. Post-deploy verification
        # belongs to deploy-cloudflare.yml, which is already anchored to publish.
        self.assertNotIn("workflow_run:", text)
        self.assertNotIn('SITE_URL: "https://vikings1984.github.io/insureai"', text)

    def test_fallback_tolerates_propagation_lag(self):
        """The fallback runs on its own clock, so the site may still be serving
        the previous release while a freshly stamped marker propagates. That is
        `stale`, not an outage. Anchoring this probe to the deploy instead
        would stop it detecting drift when no deploy ran.
        """
        text = (ROOT / ".github" / "workflows" / "deployment-verification.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_TOLERATE_STALE", text)
        self.assertIn("stale", text)

    def test_primary_workflow_stays_the_strict_release_gate(self):
        """deploy-cloudflare.yml verifies inline right after publishing, so it
        can and must demand an exact marker match.
        """
        text = (ROOT / ".github" / "workflows" / "deploy-cloudflare.yml").read_text(encoding="utf-8")
        self.assertIn("Verify live deployment", text)
        self.assertNotIn("DEPLOYMENT_TOLERATE_STALE", text)

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
