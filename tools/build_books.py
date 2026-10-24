# -*- coding: utf-8 -*-
"""把 shangshici 典籍缓存解析为 chinese-poetry-md 风格的 books/ Markdown 目录。

输出结构：
  books/README.md                      总索引
  books/catalog.json                   机器可读目录
  books/<bookSlug>/index.md            书籍信息 + 章节目录
  books/<bookSlug>/<chapterSlug>.md    单章正文
"""
import os
import re
import json
import html
import hashlib
from pypinyin import lazy_pinyin

import shangshici_scraper as S

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "books")

# 书名 -> 朝代（手工核定，未列者留空）
DYNASTY = {
    1: "先秦", 2: "先秦", 3: "先秦", 4: "明清", 5: "汉", 6: "先秦", 7: "先秦", 8: "宋",
    9: "清", 10: "先秦", 11: "先秦", 12: "明", 13: "明", 14: "宋", 15: "宋", 16: "宋",
    17: "南北朝", 18: "南北朝", 19: "先秦", 20: "先秦", 21: "先秦", 22: "先秦", 23: "先秦",
    24: "先秦", 25: "先秦", 26: "先秦", 27: "先秦", 28: "先秦", 29: "先秦", 30: "先秦",
    31: "先秦", 32: "先秦", 33: "汉", 34: "先秦", 35: "先秦", 36: "先秦", 37: "汉",
    38: "明", 39: "秦汉", 40: "汉", 41: "南北朝", 42: "先秦", 43: "南北朝", 44: "先秦",
    45: "先秦", 46: "汉", 47: "南北朝", 48: "先秦", 49: "晋", 50: "晋", 51: "清",
    52: "明", 53: "汉", 54: "晋", 55: "三国", 56: "先秦", 57: "唐", 58: "先秦",
    59: "先秦", 60: "先秦", 61: "先秦", 62: "唐", 63: "汉唐", 64: "清", 65: "唐",
    66: "唐", 67: "明", 68: "清", 69: "明", 70: "明", 71: "清", 72: "宋", 73: "清",
    74: "汉", 75: "明", 76: "汉", 77: "南北朝", 78: "明", 79: "元", 80: "秦",
    81: "唐", 82: "南北朝", 83: "南北朝", 84: "唐", 85: "唐", 86: "南北朝", 87: "唐",
    88: "唐", 89: "唐", 90: "唐", 91: "唐", 92: "五代", 93: "宋", 94: "宋", 95: "宋",
    96: "元", 97: "元", 98: "元", 99: "明", 100: "清", 101: "先秦", 102: "清",
    103: "晋", 104: "先秦", 105: "清", 106: "明", 107: "明", 108: "明", 109: "汉",
    110: "汉", 111: "宋", 112: "清", 113: "汉", 114: "清", 115: "汉", 116: "唐",
    117: "唐", 118: "清", 119: "宋", 120: "清", 121: "清", 122: "明", 123: "明",
    124: "明", 125: "明", 126: "明", 127: "明", 128: "清", 129: "明", 130: "清",
    131: "清", 132: "清", 133: "清", 134: "清", 135: "明", 136: "晋", 137: "唐",
    138: "民国", 139: "民国", 140: "民国", 141: "民国", 142: "明", 143: "明",
    144: "民国", 145: "民国", 146: "民国", 147: "民国", 148: "明", 149: "明",
    150: "先秦", 151: "民国",
}

AUTHOR_FIX = {  # 站点作者字段的清洗结果
    "刘安及门客 撰": "刘安", "管仲及门徒": "管仲", "吕不韦 主编": "吕不韦",
    "庄子及门徒": "庄子", "房玄龄等": "房玄龄", "魏征等": "魏征",
    "沈昫等": "沈昫", "脱脱、阿鲁图等": "脱脱", "宋濂、王祎等": "宋濂",
    "张廷玉等": "张廷玉", "李昉、扈蒙、徐铉等": "李昉", "蔡东藩、许廑父": "蔡东藩",
    "李大师、李延寿": "李延寿", "欧阳修、宋祁等": "欧阳修", "脱脱等": "脱脱",
    "薛居正等": "薛居正", "游戏主人纂集": "游戏主人",
}


