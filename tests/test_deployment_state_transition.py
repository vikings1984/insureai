import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.deployment_state_transition as transition


class DeploymentStateTransitionTests(unittest.TestCase):
    def _write_current(self, root: Path, payload: dict) -> None:
        (root / "deployment_verification.json").write_text(
            json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def test_same_state_does_not_append_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "status": "pending",
                "verified": False,
                "site_url": "https://example.test",
                "final_url": "https://example.test",
                "expected_marker": "InsureAI",
                "release_marker": "insureai-old",
                "http_status": None,
                "marker_found": False,
                "error": "request_failed:TimeoutError",
                "checked_at": "2026-08-22T00:00:00+00:00",
            }
            current = dict(previous, checked_at="2026-08-22T06:00:00+00:00")
            self._write_current(root, current)
            (root / "deployment_verification_history.json").write_text("[]\n", encoding="utf-8")

            with patch.object(transition, "CURRENT", root / "deployment_verification.json"), \
                 patch.object(transition, "LATEST", root / "deployment_verification_latest.json"), \
                 patch.object(transition, "HISTORY", root / "deployment_verification_history.json"), \
                 patch.object(transition, "_load_previous", return_value=previous):
                transition.main()

            saved = json.loads((root / "deployment_verification.json").read_text(encoding="utf-8"))
            history = json.loads((root / "deployment_verification_history.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, previous)
            self.assertEqual(history, [])
            latest = json.loads((root / "deployment_verification_latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest, current)

    def test_state_change_appends_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {"status": "pending", "verified": False, "error": "site_url_missing"}
            current = {"status": "verified", "verified": True, "error": None, "checked_at": "2026-08-22T06:00:00+00:00"}
            self._write_current(root, current)
            (root / "deployment_verification_history.json").write_text("[]\n", encoding="utf-8")

            with patch.object(transition, "CURRENT", root / "deployment_verification.json"), \
                 patch.object(transition, "LATEST", root / "deployment_verification_latest.json"), \
                 patch.object(transition, "HISTORY", root / "deployment_verification_history.json"), \
                 patch.object(transition, "_load_previous", return_value=previous):
                transition.main()

            history = json.loads((root / "deployment_verification_history.json").read_text(encoding="utf-8"))
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["status"], "verified")
            self.assertTrue(history[0]["verified"])

    def test_release_marker_change_is_a_transition_even_when_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "status": "verified",
                "verified": True,
                "site_url": "https://example.test",
                "final_url": "https://example.test",
                "expected_marker": "insureai-v2",
                "release_marker": "insureai-release-v2",
                "http_status": 200,
                "marker_found": True,
                "error": None,
                "checked_at": "2026-08-22T00:00:00+00:00",
            }
            current = dict(
                previous,
                expected_marker="insureai-v3",
                release_marker="insureai-release-v3",
                checked_at="2026-08-22T06:00:00+00:00",
            )
            self._write_current(root, current)
            (root / "deployment_verification_history.json").write_text("[]\n", encoding="utf-8")

            with patch.object(transition, "CURRENT", root / "deployment_verification.json"), \
                 patch.object(transition, "LATEST", root / "deployment_verification_latest.json"), \
                 patch.object(transition, "HISTORY", root / "deployment_verification_history.json"), \
                 patch.object(transition, "_load_previous", return_value=previous):
                transition.main()

            saved = json.loads((root / "deployment_verification.json").read_text(encoding="utf-8"))
            history = json.loads((root / "deployment_verification_history.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["release_marker"], current["release_marker"])
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["release_marker"], current["release_marker"])
            self.assertTrue(history[0]["verified"])


if __name__ == "__main__":
    unittest.main()
