#!/usr/bin/env python3
"""Build a dependency-free, provenance-first knowledge graph."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
INTELLIGENCE = ROOT / "intelligence.json"
CLAIMS = ROOT / "claims.json"
OUTPUT = ROOT / "knowledge_graph.json"

NODE_TYPES = {"Company", "Person", "Product", "Event", "Regulation", "Claim", "Evidence", "Topic"}
REL_TYPES = {"PARTICIPATES_IN", "MENTIONS", "ABOUT", "SUPPORTS", "EVIDENCES", "RELATED_TO", "GOVERNS", "INVOLVES"}


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


def domain(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""


def build() -> dict:
    intelligence = load(INTELLIGENCE)
    claims_doc = load(CLAIMS)
    events = intelligence.get("events") or []
    claims = claims_doc.get("claims") or []
    nodes, edges = {}, {}
    event_claim_map = {}
    evidence_nodes = {}

    for event in events:
        eid = add_node(nodes, "Event", event.get("event_id") or event.get("title") or "unknown", title=event.get("title"), topic=event.get("topic"), trust=event.get("trust"), evidence_status=event.get("evidence_status"), source_count=event.get("source_count"))
        topic = event.get("topic")
        tid = add_node(nodes, "Topic", topic or "")
        add_edge(edges, eid, "ABOUT", tid, confidence=0.9)
        title = event.get("title") or event.get("summary") or event.get("insight") or ""
        for entity in entities(title):
            kind = "Person" if re.search(r"任命|出任|履新|appoint|appointed", title, re.I) else "Company"
            nid = add_node(nodes, kind, entity)
            add_edge(edges, nid, "PARTICIPATES_IN", eid, evidence_refs=event.get("article_ids") or [], confidence=0.75)
        for ev in (event.get("evidence") or []):
            ev_id = add_node(nodes, "Evidence", ev.get("source_url") or ev.get("source_name") or "unknown", source_name=ev.get("source_name"), domain=ev.get("domain"), published_at=ev.get("published_at"))
            evidence_nodes[ev.get("evidence_id") or ev.get("source_url")] = ev_id
            add_edge(edges, ev_id, "EVIDENCES", eid, confidence=1.0)

    for claim in claims:
        cid = add_node(nodes, "Claim", claim.get("claim_id") or claim.get("text") or "unknown", text=claim.get("text"), status=claim.get("status"), confidence=claim.get("confidence"), independent_domains=claim.get("independent_domains"))
        for ref in claim.get("evidence_refs") or []:
            ev_id = evidence_nodes.get(ref)
            if not ev_id:
                evidence = next((x for x in claim.get("evidence") or [] if x.get("evidence_id") == ref), None)
                ev_id = add_node(nodes, "Evidence", (evidence or {}).get("source_url") or ref, source_name=(evidence or {}).get("source_name"), domain=(evidence or {}).get("domain"))
                evidence_nodes[ref] = ev_id
            add_edge(edges, ev_id, "SUPPORTS", cid, evidence_refs=[ref], confidence=min(1.0, float(claim.get("confidence", 0) or 0) / 100))
        text = claim.get("text") or ""
        for entity in claim.get("entities") or entities(text):
            nid = add_node(nodes, "Company", entity)
            add_edge(edges, nid, "MENTIONS", cid, confidence=0.8)
        event_id = claim.get("event_id")
        if event_id:
            add_edge(edges, cid, "INVOLVES", node_id("Event", event_id), confidence=0.9)

    result = {
        "version": 1,
        "graph": "insureai_traceable_knowledge_graph",
        "node_types": sorted(NODE_TYPES),
        "relationship_types": sorted(REL_TYPES),
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "stats": {"node_count": len(nodes), "edge_count": len(edges), "event_count": len(events), "claim_count": len(claims)},
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
