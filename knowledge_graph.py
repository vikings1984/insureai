#!/usr/bin/env python3
"""Build a dependency-free, provenance-first knowledge graph."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from contract import ARTIFACT_VERSIONS

ROOT = Path(__file__).resolve().parent
INTELLIGENCE = ROOT / "intelligence.json"
CLAIMS = ROOT / "claims.json"
OUTPUT = ROOT / "knowledge_graph.json"

NODE_TYPES = {"Company", "Person", "Product", "Event", "Regulation", "Claim", "Evidence", "Topic"}
REL_TYPES = {"PARTICIPATES_IN", "MENTIONS", "ABOUT", "SUPPORTS", "CONTRADICTS", "EVIDENCES", "RELATED_TO", "GOVERNS", "INVOLVES"}


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def node_id(kind: str, value: str) -> str:
    raw = f"{kind}|{value.strip().lower()}".encode("utf-8")
    return f"kg-{hashlib.sha1(raw).hexdigest()[:16]}"


def add_node(nodes: dict, kind: str, value: str, **attrs) -> str:
    value = (value or "").strip()
    if not value or kind not in NODE_TYPES:
        return ""
    nid = node_id(kind, value)
    row = nodes.setdefault(nid, {"id": nid, "type": kind, "name": value})
    row.update({k: v for k, v in attrs.items() if v not in (None, "", [])})
    return nid


def add_edge(edges: dict, src: str, rel: str, dst: str, evidence_refs=None, confidence=1.0):
    if not src or not dst or rel not in REL_TYPES:
        return
    key = f"{src}|{rel}|{dst}"
    row = edges.setdefault(key, {"source": src, "relationship": rel, "target": dst, "evidence_refs": [], "confidence": round(float(confidence), 4)})
    row["evidence_refs"] = sorted(set(row["evidence_refs"] + list(evidence_refs or [])))
    row["confidence"] = max(row["confidence"], round(float(confidence), 4))


def entities(text: str) -> list[str]:
    values = re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", text or "")
    values += re.findall(r"[\u4e00-\u9fff]{2,12}(?:公司|集团|保险|银行|证券|基金)", text or "")
    out, seen = [], set()
    for x in values:
        x = x.strip()
        if len(x) >= 2 and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out[:12]


def build() -> dict:
    intelligence = load(INTELLIGENCE)
    claims_doc = load(CLAIMS)
    events = intelligence.get("events") or []
    nodes, edges = {}, {}
    evidence_nodes = {}
    event_nodes = {}

    for event in events:
        event_key = event.get("event_id") or event.get("title") or "unknown"
        eid = add_node(nodes, "Event", event_key, title=event.get("title"), topic=event.get("topic"), trust=event.get("trust"), evidence_status=event.get("evidence_status"), source_count=event.get("source_count"), published_at=event.get("published_at"))
        event_nodes[event.get("event_id")] = eid
        tid = add_node(nodes, "Topic", event.get("topic") or "")
        add_edge(edges, eid, "ABOUT", tid, confidence=0.9)
        title = event.get("title") or event.get("summary") or event.get("insight") or ""
        for entity in entities(title):
            kind = "Person" if re.search(r"任命|出任|履新|appoint|appointed", title, re.I) else "Company"
            nid = add_node(nodes, kind, entity)
            add_edge(edges, nid, "PARTICIPATES_IN", eid, evidence_refs=event.get("article_ids") or [], confidence=0.75)
        for ev in event.get("evidence") or []:
            key = ev.get("evidence_id") or ev.get("source_url") or ev.get("source_name")
            ev_id = add_node(nodes, "Evidence", key or "unknown", source_name=ev.get("source_name"), domain=ev.get("domain"), published_at=ev.get("published_at"))
            evidence_nodes[key] = ev_id
            add_edge(edges, ev_id, "EVIDENCES", eid, confidence=1.0)

    for event_group in claims_doc.get("events") or []:
        eid = event_nodes.get(event_group.get("event_id"))
        for claim in event_group.get("claims") or []:
            claim_key = claim.get("claim_id") or f"{event_group.get('event_id')}:{len(nodes)}"
            cid = add_node(nodes, "Claim", claim_key, claim_text=claim.get("claim_text") or claim.get("text"), claim_type=claim.get("claim_type"), verification_status=claim.get("verification_status") or claim.get("status"), confidence=claim.get("confidence"), independent_domains=claim.get("independent_domains"), event_id=event_group.get("event_id"))
            if eid:
                add_edge(edges, cid, "INVOLVES", eid, confidence=0.9)
            for relation, field_name in (("SUPPORTS", "supporting_evidence"), ("CONTRADICTS", "contradicting_evidence")):
                for evidence in claim.get(field_name) or []:
                    ref = evidence.get("evidence_id") or evidence.get("source_url") or evidence.get("source_name")
                    ev_id = evidence_nodes.get(ref) or add_node(nodes, "Evidence", ref or "unknown", source_name=evidence.get("source_name"), domain=evidence.get("domain"), source_tier=evidence.get("source_tier"), published_at=evidence.get("published_at"))
                    evidence_nodes[ref] = ev_id
                    add_edge(edges, ev_id, relation, cid, evidence_refs=[ref], confidence=min(1.0, float(claim.get("confidence", 0) or 0) / 100))
            for entity in [x for x in (claim.get("subject"), claim.get("object")) if x] or claim.get("entities") or entities(claim.get("claim_text") or claim.get("text") or ""):
                nid = add_node(nodes, "Company", entity)
                add_edge(edges, nid, "MENTIONS", cid, confidence=0.8)
            value = claim.get("value") or {}
            if value.get("normalized") is not None:
                pid = add_node(nodes, "Product", f"amount:{value['normalized']}", raw=value.get("raw"), semantic_type="amount_fact")
                add_edge(edges, cid, "RELATED_TO", pid, confidence=0.6)
            if value.get("iso"):
                rid = add_node(nodes, "Regulation", f"date:{value['iso']}", raw=value.get("raw"), semantic_type="date_fact")
                add_edge(edges, cid, "RELATED_TO", rid, confidence=0.6)

    type_counts: dict[str, int] = {}
    for node in nodes.values():
        type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1
    event_dates = sorted(x["published_at"] for x in nodes.values() if x["type"] == "Event" and x.get("published_at"))
    result = {
        "version": ARTIFACT_VERSIONS["knowledge_graph.json"],
        "graph": "insureai_traceable_knowledge_graph",
        "node_types": sorted(NODE_TYPES),
        "relationship_types": sorted(REL_TYPES),
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "event_count": len(events),
            "claim_count": sum(len(x.get("claims") or []) for x in claims_doc.get("events") or []),
            "node_types": dict(sorted(type_counts.items(), key=lambda kv: -kv[1])),
            "latest_event_at": event_dates[-1] if event_dates else "",
        },
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
