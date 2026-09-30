#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atomic Publish + Run/Manifest tests (plan §十 / §十一 / §二十一 P0-2, P0-3).

The production quality gate is mocked so these tests exercise the publish
machinery (staging, manifest hashing, atomic swap, rollback) without depending on
the heavy gate contract. Real gate behavior is covered by test_production_quality_gate.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import atomic_publish
from run import Run

ROOT = Path(__file__).resolve().parent
FAKE_GATE_PASSED = {"version": 1, "status": "passed", "checks": [], "failed_checks": []}
FAKE_GATE_FAILED = {"version": 1, "status": "failed", "checks": [], "failed_checks": ["news_integrity"]}


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False) + "\n", encoding="utf-8")


def _make_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="insureai_atomic_root_"))
    _write(root / "data.json", {"news": [{"id": "a1", "published_at": "2026-01-01", "source_url": "https://x.com/a"}]})
    _write(root / "intelligence.json", {"events": [], "decisions": []})
    _write(root / "decision_credibility.json", {"status": "review", "reasons": ["ok"]})
    _write(root / "owner_risk_view.json", {"version": 2})
    _write(root / "evidence_availability.json", {"version": 1})
    _write(root / "decision_stability.json", {"version": 1})
    return root


class AtomicPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _make_root()
        self.staging = Path(tempfile.mkdtemp(prefix="insureai_atomic_staging_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.staging, ignore_errors=True)

    def test_build_staging_copies_and_stamps_provenance(self) -> None:
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            run = atomic_publish.build_staging(root=self.root, staging=self.staging)
        self.assertTrue((self.staging / "data.json").exists())
        staged = json.loads((self.staging / "data.json").read_text(encoding="utf-8"))
        self.assertIn("_provenance", staged)
        self.assertEqual(staged["_provenance"]["run_id"], run.run_id)
        self.assertEqual(Run.load(self.staging).run_id, run.run_id)

    def test_manifest_enumerates_artifacts_with_hashes_and_run_id(self) -> None:
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            run = atomic_publish.build_staging(root=self.root, staging=self.staging)
            manifest = atomic_publish.build_manifest(staging=self.staging)
        self.assertEqual(manifest["run_id"], run.run_id)
        self.assertEqual(manifest["build_sha"], run.build_sha)
        names = {a["path"] for a in manifest["artifacts"]}
        self.assertIn("data.json", names)
        for entry in manifest["artifacts"]:
            actual = atomic_publish._sha256_file(self.staging / entry["path"])
            self.assertEqual(entry["sha256"], actual, entry["path"])

    def test_validate_rejects_when_gate_fails(self) -> None:
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            atomic_publish.build_staging(root=self.root, staging=self.staging)
            atomic_publish.build_manifest(staging=self.staging)
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_FAILED):
            with self.assertRaises(ValueError):
                atomic_publish.validate_bundle(staging=self.staging)

    def test_validate_rejects_on_manifest_hash_mismatch(self) -> None:
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            atomic_publish.build_staging(root=self.root, staging=self.staging)
            atomic_publish.build_manifest(staging=self.staging)
        # tamper a staged artifact after the manifest was sealed
        (self.staging / "data.json").write_text('{"news": [{"id": "HACKED"}]}\n', encoding="utf-8")
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            with self.assertRaises(ValueError):
                atomic_publish.validate_bundle(staging=self.staging)

    def test_publish_is_atomic_on_failure(self) -> None:
        # root has a pre-existing production file + a legacy file that must survive
        orig_data = '{"news": [{"id": "ROOT_A"}]}\n'
        (self.root / "data.json").write_text(orig_data, encoding="utf-8")
        (self.root / "legacy.json").write_text('{"keep": true}\n', encoding="utf-8")
        _write(self.staging / "data.json", {"news": [{"id": "STAGE_B"}]})
        _write(self.staging / "intelligence.json", {"events": []})
        # minimal manifest so validate passes
        run = Run(run_id="run_test", build_sha="sha", schema_version="release-provenance-v1")
        run.save(self.staging)
        manifest = {
            "version": 1, "kind": "release_bundle", "run_id": "run_test",
            "build_sha": "sha", "schema_version": "release-provenance-v1", "engine_version": "4.2",
            "generated_at": "2026-01-01T00:00:00+00:00", "quality_gate": {"status": "passed", "failed_checks": []},
            "artifacts": [
                {"path": "data.json", "sha256": atomic_publish._sha256_file(self.staging / "data.json"), "bytes": 1},
                {"path": "intelligence.json", "sha256": atomic_publish._sha256_file(self.staging / "intelligence.json"), "bytes": 1},
            ], "artifact_count": 2,
        }
        _write(self.staging / atomic_publish.MANIFEST_NAME, manifest)

        calls = {"n": 0}

        def _boom(src, dst, *a, **k):
            calls["n"] += 1
            if calls["n"] >= 2:  # let one file land, then fail mid-swap
                raise OSError("simulated disk failure")

        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            with mock.patch.object(atomic_publish.shutil, "copy2", side_effect=_boom):
                with self.assertRaises(RuntimeError):
                    atomic_publish.publish(staging=self.staging, root=self.root)
        # root must be exactly as before the failed swap
        self.assertEqual((self.root / "data.json").read_text(encoding="utf-8"), orig_data)
        self.assertEqual((self.root / "legacy.json").read_text(encoding="utf-8"), '{"keep": true}\n')
        # staging left intact for the next retry
        self.assertEqual(json.loads((self.staging / "data.json").read_text(encoding="utf-8")), {"news": [{"id": "STAGE_B"}]})

    def test_release_end_to_end_publishes_when_gate_passes(self) -> None:
        with mock.patch.object(atomic_publish, "run_gate", return_value=FAKE_GATE_PASSED):
            out = atomic_publish.release(root=self.root, staging=self.staging)
        self.assertEqual(out["status"], "published")
        self.assertTrue((self.root / atomic_publish.MANIFEST_NAME).exists())
        published = json.loads((self.root / atomic_publish.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(published["run_id"], out["run_id"])


if __name__ == "__main__":
    unittest.main()
