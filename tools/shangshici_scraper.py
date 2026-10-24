# -*- coding: utf-8 -*-
"""抓取 赏诗词网(shangshici.com) 典籍全文 -> 本地 HTML 缓存 + 结构化 JSON/Markdown。

阶段 1: 只抓 HTML 缓存 (crawl)
阶段 2: 解析缓存 -> books.json / 生成 md (build)
"""
import os
import re
import json
import time
import html
import urllib.parse
import urllib.request

BASE = "http://www.shangshici.com"
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_BOOK = os.path.join(ROOT, "cache_book")
CACHE_SHOW = os.path.join(ROOT, "cache_show")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


# ---------- 阶段 1: 典籍列表 ----------
def crawl_index():
    books = {}
    for p in range(1, 13):
        h = fetch(f"{BASE}/dianji.asp?p={p}")
        if not h:
            continue
        blocks = re.findall(r'<div class="sons">(.*?)<div style="height:15px', h, re.S)
        for b in blocks:
            m = re.search(r"book\.asp\?ID=(\d+)", b)
            if not m:
                continue
            bid = int(m.group(1))
            t = re.search(r"<b>(.*?)</b>", b, re.S)
            au = re.search(r"作者：(.*?)&nbsp;", b, re.S)
            de = re.search(r'<p id="txt\d+_\d+" style="font-size:12px;">(.*?)</p>', b, re.S)
            books[bid] = {
                "id": bid,
                "title": html.unescape(t.group(1)).strip() if t else "",
                "author": html.unescape(au.group(1)).strip() if au else "",
                "desc": re.sub(r"<.*?>", "", html.unescape(de.group(1))).strip() if de else "",
            }
        if len(blocks) == 0:
            break
    json.dump(books, open(os.path.join(ROOT, "books_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return books


# ---------- 阶段 2: 书籍目录页 ----------
def crawl_book_toc(bid, force=False):
    os.makedirs(CACHE_BOOK, exist_ok=True)
    f = os.path.join(CACHE_BOOK, f"{bid}.html")
    if os.path.exists(f) and not force:
        return open(f, encoding="utf-8").read()
    h = fetch(f"{BASE}/book.asp?ID={bid}")
    if h:
        open(f, "w", encoding="utf-8").write(h)
    return h


def parse_toc(h):
    """返回 [(chapter_id, chapter_title, t_param), ...]"""
    out = []
    seen = set()
    for m in re.finditer(r"bookShow\.asp\?t=([^&']*)&c=([^']*)ID=(\d+)'>([^<]*)</a>", h):
        t, c, cid, ctitle = m.group(1), m.group(2), int(m.group(3)), html.unescape(m.group(4)).strip()
        if cid in seen:
            continue
        seen.add(cid)
        out.append((cid, ctitle, t))
    return out


# ---------- 阶段 3: 章节正文 ----------
def crawl_chapter(bid, cid, t, force=False):
    os.makedirs(CACHE_SHOW, exist_ok=True)
    f = os.path.join(CACHE_SHOW, f"{bid}_{cid}.html")
    if os.path.exists(f) and not force:
        return open(f, encoding="utf-8").read()
    url = f"{BASE}/bookShow.asp?t={urllib.parse.quote(t)}&c=&ID={cid}"
    h = fetch(url)
    if h:
        open(f, "w", encoding="utf-8").write(h)
    return h


def parse_chapter(h):
    """返回 (title, author, [段落...])"""
    if not h:
        return "", "", []
    m = re.search(r'<div class="son1"><h1>(.*?)</h1></div>', h, re.S)
    title = html.unescape(re.sub(r"<.*?>", "", m.group(1))).strip() if m else ""
    m2 = re.search(r'<div class="bookvson2">(.*?)<div class="bookvmiddle"', h, re.S)
    if not m2:
        m2 = re.search(r'<div class="bookvson2">(.*?)</div>', h, re.S)
    if not m2:
        return title, "", []
    body = m2.group(1)
    ma = re.search(r"<span>作者：</span>(.*?)</p>", body, re.S)
    author = html.unescape(re.sub(r"<.*?>", "", ma.group(1))).strip() if ma else ""
    body = body[ma.end():] if ma else body

    def clean(frag):
        txt = re.sub(r"<br\s*/?>", "\n", frag)
        txt = re.sub(r"<.*?>", "", txt)
        txt = html.unescape(txt)
        return txt

    paras = []
    for pm in re.finditer(r"<p[^>]*>(.*?)</p>", body, re.S):
        for line in clean(pm.group(1)).split("\n"):
            line = line.strip().strip("\u3000")
            if line:
                paras.append(line)
    if not paras:  # 裸文本 + <br /> 结构（如《山海经》）
        for line in clean(body).split("\n"):
            line = line.strip().strip("\u3000")
            if line:
                paras.append(line)
    return title, author, paras


def main():
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "crawl"
    books = json.load(open(os.path.join(ROOT, "books_index.json"), encoding="utf-8"))
    if cmd == "crawl":
        stats = []
        t0 = time.time()
        for k in sorted(books, key=lambda x: int(x)):
            bid = int(k)
            h = crawl_book_toc(bid)
            if not h:
                print("TOC FAIL", bid)
                continue
            toc = parse_toc(h)
            ok = 0
            for cid, ctitle, t in toc:
                ch = crawl_chapter(bid, cid, t)
                if ch and '<div class="bookvson2">' in ch:
                    ok += 1
                time.sleep(0.12)
            stats.append({"id": bid, "title": books[k]["title"], "chapters": len(toc), "ok": ok})
            print(f"[{bid:3d}] {books[k]['title']:<12} {ok}/{len(toc)}  ({time.time()-t0:.0f}s)", flush=True)
        json.dump(stats, open(os.path.join(ROOT, "crawl_stats.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    elif cmd == "build":
        build(books)


if __name__ == "__main__":
    main()
