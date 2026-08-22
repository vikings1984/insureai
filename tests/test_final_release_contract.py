import unittest
from pathlib import Path


class FinalReleaseContractTests(unittest.TestCase):
    def test_manifest_is_restamped_after_final_audit(self):
        workflow = Path('.github/workflows/daily-collect.yml').read_text(encoding='utf-8')
        audit_marker = 'name: Validate final analytical audit ledger'
        restamp_marker = 'name: Restamp final release manifest after final audit'
        provenance_marker = 'name: Build final release provenance'
        self.assertIn(audit_marker, workflow)
        self.assertIn(restamp_marker, workflow)
        self.assertIn(provenance_marker, workflow)
        self.assertLess(workflow.index(audit_marker), workflow.index(restamp_marker))
        self.assertLess(workflow.index(restamp_marker), workflow.index(provenance_marker))

    def test_final_manifest_validation_binds_marker_to_index(self):
        workflow = Path('.github/workflows/daily-collect.yml').read_text(encoding='utf-8')
        self.assertIn("Path('index.html').read_text(encoding='utf-8').find(m['release_marker']) >= 0", workflow)
        self.assertIn("assert audit.get('privacy') == 'hashes_and_metadata_only'", workflow)


if __name__ == '__main__':
    unittest.main()
