#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI event-based intelligence engine. Deterministic, explainable, no external API."""
import hashlib, json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
OUTPUT_PATH = os.path.join(HERE, "intelligence.json")
TOPIC_LABELS = {"ai_intelligent":"AI智能化","pension_finance":"养老金融","product_innovation":"产品创新","channel_transformation":"渠道变革","capital_reinsurance":"资本与再保险","climate_catastrophe":"气候与巨灾","digital_transformation":"数字化转型","regulatory_change":"监管变革"}
ACTION_WORDS = ["acquire","acquisition","buy","merger","launch","unveil","appoint","regulation","rule","fine","approval","invest","investment","expand","enter","exit","raise","funding","upgrade","downgrade","loss","claim","收购","并购","发布","推出","获批","监管","处罚","投资","扩张","退出","融资","升级","下调","理赔","试点","落地","三审","政策","改革"]
IMPACT_WORDS = ["reinsurance","solvency","capital","catastrophe","cyber","ai","artificial intelligence","regulation","regulator","pension","annuity","insurance","underwriting","premium","再保险","偿付能力","资本","巨灾","网络","人工智能","监管","养老","年金","保险","核保","保费","长期护理","医保","气候"]
PERSONNEL_WORDS = ["appoints","appointed","appointment","names ","joins","出任","任命","履新","就任","加盟"]
STOPWORDS = set("the a an and or of to in on for with from by as at is are was were be this that how what why insurance insurer insurers reinsurance news report reports viewpoint says said new company 保险 行业 新闻 报道 公司 表示 关于 最新 一个 以及 推动 进行".split())

def _norm(text):
    text = (text or "").lower(); text = re.sub(r"https?://\S+", " ", text); return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE).strip()

def _tokens(text):
    return {x for x in _norm(text).split() if len(x) > 1 and x not in STOPWORDS}

def _entities(item):
    entities=[]; tags=item.get("tags") or ""
    if isinstance(tags,str): entities += [x.strip().lower() for x in tags.split(",") if x.strip()]
    title=item.get("title") or ""
    entities += re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}", title)
    entities += re.findall(r"[\u4e00-\u9fff]{2,12}(?:公司|集团|保险|银行|证券|基金|监管局|委员会)", title)
    out=[]; seen=set()
    for e in entities:
        e=e.strip().lower()
        if len(e)>=2 and e not in seen: seen.add(e); out.append(e)
    return out[:12]

