#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO pre-renderer plus stable release marker for deployment verification."""
from __future__ import annotations

import argparse
import datetime
import email.utils
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
INDEX = os.path.join(HERE, "index.html")
DEFAULT_SITE = "https://vikings1984.github.io/insureai"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def load_data():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def load_release_marker():
    path = os.path.join(HERE, "release_manifest.json")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    return str(manifest.get("release_marker") or "")


def build_jsonld(data, site_url):
    news = data.get("news", [])[:12]
    item_list = {"@context":"https://schema.org","@type":"ItemList","name":"InsureAI 保险行业精选资讯","itemListElement":[{"@type":"ListItem","position":i+1,"item":{"@type":"NewsArticle","headline":n.get("title",""),"url":f"{site_url}/#/news/{n.get('id')}","datePublished":n.get("published_at",""),"articleSection":n.get("category",""),"author":{"@type":"Organization","name":n.get("source_name","")}}} for i,n in enumerate(news)]}
    website = {"@context":"https://schema.org","@type":"WebSite","name":"InsureAI","url":site_url,"description":"保险行业动态资讯聚合平台：每日精选监管政策、产品发布、行业动态、研究洞察与理赔案例。","potentialAction":{"@type":"SearchAction","target":f"{site_url}/#/search?q={{search_term_string}}","query-input":"required name=search_term_string"}}
    return [website, item_list]


def build_fallback(data, site_url):
    items=[]
    for n in data.get("news",[])[:12]:
        title=esc(n.get("title","")); summary=esc(n.get("summary","")[:120]); src=esc(n.get("source_name","")); url=f"{site_url}/#/news/{n.get('id')}"
        items.append(f'<li><a href="{url}">{title}</a> — {src}<br>{summary}</li>')
    return '<div id="seo-fallback" aria-hidden="true" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);"><h1>InsureAI 保险行业动态资讯</h1><ul>'+''.join(items)+'</ul></div>'


def build_sitemap(data, site_url):
    pages=["","#/all","#/daily","#/research","#/submit","#/about","#/log","#/feedback"]
    urls=[f"  <url><loc>{site_url}/{p}</loc></url>" for p in pages]
    for n in data.get("news",[]): urls.append(f"  <url><loc>{site_url}/#/news/{n.get('id')}</loc></url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"\n".join(urls)+'\n</urlset>\n'


def _rfc822(pub):
    if not pub: return ""
    try: return email.utils.formatdate(datetime.datetime.fromisoformat(pub.replace("Z","+00:00")).timestamp(), usegmt=True)
    except Exception: return ""


def build_rss(data, site_url):
    items=[]
    for n in data.get("news",[]):
        title=esc(n.get("title","")); summary=esc(n.get("summary","") or ""); src=esc(n.get("source_name","") or ""); url=n.get("source_url") or f"{site_url}/#/news/{n.get('id')}"
        items.append(f'    <item>\n      <title>{title}</title>\n      <link>{esc(url)}</link>\n      <guid isPermaLink="false">{esc(url)}</guid>\n      <description>{summary}</description>\n      <source>{src}</source>\n      <pubDate>{_rfc822(n.get("published_at"))}</pubDate>\n    </item>')
    return '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n    <title>InsureAI 保险行业动态资讯</title>\n    <link>'+site_url+'/</link>\n    <description>保险从业者每日必看的行业资讯过滤器：AI 评分精选、研究主题标签、权威报告徽章。</description>\n    <language>zh-CN</language>\n'+"\n".join(items)+'\n  </channel>\n</rss>\n'


def inject(tag_start, tag_end, content):
    with open(INDEX,encoding="utf-8") as f: txt=f.read()
    pat=re.compile(re.escape(tag_start)+".*?"+re.escape(tag_end),re.S)
    if not pat.search(txt): raise SystemExit(f"未找到占位标记: {tag_start} ... {tag_end}")
    with open(INDEX,"w",encoding="utf-8") as f: f.write(pat.sub(tag_start+content+tag_end,txt))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--site-url",default=os.environ.get("SITE_URL",DEFAULT_SITE)); ap.add_argument("--out",default=HERE); args=ap.parse_args(); site_url=args.site_url.rstrip("/"); data=load_data()
    blocks=build_jsonld(data,site_url); inject("<!--SEO_JSONLD_START-->","<!--SEO_JSONLD_END-->","\n".join(f'<script type="application/ld+json">{json.dumps(b,ensure_ascii=False)}</script>' for b in blocks))
    inject("<!--SEO_FALLBACK_START-->","<!--SEO_FALLBACK_END-->",build_fallback(data,site_url))
    marker=load_release_marker()
    marker_html=f'<meta name="insureai-release-marker" content="{esc(marker)}">' if marker else '<meta name="insureai-release-marker" content="">'
    if "<!--INSUREAI_RELEASE_MARKER_START-->" in open(INDEX,encoding="utf-8").read():
        inject("<!--INSUREAI_RELEASE_MARKER_START-->","<!--INSUREAI_RELEASE_MARKER_END-->",marker_html)
    else:
        with open(INDEX,"a",encoding="utf-8") as f: f.write("\n<!--INSUREAI_RELEASE_MARKER_START-->"+marker_html+"<!--INSUREAI_RELEASE_MARKER_END-->\n")
    with open(os.path.join(args.out,"sitemap.xml"),"w",encoding="utf-8") as f: f.write(build_sitemap(data,site_url))
    with open(os.path.join(args.out,"rss.xml"),"w",encoding="utf-8") as f: f.write(build_rss(data,site_url))
    print(f"✅ SEO 预渲染完成（站点: {site_url}，release_marker={marker or 'missing'}）")


if __name__=="__main__": main()