def slugify(text: str, maxlen: int = 90) -> str:
    text = re.sub(r"[（）()\[\]【】·、，,。！？!?:：;；“”‘’\"'《》〈〉/\\|]+", " ", text)
    parts = lazy_pinyin(text.strip())
    s = "-".join(p for p in parts if re.fullmatch(r"[a-z0-9]+", p or ""))
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "sec-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-") + "-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return s


def clean_author(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "佚名"
    if raw in AUTHOR_FIX:
        return AUTHOR_FIX[raw]
    raw = re.sub(r"(及门徒|及门客|等|撰|主编|纂集|編)$", "", raw).strip()
    return raw or "佚名"


# 本草/医书条目中的固定字段名，渲染为小节标题
FIELD_WORDS = {"释名", "集解", "正误", "修治", "气味", "主治", "发明", "附方", "核曰", "参曰",
               "气味主治", "主治参互", "简误", "炮制", "性味", "归经", "功效", "用法"}


def render_body(paras):
    out = []
    for p in paras:
        s = p.strip()
        if len(s) <= 6 and s in FIELD_WORDS:
            out.append(f"### {s}")
        else:
            out.append(s)
    return "\n\n".join(out)


def parse_book_categories(h):
    """从 book.asp 页面提取四部分类标签"""
    cats = []
    for m in re.finditer(r"dianji\.asp\?p=1&c=([^']+)'>([^<]*)</a>", h):
        cats.append(html.unescape(m.group(2)).strip())
    seen, out = set(), []
    for c in cats:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:3]


