# -*- coding: utf-8 -*-
"""把 shangshici 典籍缓存解析为 chinese-poetry-md 现有 poems/ 规范的 Markdown。

输出（与站内诗词同一套规范）：
  poems/<2字母前缀>/<作者slug>/<作者slug>-<书名slug>-<章节slug>.md
并在仓库根生成 dianji_catalog.json 作为典籍元数据索引。
"""
import os
import re
import sys
import json
from pypinyin import lazy_pinyin

import shangshici_scraper as S
from build_books import DYNASTY, AUTHOR_FIX, clean_author, render_body, slugify, parse_book_categories

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(ROOT, "repo_full", "poems")


def slugify(text: str, maxlen: int = 90) -> str:  # noqa: F811
    from build_books import slugify as _s
    return _s(text, maxlen)


def scan_existing(poems_dir):
    """扫描现有 poems，建立 作者(名,朝代)->slug 映射，避免新建重复作者目录。"""
    by_name_dyn, by_name = {}, {}
    for letter in os.listdir(poems_dir):
        ldir = os.path.join(poems_dir, letter)
        if not os.path.isdir(ldir):
            continue
        for slug in os.listdir(ldir):
            adir = os.path.join(ldir, slug)
            if not os.path.isdir(adir):
                continue
            picked = None
            for f in os.listdir(adir):
                if f.endswith(".md") and f != "bio.md":
                    picked = os.path.join(adir, f)
                    break
            if not picked:
                continue
            try:
                head = open(picked, encoding="utf-8", errors="replace").read(1200)
            except Exception:
                continue
            ma = re.search(r"^author:\s*(.+)$", head, re.M)
            md = re.search(r"^dynasty:\s*(.+)$", head, re.M)
            if not ma:
                continue
            name = ma.group(1).strip().strip('"')
            dyn = md.group(1).strip().strip('"') if md else ""
            by_name_dyn.setdefault((name, dyn), slug)
            by_name.setdefault(name, slug)
    return by_name_dyn, by_name


def build(target_poems, only=None):
    books = json.load(open(os.path.join(ROOT, "books_index.json"), encoding="utf-8"))
    print("scanning existing poems ...", flush=True)
    by_name_dyn, by_name = scan_existing(target_poems)
    print(f"existing author slugs: {len(set(by_name.values()))}", flush=True)

    catalog, total_ch, total_bytes, conflict = [], 0, 0, 0
    for k in sorted(books, key=lambda x: int(x)):
        bid = int(k)
        if only and bid not in only:
            continue
        info = books[k]
        btitle = info["title"]
        bslug = slugify(btitle, 24)
        author = clean_author(info.get("author", ""))
        dynasty = DYNASTY.get(bid, "")
        toc_html = S.crawl_book_toc(bid)
        cats = parse_book_categories(toc_html or "")
        toc = S.parse_toc(toc_html or "")

        aslug = by_name_dyn.get((author, dynasty)) or by_name.get(author) or slugify(author, 30)
        letter = aslug[:2].ljust(2, "-")
        adir = os.path.join(target_poems, letter, aslug)
        os.makedirs(adir, exist_ok=True)

        chapters = []
        for idx, (cid, ctitle, t) in enumerate(toc, 1):
            _, _, paras = S.parse_chapter(S.crawl_chapter(bid, cid, t))
            title = ctitle
            if not paras:
                continue
            room = max(20, 120 - len(aslug) - len(bslug) - 2)
            cslug = slugify(title, room)
            stem = f"{aslug}-{bslug}-{cslug}"
            fp = os.path.join(adir, stem + ".md")
            if os.path.exists(fp):
                conflict += 1
                fp = os.path.join(adir, f"{stem}-{cid}.md")

            text = render_body(paras)
            fm = ["---", f"id: {os.path.basename(fp)[:-3]}", f"title: {title}",
                  f"author: {author}", f"authorSlug: {aslug}",
                  f"book: {btitle}", f"bookSlug: {bslug}"]
            if dynasty:
                fm += [f"dynasty: {dynasty}", f"dynastySlug: {slugify(dynasty, 20)}"]
            fm += ["tags:", "  - 古籍"]
            for c in cats:
                fm.append(f"  - {c}")
            fm += [f"chapterIndex: {idx}", f"sourceId: {cid}", "---", "", "## 正文", "", text, ""]
            body = "\n".join(fm)
            open(fp, "w", encoding="utf-8").write(body)
            total_bytes += len(body.encode("utf-8"))
            chapters.append({"index": idx, "title": title,
                             "file": f"poems/{letter}/{aslug}/{os.path.basename(fp)}"})
        total_ch += len(chapters)
        catalog.append({"id": bid, "title": btitle, "slug": bslug, "author": author,
                        "authorSlug": aslug, "path": f"poems/{letter}/{aslug}/",
                        "dynasty": dynasty, "categories": cats,
                        "chapters": len(chapters), "tocCount": len(toc)})
        print(f"[{bid:3d}] {btitle:<12} {len(chapters):>4} 章 -> poems/{letter}/{aslug}/ "
              f"({aslug}-{bslug}-*)", flush=True)

    json.dump(catalog, open(os.path.join(ROOT, "dianji_catalog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nDONE books={len(catalog)} chapters={total_ch} conflicts={conflict} "
          f"size={total_bytes/1048576:.1f} MB")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    only = None
    for a in sys.argv[2:]:
        if a.startswith("--only="):
            only = set(int(x) for x in a[7:].split(","))
    build(out, only)
