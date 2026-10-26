# -*- coding: utf-8 -*-
"""把古文岛抓取结果生成到 chinese-poetry-md 的 poems/ 结构。

产出两类条目，均沿用仓内诗词 frontmatter：
  1. 古籍章节  poems/<2字母>/<作者slug>/<作者slug>-<书名slug>-<章节slug>.md
  2. 古籍名句  poems/<2字母>/<作者slug>/<作者slug>-<书名slug>-mingju-<hash8>.md
     （含 摘自 / 译文 / 注释 / 赏析 区块）

用法：
  python build_gw.py <target_poems_dir>
"""
import os
import re
import sys
import json
import hashlib

from build_books import slugify, render_body
from build_poems import scan_existing

ROOT = os.path.dirname(os.path.abspath(__file__))

DYNASTY_FIX = {"两汉": "汉", "汉代": "汉", "先秦": "先秦", "魏晋": "魏晋", "南北朝": "南北朝",
               "隋代": "隋", "唐代": "唐", "五代": "五代", "宋代": "宋", "金朝": "金",
               "元代": "元", "明代": "明", "清代": "清", "近现代": "近现代", "中华民国": "民国"}


def clean_author(raw):
    s = (raw or "").strip()
    s = re.sub(r"[（(].*?[)）]", "", s).strip()
    s = re.sub(r"(及其后学|及后学|及门人|及门徒|及再传弟子|等撰|等编|等|撰|编|著)$", "", s).strip()
    return s or "佚名"


def author_slug_base(name):
    """作者名用于 slug 的部分：截掉“及…”等并列修饰"""
    s = re.split(r"(及其|及|等)", name)[0].strip()
    return s or name


def split_cat(cat):
    """'子部道家类' -> ['子部','道家类']"""
    m = re.match(r"^(经部|史部|子部|集部|丛书部)(.*)$", cat or "")
    if m:
        return [x for x in (m.group(1), m.group(2)) if x]
    return [cat] if cat else []


def safe_name(stem, adir, limit=120):
    """避免 Windows 长路径：超长截断并加短 hash"""
    if len(stem) <= limit:
        return stem
    h = hashlib.md5(stem.encode("utf-8")).hexdigest()[:8]
    return stem[:limit - 9].rstrip("-") + "-" + h