def build(only=None):
    books = json.load(open(os.path.join(ROOT, "books_index.json"), encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    catalog = []
    total_ch = 0
    total_bytes = 0

    for k in sorted(books, key=lambda x: int(x)):
        bid = int(k)
        if only and bid not in only:
            continue
        info = books[k]
        btitle = info["title"]
        slug = slugify(btitle, 40)
        author = clean_author(info.get("author", ""))
        dynasty = DYNASTY.get(bid, "")
        toc_html = S.crawl_book_toc(bid)
        cats = parse_book_categories(toc_html or "")
        toc = S.parse_toc(toc_html or "")

        bdir = os.path.join(OUT, slug)
        os.makedirs(bdir, exist_ok=True)

        chapters = []
        used = set()
        for idx, (cid, ctitle, t) in enumerate(toc, 1):
            ch_html = S.crawl_chapter(bid, cid, t)
            title, _, paras = S.parse_chapter(ch_html)
            title = title or ctitle
            if not paras:
                continue
            base = f"{slug}-{slugify(title, 70)}"
            fname = base + ".md"
            if fname in used:
                fname = f"{slug}-{slugify(title, 60)}-{cid}.md"
            used.add(fname)

            text = render_body(paras)
            fm = [
                "---",
                f'id: {fname[:-3]}',
                f"title: {title}",
                f"book: {btitle}",
                f"bookSlug: {slug}",
                f"author: {author}",
                f"authorSlug: {slugify(author, 30)}",
            ]
            if dynasty:
                fm += [f"dynasty: {dynasty}", f"dynastySlug: {slugify(dynasty, 20)}"]
            fm += ["tags:", "  - 古籍"]
            for c in cats:
                fm.append(f"  - {c}")
            fm += [f"chapterIndex: {idx}", f"sourceId: {cid}", "---", "",
                   "## 正文", "", text, ""]
            body = "\n".join(fm)
            open(os.path.join(bdir, fname), "w", encoding="utf-8").write(body)
            total_bytes += len(body.encode("utf-8"))
            chapters.append({"index": idx, "title": title, "file": fname, "chars": len(text)})

        total_ch += len(chapters)

        # 书籍 index.md
        lines = ["---", f"id: {slug}", f"title: {btitle}", f"author: {author}",
                 f"authorSlug: {slugify(author, 30)}"]
        if dynasty:
            lines += [f"dynasty: {dynasty}", f"dynastySlug: {slugify(dynasty, 20)}"]
        lines += ["type: book", "tags:", "  - 古籍"]
        for c in cats:
            lines.append(f"  - {c}")
        lines += ["---", "", f"# {btitle}", "",
                  f"- 作者：{author}",
                  f"- 朝代：{dynasty or '未标注'}",
                  f"- 分类：{' / '.join(cats) if cats else '未标注'}",
                  f"- 章节数：{len(chapters)}", ""]
        desc = (info.get("desc") or "").replace("&nbsp;", "").replace("\u00a0", "").replace("▼", "").strip()
        if desc:
            lines += ["## 简介", "", desc, ""]
        lines += ["## 目录", ""]
        if not chapters:
            lines += ["> 说明：源站该典籍的章节链接缺少正文数据（全部指向空 ID），故暂未收录正文。", ""]
        for c in chapters:
            lines.append(f"{c['index']}. [{c['title']}](./{c['file']})")
        lines.append("")
        if len(toc) > len(chapters) > 0:
            lines += [f"> 说明：源站目录列出 {len(toc)} 条，其中 {len(toc) - len(chapters)} 条正文缺失或重复，"
                      "已按实际有内容的章节收录。", ""]
        open(os.path.join(bdir, "index.md"), "w", encoding="utf-8").write("\n".join(lines))

        catalog.append({
            "id": bid, "title": btitle, "slug": slug, "author": author,
            "dynasty": dynasty, "categories": cats, "chapters": len(chapters),
            "tocCount": len(toc), "desc": desc,
        })
        print(f"[{bid:3d}] {btitle:<12} {len(chapters)}/{len(toc)} 章 -> books/{slug}/", flush=True)

    json.dump(catalog, open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 总索引 README
    by_cat = {}
    for c in catalog:
        key = c["categories"][0] if c["categories"] else "其他"
        by_cat.setdefault(key, []).append(c)
    lines = ["# 古籍典籍", "",
             "本目录收录自 [赏诗词网·古文典籍](http://www.shangshici.com/dianji.asp) 整理的中国古籍全文，",
             "以 Markdown 形式存放，供 chinese-poetry-md 内容层使用。", "",
             f"- 典籍：{len(catalog)} 部", f"- 章节：{total_ch} 篇", "",
             "## 目录", ""]
    for cat in sorted(by_cat, key=lambda x: -len(by_cat[x])):
        lines.append(f"### {cat}（{len(by_cat[cat])} 部）")
        lines.append("")
        for c in by_cat[cat]:
            lines.append(f"- [{c['title']}](./{c['slug']}/index.md) — {c['author']}"
                         f"{'·' + c['dynasty'] if c['dynasty'] else ''}｜{c['chapters']} 章")
        lines.append("")
    gaps = [c for c in catalog if c["tocCount"] > c["chapters"]]
    if gaps:
        lines += ["## 数据完整性", "",
                  "以下典籍在源站存在目录条目但正文缺失/重复，已按实际抓到的章节收录：", ""]
        for c in gaps:
            lines.append(f"- {c['title']}：目录 {c['tocCount']} 条，实收 {c['chapters']} 章")
        lines.append("")
    lines += ["## 文件格式", "",
              "每章一个 .md，YAML frontmatter 字段：`id` / `title` / `book` / `bookSlug` / "
              "`author` / `authorSlug` / `dynasty` / `tags` / `chapterIndex` / `sourceId`，"
              "正文位于 `## 正文` 区块。每部典籍另有 `index.md` 作为目录页。", ""]
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write("\n".join(lines))

    print(f"\nDONE books={len(catalog)} chapters={total_ch} size={total_bytes/1048576:.1f} MB")


if __name__ == "__main__":
    build()
