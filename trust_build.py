#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Attach trust and claim-level evidence to intelligence.json."""
import json
import os
from claims import build_claims
from trust import summarize_event_trust

HERE=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.join(HERE,"data.json")
INTEL=os.path.join(HERE,"intelligence.json")

def main():
    data=json.load(open(DATA,encoding="utf-8"))
    intel=json.load(open(INTEL,encoding="utf-8"))
    news_by_id={str(x.get("id")):x for x in data.get("news",[])}
    for event in intel.get("events",[]):
        items=[news_by_id[str(i)] for i in event.get("article_ids",[]) if str(i) in news_by_id]
        event["trust"]=summarize_event_trust(items,event)
        event["claims"]=build_claims(items,event)
        event.setdefault("insight",{})["trust_reason"]=event["trust"]["reason"]
        event["insight"]["trust_level"]=event["trust"]["level"]
        event["insight"]["claim_coverage"]=event["claims"]["coverage"]
    intel["version"]=5
    levels={"high":0,"medium":0,"low":0}
    conflicts=0
    claims_total=0
    claims_cross_checked=0
    claims_conflicted=0
    for e in intel.get("events",[]):
        level=e.get("trust",{}).get("level","low")
        levels[level]=levels.get(level,0)+1
        conflicts += 1 if e.get("trust",{}).get("conflict") else 0
        c=e.get("claims",{})
        claims_total += len(c.get("claims",[]))
        claims_cross_checked += int(c.get("cross_checked",0))
        claims_conflicted += int(c.get("conflicted",0))
    intel["trust_stats"]={"high":levels.get("high",0),"medium":levels.get("medium",0),"low":levels.get("low",0),"conflicts":conflicts}
    intel["claim_stats"]={"claims":claims_total,"cross_checked":claims_cross_checked,"conflicted":claims_conflicted,"coverage":round(100*claims_cross_checked/claims_total) if claims_total else 0}
    with open(INTEL+".tmp","w",encoding="utf-8") as f: json.dump(intel,f,ensure_ascii=False,indent=2); f.write("\n")
    os.replace(INTEL+".tmp",INTEL)
    print("Trust + claims: %s events, conflicts=%s, claims=%s"%(len(intel.get("events",[])),conflicts,claims_total))

if __name__=="__main__": main()
