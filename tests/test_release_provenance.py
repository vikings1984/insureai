#!/usr/bin/env python3
import json, tempfile, unittest
from pathlib import Path
from release_provenance import attach_deployment_verification, build_provenance

class TestReleaseProvenance(unittest.TestCase):
    def _root(self):
        root=Path(tempfile.mkdtemp())
        (root/"release_manifest.json").write_text(json.dumps({"version":1,"source_commit":"manifest-sha","release_marker":"insureai:commit-123","release_channel":"github_pages","site_url":"https://example.test","quality_status":"passed","deployment_status":"pending","deployment_verified":False}),encoding="utf-8")
        (root/"audit_ledger.json").write_text(json.dumps({"version":1,"privacy":"hashes_and_metadata_only","stages":[{"artifact":"data.json","sha256":"a"*64}]}),encoding="utf-8")
        (root/"change_impact.json").write_text(json.dumps({"version":1,"baseline_available":True,"impacted_count":3}),encoding="utf-8")
        return root
    def test_build_contains_release_identity(self):
        p=build_provenance(source_commit="commit-123",site_url="https://example.test",root=self._root())
        self.assertEqual(p["release_marker"],"insureai:commit-123"); self.assertEqual(p["deployment"]["status"],"pending"); self.assertFalse(p["deployment"]["verified"])
    def test_verified_requires_matching_release_marker(self):
        root=self._root(); (root/"release_provenance.json").write_text(json.dumps(build_provenance(source_commit="commit-123",site_url="https://example.test",root=root)),encoding="utf-8")
        (root/"deployment_verification.json").write_text(json.dumps({"version":2,"status":"verified","verified":True,"release_marker":"insureai:old","release_marker_found":True,"http_status":200,"marker_found":True,"checked_at":"2026-08-22T00:00:00+00:00"}),encoding="utf-8")
        p=attach_deployment_verification(root=root); self.assertEqual(p["deployment"]["status"],"stale"); self.assertFalse(p["deployment"]["verified"])
        (root/"deployment_verification.json").write_text(json.dumps({"version":2,"status":"verified","verified":True,"release_marker":"insureai:commit-123","release_marker_found":True,"http_status":200,"marker_found":True,"checked_at":"2026-08-22T00:00:01+00:00"}),encoding="utf-8")
        p=attach_deployment_verification(root=root); self.assertEqual(p["deployment"]["status"],"verified"); self.assertTrue(p["deployment"]["verified"])

if __name__=="__main__": unittest.main()
