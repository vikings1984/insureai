#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence and trust layer for InsureAI."""
from __future__ import annotations
import re
from collections import Counter
from urllib.parse import urlparse

def _domain(item):
    try: return urlparse(item.get("source_url") or "").netloc.lower()
    except Exception: return ""

def _text(item):
    return " ".join([str(item.get("title_zh") or item.get("title") or ""), str(item.get("summary_zh") or item.get("summary") or "")]).lower()

def _numbers(item):
    return set(re.findall(r"\b\d+(?:[.,]\d+)?(?:%|m|bn|million|billion|亿|万)?\b", _text(item)))

def _entities(item):
    tags=item.get("tags") or ""
    values={x.strip().lower() for x in tags.split(",") if x.strip()} if isinstance(tags,str) else set()
    values.update(x.lower().strip() for x in re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", str(item.get("title") or "")))
    return {x for x in values if len(x)>=2}

def _pair_similarity(a,b):
    ta,tb=set(_text(a).split()),set(_text(b).split()); ea,eb=_entities(a),_entities(b); na,nb=_numbers(a),_numbers(b)
    token=len(ta&tb)/max(1,len(ta|tb)); entity=len(ea&eb)/max(1,len(ea|eb)) if (ea or eb) else 0.0; number=1.0 if not na or not nb else len(na&nb)/max(1,len(na|nb))
    return round(.45*token+.35*entity+.20*number,3)

def assess(items,event):
    if not items: return {"level":"low","score":0,"source_count":0,"independent_domains":0,"evidence_coverage":0,"agreement":0,"conflict":False,"conflict_fields":[]}
    domains=[_domain(x) for x in items if _domain(x)]; unique_domains=set(domains); verified=sum(1 for x in items if x.get("date_verified") or x.get("published_at")); coverage=round(100*verified/len(items))
    pairs=[]
    for i,a in enumerate(items):
        for b in items[i+1:]:
            if _domain(a)!=_domain(b): pairs.append(_pair_similarity(a,b))
    agreement=round(sum(pairs)/len(pairs)*100) if pairs else (60 if len(items)==1 else 70)
    conflicts=[]; nums=[_numbers(x) for x in items if _numbers(x)]
    if len(nums)>=2 and not set.intersection(*nums): conflicts.append("numeric_facts")
    ents=[e for x in items for e in _entities(x)]; counts=Counter(ents)
    if len(unique_domains)>=2 and sum(1 for _,c in counts.items() if c==1)>=max(2,len(counts)//2): conflicts.append("entities")
    conflict=bool(conflicts); source_score=min(100,45+len(unique_domains)*15); score=round(source_score*.35+coverage*.20+agreement*.35+(10 if event.get("source_count",1)>1 else 0))
    if conflict: score=max(0,score-18)
    level="high" if score>=82 and not conflict else ("medium" if score>=62 else "low")
    return {"level":level,"score":score,"source_count":len(items),"independent_domains":len(unique_domains),"evidence_coverage":coverage,"agreement":agreement,"conflict":conflict,"conflict_fields":conflicts,"reason":"多源一致" if level=="high" and not conflict else ("存在证据冲突" if conflict else "证据有限")}

def summarize_event_trust(items,event):
    trust=assess(items,event); trust["evidence"]=[]
    for item in sorted(items,key=lambda x:x.get("published_at") or "",reverse=True)[:5]:
        trust["evidence"].append({"source_name":item.get("source_name"),"source_url":item.get("source_url"),"domain":_domain(item),"published_at":item.get("published_at"),"date_verified":bool(item.get("date_verified"))})
    return trust
