# -*- coding: utf-8 -*-
"""古文岛 gushiwen.cn《古籍》+《名句》抓取器（带全局限速与 512 退避）。

分阶段抓取，全部落盘 HTML 缓存，可断点续跑：
  index     /guwen/default.aspx?p=N                     古籍列表
  book      /guwen/book_<hash>.aspx                     书目（含章节清单）
  chapter   /guwen/bookv_<hash>.aspx                    章节正文
  mjpage    /mingjus/default.aspx?page=N&tstr=<书名>     名句列表（分页）
  juv       /mingju/juv_<hash>.aspx                     名句详情（摘自/译文/注释/赏析）

用法：
  python gushiwen_scraper.py index|books|chapters|mingju [workers]
"""
import os
import re
import sys
import json
import time
import random
import threading
import html as H
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "https://www.gushiwen.cn"
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "gw_cache")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_local = threading.local()
_lock = threading.Lock()
_last = [0.0]
MIN_GAP = 0.85          # 全局最小请求间隔（秒）→ 约 1 req/s，礼貌抓取，避免被判为爬虫
JITTER = 0.4            # 额外随机抖动上限（秒）
STATS = {"ok": 0, "cache": 0, "fail": 0, "block": 0}


def sess():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": BASE + "/guwen/",
        })
        _local.s = s
    return s


def throttle():
    with _lock:
        now = time.time()
        wait = _last[0] + MIN_GAP + random.random() * JITTER - now
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def cache_path(kind, key):
    d = os.path.join(CACHE, kind)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key + ".html")


def fetch(url, kind, key, retries=8):
    p = cache_path(kind, key)
    if os.path.exists(p):
        with _lock:
            STATS["cache"] += 1
        return open(p, encoding="utf-8", errors="replace").read()
    for i in range(retries):
        throttle()
        try:
            r = sess().get(url, timeout=25)
            if r.status_code == 200 and len(r.text) > 1500:
                open(p, "w", encoding="utf-8").write(r.text)
                with _lock:
                    STATS["ok"] += 1
                return r.text
            if r.status_code in (512, 403, 429):
                with _lock:
                    STATS["block"] += 1
                time.sleep(2.5 * (i + 1) + random.random())
                continue
            time.sleep(0.6 * (i + 1))
        except Exception:
            time.sleep(0.8 * (i + 1))
    with _lock:
        STATS["fail"] += 1
    return None


# ---------------- 解析 ----------------
def parse_index(h):
    out = []
    for blk in re.split(r'<div class="sonspic">', h)[1:]:
        blk = blk.split('<div class="tool">')[0]
        m = re.search(r'href="/guwen/book_([0-9a-f]+)\.aspx"[^>]*><b>([^<]+)</b>', blk)
        if not m:
            continue
        tags = re.findall(r'<div class="book-tag"><span>([^<]*)</span>', blk)
        mj = re.search(r'href="(/mingjus/default\.aspx\?tstr=[^"]+)"[^>]*>(\d+)条名句', blk)
        ps = re.findall(r'<p style="margin:0px;">(.*?)</p>', blk, re.S)
        out.append({
            "hash": m.group(1), "title": H.unescape(m.group(2)).strip(),
            "author": tags[0] if tags else "", "dynasty": tags[1] if len(tags) > 1 else "",
            "cat": tags[2] if len(tags) > 2 else "",
            "mingjuCount": int(mj.group(2)) if mj else 0,
            "mingjuUrl": H.unescape(mj.group(1)) if mj else "",
            "desc": H.unescape(re.sub(r"<.*?>", "", ps[0])).strip() if ps else "",
        })
    return out


def page_has_next(h, param="p"):
    return "下一页" in h and re.search(r'class="amore"\s+href="[^"]*[?&]' + param + r'=\d+', h)


