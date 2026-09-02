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


# 句首状语 / 功能词：作为大写短语的「首词」且位于句首时，几乎都是标题片段而非机构名
# （如 "According to…"、"The report said…"、"Sources said…"）。机构名极少以这些词引领，
# 故在句首位置时直接丢弃；句中出现的同名（如 "… The Hartford 发布…"）仍保留。
EN_ADVERB_TOKENS = {
    "According", "Sources", "Source", "Report", "Reports", "Said", "The", "A", "An",
    "As", "In", "On", "For", "With", "To", "From", "By", "At", "Of", "After", "Before",
    "When", "While", "If", "But", "And", "Or", "This", "That", "These", "Those",
    "It", "Its", "They", "Their", "We", "Our", "You", "Your", "Not", "No", "Yes",
}
# 机构名长度上限：超出即大概率是拼接的长句片段，而非实体
MAX_ENTITY_CHARS = 40
# 中文机构名前的状语/介词/将来时前缀：递归剥离后若仍含机构后缀才算有效实体
# （"随着再保险公司" → "再保险公司"；"在X银行" → "X银行"；"将收购保险服务公司" → "保险服务公司"）
CN_ADVERB_PREFIXES = (
    "随着", "在", "对于", "关于", "通过", "由于", "基于", "面对", "从", "为",
    "当", "经", "由", "受", "被", "据", "按", "依", "就", "因", "因应",
    "将", "收购", "支持", "加快", "推进", "人工智能在",
)
# 句中动词粒子：标题常为「主体 + 动词 + 机构名」的从句片段（如「摩根大通表示再保险」），
# 切分后保留以机构后缀结尾的最右片段（"再保险"），去掉从句与品牌前的动词。
# 仅用于含明确动词粒子的候选；真实机构名（慕尼黑再保险、瑞士再保险）不含这些粒子，不受影响。
CN_VERB_PARTICLES = (
    "表示", "称", "宣布", "预计", "认为", "计划", "拟", "寻求", "推动", "面临",
    "指出", "透露", "提及", "称其", "据悉", "日前", "近日",
)
_CN_SUFFIX = re.compile(r"(公司|集团|保险|银行|证券|基金)$")


def _clean_cn_entity(x: str) -> str | None:
    """中文机构名噪声治理：递归剥离句首状语前缀，再从句中动词粒子处切分保留机构尾片。

    返回 None 表示剥离/切分后不再是机构名（如纯状语「随着市场」、纯动词从句）。
    """
    stripped = x
    # 1) 递归剥离句首状语/介词前缀
    changed = True
    while changed:
        changed = False
        for p in CN_ADVERB_PREFIXES:
            if stripped.startswith(p):
                stripped = stripped[len(p):]
                changed = True
                break
    # 2) 句中动词粒子切分：保留以机构后缀结尾的最右片段
    for v in CN_VERB_PARTICLES:
        idx = stripped.find(v)
        if idx != -1:
            tail = stripped[idx + len(v):]
            if _CN_SUFFIX.search(tail) and len(tail) >= 2:
                stripped = tail
                break
    if len(stripped) < 2:
        return None
    if not _CN_SUFFIX.search(stripped):
        return None
    return stripped


def entities(text: str) -> list[str]:
    text = text or ""
    out, seen = [], set()
    # 英文：句首且首词为功能词/状语的片段丢弃；限制长度
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", text):
        x = m.group(0).strip()
        if m.start() == 0 and x.split()[0] in EN_ADVERB_TOKENS:
            continue
        if len(x) > MAX_ENTITY_CHARS:
            continue
        if len(x) >= 2 and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    # 中文：剥离句首状语前缀后复查机构后缀
    for x in re.findall(r"[\u4e00-\u9fff]{2,12}(?:公司|集团|保险|银行|证券|基金)", text):
        x = x.strip()
        cleaned = _clean_cn_entity(x)
        if not cleaned or len(cleaned) > MAX_ENTITY_CHARS:
            continue
        if cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
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