def _timestamp(item):
    try: return datetime.fromisoformat((item.get("published_at") or "").replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception: return datetime.min.replace(tzinfo=timezone.utc)

def _event_key(item):
    title=item.get("title_zh") or item.get("title") or ""; core="|".join(sorted(_tokens(title))[:12] + sorted(_entities(item))[:8]) or _norm(title)[:120]
    return hashlib.sha1(core.encode("utf-8")).hexdigest()[:12]

def _similarity(a,b):
    ta,tb=_tokens(a),_tokens(b)
    return len(ta & tb)/max(1,len(ta|tb)) if ta and tb else 0.0

def _cluster(items):
    groups={}; reps=[]
    for item in sorted(items,key=_timestamp,reverse=True):
        key=_event_key(item)
        if key in groups: groups[key].append(item); continue
        title=item.get("title_zh") or item.get("title") or ""; matched=None
        for rep_key,rep_title in reps:
            if _similarity(title,rep_title)>=0.62: matched=rep_key; break
        if matched: groups[matched].append(item)
        else: groups[key]=[item]; reps.append((key,title))
    return groups

def _score(items):
    rows=[]
    for item in items:
        base=float(item.get("ai_score") or 0); text=_norm((item.get("title","")+" "+item.get("summary",""))); topic=item.get("research_topic")
        relevance=min(100,max(0,base+(8 if topic else 0)))
        impact=min(100,48+sum(1 for x in IMPACT_WORDS if x in text)*8+(8 if topic in {"regulatory_change","capital_reinsurance","climate_catastrophe"} else 0))
        actionability=min(100,42+sum(1 for x in ACTION_WORDS if x in text)*7)
        if any(x in text for x in PERSONNEL_WORDS): actionability=min(actionability,42); impact=min(impact,55)
        authority=float(item.get("source_authority") or 70); confidence=min(100,max(40,authority*0.75+(15 if item.get("date_verified") else 0)))
        rows.append((relevance,impact,actionability,confidence))
    relevance=max(x[0] for x in rows); impact=max(x[1] for x in rows); actionability=max(x[2] for x in rows)
    confidence=min(100,sum(x[3] for x in rows)/len(rows)+min(10,(len(items)-1)*3)); novelty=max(55,100-(len(items)-1)*12)
    total=round(relevance*.30+impact*.25+novelty*.15+actionability*.20+confidence*.10)
    return {"relevance":round(relevance),"impact":round(impact),"novelty":round(novelty),"actionability":round(actionability),"confidence":round(confidence),"intelligence_score":total}

def _insight(items,scores):
    lead=max(items,key=lambda x:float(x.get("ai_score") or 0)); title=lead.get("title_zh") or lead.get("title") or ""; summary=lead.get("summary_zh") or lead.get("summary") or ""; topic=TOPIC_LABELS.get(lead.get("research_topic"),"保险行业")
    source_count=len({x.get("source_name") for x in items if x.get("source_name")})
    why=f"该变化已被 {source_count} 个信源独立报道，说明它不只是单一媒体噪声，值得作为行业事件跟踪。" if source_count>1 else (f"它涉及{topic}的关键变化，潜在影响面较大，应关注后续监管、资本、产品或经营层面的连锁反应。" if scores["impact"]>=75 else f"它与{topic}相关，当前更适合作为趋势信号观察，而不是直接视为行业结论。")
    watch="建议继续追踪后续公告、监管文件、市场数据或竞争对手动作，并评估是否需要调整业务判断。" if scores["actionability"]>=70 else "建议观察是否出现第二个独立信源、监管动作或同类公司跟进，以确认趋势是否形成。"
    return {"what_happened":title,"why_it_matters":why,"who_is_affected":topic,"what_to_watch":watch,"evidence":[{"source_name":x.get("source_name"),"source_url":x.get("source_url"),"title":x.get("title_zh") or x.get("title")} for x in sorted(items,key=_timestamp,reverse=True)[:5]],"confidence":scores["confidence"],"summary":summary[:360]}

def build(data):
    news=data.get("news",[]) if isinstance(data,dict) else []; events=[]
    for event_id,items in _cluster(news).items():
        items=sorted(items,key=_timestamp,reverse=True); scores=_score(items); lead=items[0]
        events.append({"event_id":"evt_"+event_id,"title":lead.get("title_zh") or lead.get("title") or "","topic":lead.get("research_topic"),"topic_label":TOPIC_LABELS.get(lead.get("research_topic"),"保险行业"),"published_at":lead.get("published_at"),"source_count":len({x.get("source_name") for x in items if x.get("source_name")}),"article_count":len(items),"article_ids":[x.get("id") for x in items if x.get("id") is not None],"scores":scores,"insight":_insight(items,scores)})
    events.sort(key=lambda x:(x["scores"]["intelligence_score"],x.get("published_at") or ""),reverse=True)
    today=datetime.now(timezone.utc).date().isoformat(); daily=[e for e in events if (e.get("published_at") or "").startswith(today)][:5] or events[:5]
    return {"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"principle":"发现值得行动的变化，而不是堆积更多新闻","events":events,"daily_brief":daily,"stats":{"news_count":len(news),"event_count":len(events),"multi_source_events":sum(1 for e in events if e["source_count"]>1)}}

def main():
    with open(DATA_PATH,encoding="utf-8") as f: data=json.load(f)
    result=build(data); tmp=OUTPUT_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2); f.write("\n")
    os.replace(tmp,OUTPUT_PATH); print(f"Intelligence engine: {result['stats']['news_count']} news -> {result['stats']['event_count']} events; daily brief={len(result['daily_brief'])}")

if __name__=="__main__": main()
