#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prerender.py — InsureAI 纯静态 SPA 的 SEO 预渲染器（零依赖）

读取 data.json，为搜索引擎/爬虫生成可抓取的静态内容：
  1. JSON-LD（WebSite + ItemList）注入 index.html 的 <!--SEO_JSONLD_START/END-->
  2. 首屏资讯静态列表（隐藏 div）注入 <!--SEO_FALLBACK_START/END-->
  3. sitemap.xml（全部页面路由 + 全部资讯深链）
  4. rss.xml（由 data.json 生成的 RSS 2.0 订阅源）

本工具不依赖任何第三方库，仅使用 Python 标准库。

用法：
    python3 prerender.py [--site-url URL] [--out DIR]
环境变量：
    SITE_URL  站点正式域名（默认 GitHub Pages 地址）
"""
import json
import re
import html
import os
import sys
import argparse
import datetime
import email.utils

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
INDEX = os.path.join(HERE, "index.html")
DEFAULT_SITE = "https://vikings1984.github.io/insureai"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def load_data():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def build_jsonld(data, site_url):
    news = data.get("news", [])[:12]
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "InsureAI 保险行业精选资讯",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "item": {
                    "@type": "NewsArticle",
                    "headline": n.get("title", ""),
                    "url": f"{site_url}/#/news/{n.get('id')}",
                    "datePublished": n.get("published_at", ""),
                    "articleSection": n.get("category", ""),
                    "author": {"@type": "Organization", "name": n.get("source_name", "")},
                },
            }
            for i, n in enumerate(news)
        ],
    }
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "InsureAI",
        "url": site_url,
        "description": "保险行业动态资讯聚合平台：每日精选监管政策、产品发布、行业动态、研究洞察与理赔案例。",
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{site_url}/#/search?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }
    return [website, item_list]


def build_fallback(data, site_url):
    news = data.get("news", [])[:12]
    items = []
    for n in news:
        title = esc(n.get("title", ""))
        summary = esc(n.get("summary", "")[:120])
        src = esc(n.get("source_name", ""))
        url = f"{site_url}/#/news/{n.get('id')}"
        items.append(
            f'<li><a href="{url}">{title}</a> — {src}<br>{summary}</li>'
        )
    return (
        '<div id="seo-fallback" aria-hidden="true" '
        'style="position:absolute;width:1px;height:1px;overflow:hidden;'
        'clip:rect(0 0 0 0);">'
        "<h1>InsureAI 保险行业动态资讯</h1>"
        f'<ul>{"".join(items)}</ul></div>'
    )


def build_sitemap(data, site_url):
    # 修正：移除不存在的 #/sources；#/changelog 实际路由为 #/log；补充 #/research、#/submit
    pages = ["", "#/all", "#/daily", "#/research", "#/submit", "#/about", "#/log", "#/feedback"]
    urls = [f"  <url><loc>{site_url}/{p}</loc></url>" for p in pages]
    # 收录全部资讯深链（不再截断 50）
    for n in data.get("news", []):
        urls.append(f"  <url><loc>{site_url}/#/news/{n.get('id')}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def _rfc822(pub):
    if not pub:
        return ""
    s = pub.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except Exception:
        return ""
    return email.utils.formatdate(dt.timestamp(), usegmt=True)


def build_rss(data, site_url):
    items = []
    for n in data.get("news", []):
        title = esc(n.get("title", ""))
        summary = esc(n.get("summary", "") or "")
        src = esc(n.get("source_name", "") or "")
        url = n.get("source_url") or f"{site_url}/#/news/{n.get('id')}"
        items.append(
            "    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{esc(url)}</link>\n"
            f"      <guid isPermaLink=\"false\">{esc(url)}</guid>\n"
            f"      <description>{summary}</description>\n"
            f"      <source>{src}</source>\n"
            f"      <pubDate>{_rfc822(n.get('published_at'))}</pubDate>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        "    <title>InsureAI 保险行业动态资讯</title>\n"
        f"    <link>{site_url}/</link>\n"
        "    <description>保险从业者每日必看的行业资讯过滤器：AI 评分精选、研究主题标签、权威报告徽章。</description>\n"
        "    <language>zh-CN</language>\n"
        + "\n".join(items)
        + "\n  </channel>\n"
        "</rss>\n"
    )


def inject(tag_start, tag_end, content):
    with open(INDEX, encoding="utf-8") as f:
        txt = f.read()
    pat = re.compile(re.escape(tag_start) + ".*?" + re.escape(tag_end), re.S)
    if not pat.search(txt):
        raise SystemExit(f"未找到占位标记: {tag_start} ... {tag_end}")
    new = pat.sub(tag_start + content + tag_end, txt)
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", DEFAULT_SITE))
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()

    site_url = args.site_url.rstrip("/")
    data = load_data()

    # 1. JSON-LD
    blocks = build_jsonld(data, site_url)
    jsonld = "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in blocks
    )
    inject("<!--SEO_JSONLD_START-->", "<!--SEO_JSONLD_END-->", jsonld)

    # 2. 首屏静态列表（隐藏 div，供爬虫抓取）
    fallback = build_fallback(data, site_url)
    inject("<!--SEO_FALLBACK_START-->", "<!--SEO_FALLBACK_END-->", fallback)

    # 3. sitemap.xml
    sitemap_path = os.path.join(args.out, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(build_sitemap(data, site_url))

    # 4. rss.xml（由 data.json 生成，供 RSS 阅读器订阅）
    rss_path = os.path.join(args.out, "rss.xml")
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(build_rss(data, site_url))

    print(f"✅ SEO 预渲染完成（站点: {site_url}）")
    print(f"   - JSON-LD 块: {len(blocks)}")
    print(f"   - 首屏静态列表: {len(data.get('news', [])[:12])} 条")
    print(f"   - sitemap.xml: {sitemap_path}")
    print(f"   - rss.xml: {rss_path}（{len(data.get('news', []))} 条）")


if __name__ == "__main__":
    main()