def parse_book(h):
    author = dynasty = cat = desc = ""
    m = re.search(r'<div class="book-tag book-tag-mingju">.*?</div>(.*?)</p>', h, re.S)
    if m:
        tags = re.findall(r'<div class="book-tag"><span>([^<]*)</span>', m.group(1))
        author = tags[0] if tags else ""
        dynasty = tags[1] if len(tags) > 1 else ""
        cat = tags[2] if len(tags) > 2 else ""
    d = re.search(r'<p style="margin-top:20px;font-size:16px;color:#0F0F0F;">(.*?)</p>', h, re.S)
    if d:
        desc = H.unescape(re.sub(r"<.*?>", "", d.group(1))).strip()
    chaps, seen = [], set()
    for mm in re.finditer(r'href="/guwen/bookv_([0-9a-f]+)\.aspx"[^>]*>([^<]{1,60})</a>', h):
        if mm.group(1) in seen:
            continue
        seen.add(mm.group(1))
        chaps.append((mm.group(1), H.unescape(mm.group(2)).strip()))
    total = re.search(r"共(\d+)章", h)
    return author, dynasty, cat, desc, chaps, (int(total.group(1)) if total else len(chaps))


def parse_chapter(h):
    title = ""
    m = re.search(r'<h1[^>]*>\s*<span[^>]*><b>([^<]*)</b>', h)
    if m:
        title = H.unescape(m.group(1)).strip()
    if not title:
        m = re.search(r'<title>([^_<]+)', h)
        title = H.unescape(m.group(1)).strip() if m else ""
    paras = []
    m2 = re.search(r'<div class="contson"[^>]*>(.*?)</div>', h, re.S)
    if m2:
        body = re.sub(r"<br\s*/?>", "\n", m2.group(1))
        body = re.sub(r"</p>", "\n", body)
        body = re.sub(r"<.*?>", "", body)
        for line in H.unescape(body).split("\n"):
            line = line.strip().strip("\u3000").strip()
            if line:
                paras.append(line)
    return title, paras


def parse_mingju_list(h):
    out = []
    for blk in re.split(r'<div class="cont" style="margin-top: ?20px', h)[1:]:
        m = re.search(r'href="/mingju/juv_([0-9a-f]+)\.aspx">([^<]+)</a>', blk)
        fm = re.search(r'href="/guwen/bookv_([0-9a-f]+)\.aspx">([^<]+)</a>', blk)
        if m:
            out.append({"juv": m.group(1), "text": H.unescape(m.group(2)).strip(),
                        "fromHash": fm.group(1) if fm else "",
                        "fromText": H.unescape(fm.group(2)).strip() if fm else ""})
    return out


def parse_juv(h):
    m = re.search(r'id="sonsyuanwen".*?<h1[^>]*>(.*?)</h1>', h, re.S)
    text = H.unescape(re.sub(r"<.*?>", "", m.group(1))).strip() if m else ""
    fm = re.search(r'摘自《<a href="/guwen/bookv_([0-9a-f]+)\.aspx">(.*?)</a>》', h, re.S)
    d = {"text": text, "fromHash": fm.group(1) if fm else "",
         "from": H.unescape(fm.group(2)).strip() if fm else "",
         "译文": "", "注释": "", "赏析": ""}
    body = re.search(r'<div class="contson"[^>]*>(.*?)</div>', h, re.S)
    if body:
        cur, buf = None, {}
        for pm in re.finditer(r"<p>(.*?)</p>", body.group(1), re.S):
            raw = pm.group(1)
            km = re.search(r'<span class="yzsSpan">([^<]+)</span>', raw)
            txt = H.unescape(re.sub(r"<.*?>", "", raw)).strip()
            if km:
                cur = km.group(1)
                buf[cur] = [txt.replace(cur, "", 1).strip()]
            elif cur:
                buf[cur].append(txt)
        for k in ("译文", "注释", "赏析"):
            d[k] = "\n".join(x for x in buf.get(k, []) if x).strip()
    return d


