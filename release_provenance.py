#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and update a privacy-safe release provenance record."""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from deployment_trend import attribute_deployment_trend
ROOT=Path(__file__).resolve().parent; OUTPUT=ROOT/"release_provenance.json"

def _read_json(path): return json.loads(path.read_text(encoding="utf-8"))
def _read_history(path):
    if not path.exists(): return []
    data=_read_json(path); return data if isinstance(data,list) else []
def _sha256(path):
    h=hashlib.sha256();
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def build_provenance(*, source_commit, site_url, root=ROOT):
    release_path=root/"release_manifest.json"; audit_path=root/"audit_ledger.json"; impact_path=root/"change_impact.json"; deployment_path=root/"deployment_verification.json"; history_path=root/"deployment_verification_history.json"
    release=_read_json(release_path); audit=_read_json(audit_path); impact=_read_json(impact_path) if impact_path.exists() else {}; deployment=_read_json(deployment_path) if deployment_path.exists() else {}; history=_read_history(history_path)
    release_marker=str(release.get("release_marker") or ""); verified=bool(deployment.get("verified",False)) and deployment.get("release_marker")==release_marker
    status="verified" if verified else ("stale" if deployment.get("verified") else release.get("deployment_status","pending"))
    return {"version":1,"schema_version":"release-provenance-v1","source_commit":source_commit or release.get("source_commit") or "unknown","release_marker":release_marker,"release_channel":release.get("release_channel","github_pages"),"site_url":site_url or release.get("site_url",""),"quality":{"status":release.get("quality_status","unknown"),"audit_privacy":audit.get("privacy","unknown"),"audit_stage_count":len(audit.get("stages",[])),"audit_artifact_count":len({r.get("artifact") for r in audit.get("stages",[]) if r.get("artifact")})},"impact":{"baseline_available":bool(impact.get("baseline_available",False)),"impacted_count":int(impact.get("impacted_count",0))},"deployment":{"status":status,"verified":verified,"checked_at":deployment.get("checked_at"),"http_status":deployment.get("http_status"),"marker_found":bool(deployment.get("marker_found",False)),"release_marker_found":bool(deployment.get("release_marker_found",False)),"error":deployment.get("error"),"trend":attribute_deployment_trend(history)},"artifacts":{"release_manifest_sha256":_sha256(release_path),"audit_ledger_sha256":_sha256(audit_path),"change_impact_sha256":_sha256(impact_path) if impact_path.exists() else None,"deployment_verification_sha256":_sha256(deployment_path) if deployment_path.exists() else None,"deployment_history_sha256":_sha256(history_path) if history_path.exists() else None},"generated_at":datetime.now(timezone.utc).isoformat()}

def attach_deployment_verification(*, root=ROOT):
    provenance_path=root/"release_provenance.json"; deployment_path=root/"deployment_verification.json"; history_path=root/"deployment_verification_history.json"
    provenance=_read_json(provenance_path); deployment=_read_json(deployment_path); history=_read_history(history_path); expected=str(provenance.get("release_marker") or ""); match=bool(expected and deployment.get("release_marker")==expected); verified=bool(deployment.get("verified",False)) and match
    status="verified" if verified else ("stale" if deployment.get("verified") and not match else deployment.get("status","failed"))
    provenance["deployment"]={"status":status,"verified":verified,"checked_at":deployment.get("checked_at"),"http_status":deployment.get("http_status"),"marker_found":bool(deployment.get("marker_found",False)),"release_marker_found":bool(deployment.get("release_marker_found",False)),"error":deployment.get("error") if match else ("release_identity_mismatch" if deployment.get("verified") else deployment.get("error")),"trend":attribute_deployment_trend(history)}
    artifacts=provenance.setdefault("artifacts",{}); artifacts["deployment_verification_sha256"]=_sha256(deployment_path); artifacts["deployment_history_sha256"]=_sha256(history_path) if history_path.exists() else None; provenance["generated_at"]=datetime.now(timezone.utc).isoformat(); provenance["schema_version"]="release-provenance-v1"; provenance["version"]=1
    provenance_path.write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return provenance

def main():
    p=build_provenance(source_commit=os.environ.get("GITHUB_SHA","unknown"),site_url=os.environ.get("SITE_URL","")); OUTPUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(p,ensure_ascii=False))
if __name__=="__main__": main()
