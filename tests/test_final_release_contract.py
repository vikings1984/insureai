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

    def test_smoke_builds_freshness_and_evidence_before_credibility_and_release(self):
        smoke = Path('scripts/verify_full_pipeline.py').read_text(encoding='utf-8')
        freshness = smoke.index('[sys.executable, "freshness.py"]')
        availability = smoke.index('[sys.executable, "evidence_availability.py"]')
        credibility = smoke.index('[sys.executable, "decision_credibility.py"]')
        release = smoke.index('[sys.executable, "release_manifest.py"]')
        self.assertLess(freshness, availability)
        self.assertLess(availability, credibility)
        self.assertLess(credibility, release)

    def test_daily_pipeline_builds_freshness_and_evidence_before_credibility(self):
        workflow = Path('.github/workflows/daily-collect.yml').read_text(encoding='utf-8')
        freshness = workflow.index('name: Build input freshness')
        availability = workflow.index('name: Build evidence availability')
        credibility = workflow.index('name: Build decision credibility summary')
        final_audit = workflow.index('name: Build final analytical audit ledger')
        self.assertLess(freshness, availability)
        self.assertLess(availability, credibility)
        self.assertLess(credibility, final_audit)
        self.assertIn('run: python3 freshness.py', workflow)
        self.assertIn('run: python3 evidence_availability.py', workflow)


if __name__ == '__main__':
    unittest.main()