# ---------------- 阶段 ----------------
def stage_index():
    books, page = [], 1
    while page <= 60:
        h = fetch(f"{BASE}/guwen/default.aspx?p={page}", "index", f"p{page}")
        if not h:
            print("fail p", page)
            break
        rows = parse_index(h)
        if not rows:
            break
        books += rows
        if not page_has_next(h):
            break
        page += 1
    seen, uniq = set(), []
    for b in books:
        if b["hash"] not in seen:
            seen.add(b["hash"])
            uniq.append(b)
    json.dump(uniq, open(os.path.join(ROOT, "gw_books.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"BOOKS {len(uniq)} 名句合计 {sum(b['mingjuCount'] for b in uniq)}")


def stage_books(workers=3):
    books = json.load(open(os.path.join(ROOT, "gw_books.json"), encoding="utf-8"))

    def one(b):
        h = fetch(f"{BASE}/guwen/book_{b['hash']}.aspx", "book", b["hash"])
        if not h:
            return None
        a, d, c, desc, chaps, total = parse_book(h)
        b2 = dict(b)
        b2.update({"author": a or b["author"], "dynasty": d or b["dynasty"],
                   "cat": c or b["cat"], "desc": desc or b["desc"], "total": total,
                   "chapters": [{"hash": x, "title": y} for x, y in chaps]})
        return b2

    out = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, b) for b in books]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                out.append(r)
            if i % 50 == 0:
                print(f"books {i}/{len(books)} {STATS}", flush=True)
    order = {b["hash"]: i for i, b in enumerate(books)}
    out.sort(key=lambda x: order[x["hash"]])
    json.dump(out, open(os.path.join(ROOT, "gw_books_full.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"BOOKS {len(out)} CHAPTERS {sum(len(b['chapters']) for b in out)} "
          f"DECLARED {sum(b['total'] for b in out)} {STATS}")


def stage_chapters(workers=3):
    books = json.load(open(os.path.join(ROOT, "gw_books_full.json"), encoding="utf-8"))
    tasks = [(b["hash"], c["hash"]) for b in books for c in b["chapters"]]
    print("chapters to fetch:", len(tasks), flush=True)

    def one(t):
        bh, ch = t
        h = fetch(f"{BASE}/guwen/bookv_{ch}.aspx", "chapter", ch)
        if not h:
            return None
        title, paras = parse_chapter(h)
        return {"book": bh, "hash": ch, "title": title, "paras": paras}

    done = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, t) for t in tasks]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                done.append(r)
            if i % 500 == 0:
                print(f"chapters {i}/{len(tasks)} {STATS}", flush=True)
    json.dump(done, open(os.path.join(ROOT, "gw_chapters.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"CHAPTERS ok={len(done)}/{len(tasks)} {STATS}")


def stage_mingju(workers=3):
    books = json.load(open(os.path.join(ROOT, "gw_books_full.json"), encoding="utf-8"))
    books = [b for b in books if b.get("mingjuUrl")]

    def one_book(b):
        base = b["mingjuUrl"]
        if base.startswith("http"):
            base = base.split(".cn", 1)[1]
        base = BASE + base
        rows, page = [], 1
        while page <= 30:
            url = f"{base}&page={page}" if page > 1 else base
            h = fetch(url, "mjpage", f"{b['hash']}_{page}")
            if not h:
                break
            got = parse_mingju_list(h)
            if not got:
                break
            for g in got:
                g["book"] = b["hash"]
                g["bookTitle"] = b["title"]
            rows += got
            if not page_has_next(h, "page"):
                break
            page += 1
        return rows

    lists = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one_book, b) for b in books]
        for i, f in enumerate(as_completed(futs), 1):
            lists += f.result()
            if i % 40 == 0:
                print(f"mj-list {i}/{len(books)} rows={len(lists)} {STATS}", flush=True)
    seen, uniq = set(), []
    for r in lists:
        if r["juv"] in seen:
            continue
        seen.add(r["juv"])
        uniq.append(r)
    json.dump(uniq, open(os.path.join(ROOT, "gw_mingju_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"MINGJU listed {len(uniq)} {STATS}", flush=True)

    def one_juv(r):
        h = fetch(f"{BASE}/mingju/juv_{r['juv']}.aspx", "juv", r["juv"])
        if not h:
            return None
        d = parse_juv(h)
        d["juv"] = r["juv"]
        d["book"] = r["book"]
        d["bookTitle"] = r["bookTitle"]
        d["fromText"] = d["from"] or r["fromText"]
        return d

    out = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one_juv, r) for r in uniq]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                out.append(r)
            if i % 500 == 0:
                print(f"juv {i}/{len(uniq)} {STATS}", flush=True)
    json.dump(out, open(os.path.join(ROOT, "gw_mingju_detail.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"JUV ok={len(out)}/{len(uniq)} {STATS}")


STAGES = {"index": stage_index, "books": stage_books,
          "chapters": stage_chapters, "mingju": stage_mingju}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "index"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    fn = STAGES[cmd]
    if cmd == "index":
        fn()
    else:
        fn(workers)
