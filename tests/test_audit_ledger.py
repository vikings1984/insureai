import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_ledger


class AuditLedgerTests(unittest.TestCase):
    def test_ledger_has_hashes_and_no_content_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text(json.dumps({"news": [{"title": "secret title", "url": "https://example.com", "body": "private"}]}), encoding="utf-8")
            with patch.object(audit_ledger, "ROOT", root):
                ledger = audit_ledger.build_ledger()
        row = ledger["stages"][0]
        self.assertEqual(len(row["sha256"]), 64)
        self.assertNotIn("title", row)
        self.assertNotIn("url", row)
        self.assertNotIn("body", row)
        self.assertEqual(ledger["privacy"], "hashes_and_metadata_only")

    def test_empty_or_invalid_artifact_is_skipped_without_content_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text("not-json", encoding="utf-8")
            with patch.object(audit_ledger, "ROOT", root):
                ledger = audit_ledger.build_ledger()
        self.assertEqual(ledger["stages"][0]["counts"], {})
        self.assertEqual(len(ledger["stages"][0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
