#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate.py — 英文资讯免费翻译为中文（零依赖，仅标准库）
=============================================================
目标：英文源（RSS）的标题/摘要自动翻译为中文，前端以中文为主展示。

免费方案（双端点回退，均无需 API key）：
  1) Google translate gtx 端点：质量最好、无每日配额；CI（GitHub Actions，海外网络）首选。
     本地（国内网络）通常超时 → 自动回退 2)。
  2) MyMemory API：国内可达，匿名每日约 5000 字符配额，作为回退。

缓存：data/translation_cache.json 以 sha1(原文) 为键持久化，避免 CI 每日
重跑时重复翻译同一批标题（缓存随仓库提交，增量累计）。

容错：翻译失败静默跳过（保留英文原文），绝不阻塞采集主流程。
限流：请求间 sleep，单次运行翻译预算（条数）有限，存量英文随每日 CI 增量消化。

用法（被 collect.py 调用）：
    from translate import translate_news
    translated = translate_news(merged_news, budget=40)
"""

import hashlib
import json
import os
import time
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "data", "translation_cache.json")
TIMEOUT = 8
MAX_TEXT_LEN = 250          # 翻译前截断（摘要过长无意义且耗时）
REQUEST_INTERVAL = 0.3      # 端点限流间隔（秒）

UA = "Mozilla/5.0 (compatible; InsureAIBot/1.0; +https://github.com/vikings1984/insureai)"


# ===================== 语言检测 =====================
def is_english(text):
    """启发式判断：ASCII 字母占比 > 0.6 视为英文（标题场景足够可靠）。"""
    t = (text or "").strip()
    if len(t) < 8:
        return False
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return False
    ascii_letters = [c for c in letters if ord(c) < 128]
    return len(ascii_letters) / len(letters) > 0.6


# ===================== 端点 1：Google gtx（CI 首选） =====================
def _parse_gtx(data):
    """gtx 响应为嵌套数组：[[['译文片段', '原文片段', ...], ...], ...]，拼接所有译文片段。"""
    if not data or not isinstance(data, list) or not data[0]:
        return ""
    parts = [seg[0] for seg in data[0] if isinstance(seg, list) and seg and seg[0]]
    return "".join(parts).strip()


def _gtx_translate(text):
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=gtx&sl=en&tl=zh-CN&dt=t&q=" + urllib.parse.quote(text[:MAX_TEXT_LEN]))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8", "ignore")
    return _parse_gtx(json.loads(raw))


# ===================== 端点 2：MyMemory（国内回退） =====================
def _parse_mymemory(data):
    if not isinstance(data, dict):
        return ""
    t = (data.get("responseData") or {}).get("translatedText", "")
    # 配额/异常时返回的错误说明文本不作为译文
    if not t or "MYMEMORY WARNING" in t or "INVALID LANGUAGE PAIR" in t.upper():
        return ""
    return t.strip()


def _mymemory_translate(text):
    url = ("https://api.mymemory.translated.net/get?q="
           + urllib.parse.quote(text[:MAX_TEXT_LEN]) + "&langpair=en|zh-CN")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8", "ignore")
    return _parse_mymemory(json.loads(raw))


# ===================== 主入口：带缓存的单条翻译 =====================
def _looks_translated(src, dst):
    """译文必须非空、非原样照抄、且中文占比达标（防端点返回错误说明文本）。"""
    if not dst:
        return False
    if dst.strip() == src.strip():
        return False
    cjk = sum(1 for c in dst if '\u4e00' <= c <= '\u9fff')
    return cjk / max(len(dst), 1) >= 0.25


def translate_en2zh(text, cache=None):
    """单条翻译（带缓存）。返回译文；失败返回空串。cache 为 dict 时读写缓存。"""
    src = (text or "").strip()
    if not src:
        return ""
    key = hashlib.sha1(src.encode("utf-8")).hexdigest()
    if cache is not None and key in cache:
        return cache[key]

    result = ""
    for fn in (_gtx_translate, _mymemory_translate):
        try:
            out = fn(src)
            if _looks_translated(src, out):
                result = out
                break
        except Exception:
            continue
        finally:
            time.sleep(REQUEST_INTERVAL)

    if result and cache is not None:
        cache[key] = result
    return result


# ===================== 缓存持久化 =====================
def load_cache(path=None):
    path = path or CACHE_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache, path=None):
    path = path or CACHE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)


# ===================== 批量：新闻条目翻译 =====================
def translate_news(news_list, budget=40, cache=None, verbose=True):
    """为英文条目补充 title_zh / summary_zh（原地修改，返回翻译条数）。

    预算控制单次运行的 API 调用量（标题优先于摘要）；缓存命中的不计入预算。
    """
    own_cache = cache is None
    cache = load_cache() if own_cache else cache
    translated = 0

    pending = [n for n in news_list
               if is_english(n.get("title", "")) and not n.get("title_zh")]
    for n in pending:
        if translated >= budget:
            break
        t = translate_en2zh(n["title"], cache)
        if t:
            n["title_zh"] = t
            translated += 1

    # 标题翻译完且预算尚有余量 → 摘要（截断后翻译，前端同样截断展示）
    pending_sum = [n for n in news_list
                   if n.get("title_zh") and not n.get("summary_zh")
                   and is_english(n.get("summary", ""))]
    for n in pending_sum:
        if translated >= budget:
            break
        s = translate_en2zh(n["summary"], cache)
        if s:
            n["summary_zh"] = s
            translated += 1

    if own_cache and translated:
        try:
            save_cache(cache)
        except Exception as e:
            if verbose:
                print(f"  ⚠ 翻译缓存写入失败: {e}")
    if verbose and translated:
        print(f"  🌐 英译中: 本次翻译 {translated} 条（缓存 {len(cache)} 条）")
    return translated


if __name__ == "__main__":
    # 独立运行：翻译 data.json 中未翻译的英文条目（调试用）
    import collect
    data = collect.load_existing()
    n = translate_news(data.get("news", []), budget=10)
    if n:
        with open(collect.DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写回 data.json（{n} 条新增翻译）")
    else:
        print("（无新翻译）")
