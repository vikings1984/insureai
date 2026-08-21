import tempfile
import unittest
from pathlib import Path

from audit_ledger import build_ledger, sha256_file


class AuditLedgerTests(unittest.TestCase):
    def test_ledger_contains_hashes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.json'
            path.write_text('{"events":[1,2],"version":1}', encoding='utf-8')
            digest = sha256_file(path)
            self.assertEqual(len(digest), 64)
            self.assertNotIn('events', digest)

    def test_ledger_schema_is_privacy_preserving(self):
        ledger = build_ledger()
        self.assertEqual(ledger['version'], 1)
        self.assertEqual(ledger['schema_version'], 'audit-ledger-v1')
        self.assertEqual(ledger['privacy'], 'hashes_and_metadata_only')
        for row in ledger['stages']:
            self.assertEqual(len(row['sha256']), 64)
            self.assertNotIn('title', row)
            self.assertNotIn('url', row)
            self.assertNotIn('body', row)


if __name__ == '__main__':
    unittest.main()