def build(target_poems):
    books = json.load(open(os.path.join(ROOT, "gw_books_full.json"), encoding="utf-8"))
    chapters = {c["hash"]: c for c in
                json.load(open(os.path.join(ROOT, "gw_chapters.json"), encoding="utf-8"))}
    jp = os.path.join(ROOT, "gw_mingju_detail.json")
    juvs = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else []
    # 名句归属校正：站点按书名模糊匹配，可能把《后汉书》的名句挂到《汉书》下；
    # 以详情页「摘自《X·Y》」的 X 为准重定向到正确的书。
    by_title = {b["title"]: b for b in books}
    order = sorted(by_title, key=len, reverse=True)

    def resolve(book_hash, frm):
        head = re.split(r"[·•]", (frm or "").strip())[0] if frm else ""
        if head:
            for t in order:                      # 最长书名优先
                if head == t or head.startswith(t):
                    return by_title[t]
        return next((b for b in books if b["hash"] == book_hash), None)

    juv_by_book, retarget = {}, 0
    for j in juvs:
        tgt = resolve(j.get("book", ""), j.get("from") or j.get("fromText"))
        if tgt:
            if tgt["hash"] != j.get("book"):
                retarget += 1
            j = dict(j)
            j["_book"] = tgt
            juv_by_book.setdefault(tgt["hash"], []).append(j)
        else:
            juv_by_book.setdefault(j.get("book", ""), []).append(j)
    print("名句归属校正:", retarget, flush=True)

    scan_dir = os.path.join(ROOT, "repo_full", "poems")
    if not os.path.isdir(scan_dir):
        scan_dir = target_poems
    os.makedirs(target_poems, exist_ok=True)
    print("scan existing poems ...", flush=True)
    by_name_dyn, by_name = scan_existing(scan_dir)
    print("existing authors:", len(set(by_name.values())), flush=True)

    catalog = []
    n_ch = n_juv = conflicts = 0
    bytes_total = 0

    only = set(x.strip() for x in os.environ.get("GW_ONLY", "").split(",") if x.strip())
    for b in books:
        title = b["title"]
        if only and title not in only:
            continue
        bslug = slugify(title, 24)
        author_raw = b.get("author", "")
        author = clean_author(author_raw)
        dynasty = DYNASTY_FIX.get(b.get("dynasty", ""), b.get("dynasty", ""))
        cats = split_cat(b.get("cat", ""))
        aslug = (by_name_dyn.get((author, dynasty)) or by_name.get(author)
                 or slugify(author_slug_base(author), 30))
        letter = aslug[:2].ljust(2, "-")
        adir = os.path.join(target_poems, letter, aslug)
        os.makedirs(adir, exist_ok=True)

        book_ch, book_juv = 0, 0
        for idx, c in enumerate(b.get("chapters", []), 1):
            body = chapters.get(c["hash"])
            if not body or not body["paras"]:
                continue
            ctitle = c["title"] or body["title"]
            prefix = aslug if aslug == bslug else f"{aslug}-{bslug}"
            stem = safe_name(f"{prefix}-{slugify(ctitle, 70)}", adir)
            fp = os.path.join(adir, stem + ".md")
            if os.path.exists(fp):
                conflicts += 1
                cand = os.path.join(adir, f"{stem}-c{idx:03d}.md")
                fp = cand if not os.path.exists(cand) else os.path.join(
                    adir, f"{stem}-c{idx:03d}-{c['hash'][:6]}.md")
            text = render_body(body["paras"])
            fm = ["---", f"id: {os.path.basename(fp)[:-3]}", f"title: {ctitle}",
                  f"author: {author}", f"authorSlug: {aslug}",
                  f"book: {title}", f"bookSlug: {bslug}"]
            if dynasty:
                fm += [f"dynasty: {dynasty}", f"dynastySlug: {slugify(dynasty, 20)}"]
            fm += ["tags:", "  - 古籍"]
            for x in cats:
                fm.append(f"  - {x}")
            fm += [f"chapterIndex: {idx}", f"sourceId: {c['hash']}", "---", "",
                   "## 正文", "", text, ""]
            out = "\n".join(fm)
            open(fp, "w", encoding="utf-8").write(out)
            bytes_total += len(out.encode("utf-8"))
            book_ch += 1

        for j in juv_by_book.get(b["hash"], []):
            jtext = (j.get("text") or "").strip()
            if not jtext:
                continue
            # 该名句所属书（可能是校正后的书）
            jb = j.get("_book") or b
            if jb["hash"] != b["hash"]:
                continue   # 在它自己所属的书环节生成
            jhash = j.get("juv", "")[:8]
            mprefix = aslug if aslug == bslug else f"{aslug}-{bslug}"
            stem = safe_name(f"{mprefix}-mingju-{jhash}", adir)
            fp = os.path.join(adir, stem + ".md")
            if os.path.exists(fp):
                conflicts += 1
                fp = os.path.join(adir, f"{stem}-{jhash}.md")
            fm = ["---", f"id: {os.path.basename(fp)[:-3]}",
                  f"title: {re.sub(chr(10), ' ', jtext)[:60]}",
                  "type: 名句",
                  f"author: {author}", f"authorSlug: {aslug}",
                  f"book: {title}", f"bookSlug: {bslug}",
                  f"from: {j.get('fromText') or j.get('from') or ''}"]
            if dynasty:
                fm += [f"dynasty: {dynasty}", f"dynastySlug: {slugify(dynasty, 20)}"]
            fm += ["tags:", "  - 名句", "  - 古籍"]
            for x in cats:
                fm.append(f"  - {x}")
            fm += [f"sourceId: {j.get('juv','')}", "---", "", "## 正文", "", jtext, ""]
            for key in ("译文", "注释", "赏析"):
                val = (j.get(key) or "").strip()
                if val:
                    fm += [f"## {key}", "", val, ""]
            out = "\n".join(fm)
            open(fp, "w", encoding="utf-8").write(out)
            bytes_total += len(out.encode("utf-8"))
            book_juv += 1

        n_ch += book_ch
        n_juv += book_juv
        catalog.append({"hash": b["hash"], "title": title, "slug": bslug,
                        "author": author, "authorRaw": author_raw, "authorSlug": aslug,
                        "path": f"poems/{letter}/{aslug}/", "dynasty": dynasty,
                        "cat": b.get("cat", ""), "categories": cats,
                        "chapters": book_ch, "declaredChapters": b.get("total", 0),
                        "mingju": book_juv, "declaredMingju": b.get("mingjuCount", 0),
                        "desc": b.get("desc", "")})
        print(f"[{title:<10}] {book_ch:>4}章 {book_juv:>4}名句 -> poems/{letter}/{aslug}/",
              flush=True)

    json.dump(catalog, open(os.path.join(ROOT, "gushiwen_catalog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nDONE books={len(catalog)} chapters={n_ch} mingju={n_juv} "
          f"conflicts={conflicts} size={bytes_total/1048576:.1f} MB")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "repo_full", "poems")
    build(target)
