#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Attach evidence/trust signals to intelligence.json without changing source news."""
import json
import os
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
        event.setdefault("insight",{})["trust_reason"]=event["trust"]["reason"]
        event["insight"]["trust_level"]=event["trust"]["level"]
    intel["version"]=4
    levels={"high":0,"medium":0,"low":0}
    conflicts=0
    for e in intel.get("events",[]):
        levels[e.get("trust",{}).get("level","low")]=levels.get(e.get("trust",{}).get("level","low"),0)+1
        conflicts+=1 if e.get("trust",{}).get("conflict") else 0
    intel["trust_stats"]={"high":levels.get("high",0),"medium":levels.get("medium",0),"low":levels.get("low",0),"conflicts":conflicts}
    with open(INTEL+".tmp","w",encoding="utf-8") as f: json.dump(intel,f,ensure_ascii=False,indent=2); f.write("\n")
    os.replace(INTEL+".tmp",INTEL)
    print("Trust layer: %s events, conflicts=%s"%(len(intel.get("events",[])),conflicts))

if __name__=="__main__": main()
