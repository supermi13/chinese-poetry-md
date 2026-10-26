# chinese-poetry-md

[![GitHub stars](https://img.shields.io/github/stars/daichangya/chinese-poetry-md)](https://github.com/daichangya/chinese-poetry-md/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/daichangya/chinese-poetry-md)](https://github.com/daichangya/chinese-poetry-md/network/members)

中文诗词 Markdown 仓库，供 [chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) 构建使用。每首诗对应一个 .md 文件，可在此仓参与纠错与完善。本仓是站点的**内容层**，便于版本管理与协作；可增补译文、赏析、注释或纠错别字，站点构建时从本仓解析 .md 入库后提供阅读与检索。

## 目录结构

- `poems/<2字母前缀>/<作者slug>/<作者slug>-<题名slug>.md` — 单首诗词的 Markdown（正文、拼音、译文、注释、赏析等）
- `poems/<2字母前缀>/<作者slug>/bio.md` — 该作者的简介（可选）

示例：`poems/li/li-bai/li-bai-jing-ye-si-chuang-qian-ming-yue-guang.md`、`poems/su/su-shi/bio.md`。

古籍条目同在此结构内，文件名带书名段：`poems/la/lao-zi/lao-zi-di-ba-shi-yi-zhang.md`、`poems/si/si-ma-qian/si-ma-qian-shi-ji-bo-yi-lie-zhuan-di-yi.md`、`poems/la/lao-zi/lao-zi-mingju-021f273e.md`（名句）。

## 单首 .md 格式

每个 .md 包含 **YAML frontmatter**（标题、作者、朝代、标签、词牌等）和 **正文区块**：`## 正文`、`## 拼音`、`## 译文`、`## 赏析`、`## 注释`。路径为 `poems/<作者slug>/<诗题slug>.md`，slug 为无声调拼音 + 连字符。详细约定见 [chinese-poetry-site 的 markdown-format](https://github.com/daichangya/chinese-poetry-site/blob/main/docs/markdown-format.md)。

## 古籍典籍与名句（收录在 poems/ 内）

仓内古籍条目与诗词共用 `poems/` 结构，整理自 [古文岛（原古诗文网）· 古籍](https://www.gushiwen.cn/guwen/)。当前收录 **200 部典籍、18312 章**，另有 **6211 条古籍名句**，涵盖经、史、子、集四部（如《论语》《史记》《资治通鉴》《本草纲目》《聊斋志异》），已按作者归入既有作者 slug（`lao-zi`、`si-ma-qian`、`pu-song-ling`、`tuo-tuo` 等）。

### 两类条目

1. **古籍章节**：`poems/<2字母>/<作者slug>/<作者slug>-<书名slug>-<章节slug>.md`
   frontmatter：`id` / `title` / `author` / `authorSlug` / `book` / `bookSlug` / `dynasty` / `tags`（首项 `古籍`，后接四部分类）/ `chapterIndex` / `sourceId`，正文在 `## 正文`。
   作者 slug 与书名 slug 相同时省略书名段（如 `lao-zi-di-ba-shi-yi-zhang.md`）；同书内章节重名追加 `-c<序号>` 区分。
2. **古籍名句**：`poems/<2字母>/<作者slug>/<作者slug>-<书名slug>-mingju-<hash8>.md`
   frontmatter 额外带 `type: 名句`、`book`、`from`（摘自，如「老子·德经·第六十四章」），正文区块为 `## 正文`（名句原文）、`## 译文`、`## 注释`、`## 赏析`。

典籍层级元数据（书名、作者、朝代、四部分类、章节数与名句数、落盘路径）见仓库根 `gushiwen_catalog.json`。

采集与生成脚本见 `tools/`（`gushiwen_scraper.py` 抓取、`build_gw.py` 生成 Markdown），可重跑以更新或增补。

## 访问站点

由本仓 .md 构建的诗词站：[https://shi-ci.cn](https://shi-ci.cn)（[chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) 部署）。

## 数据来源

本仓库内容由 [chinese-poetry](https://github.com/daichangya/chinese-poetry) 经 [chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) 的 `gen_markdown` 脚本生成，并可在本地或 GitHub 上人工增补、纠错。

## 相关仓库

| 仓库 | 说明 |
|------|------|
| [chinese-poetry](https://github.com/daichangya/chinese-poetry) | 诗词 JSON 数据源 |
| [chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) | 站点代码与 gen_markdown/seed_db |
| 本仓 chinese-poetry-md | 诗词 .md 合集，供站点构建使用 |

## 本地生成与推送

在 [chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) 中克隆本仓到目录（如 `chinese-poetry-md`），设置 `POEMS_DIR` 指向该目录。执行 `npm run gen_markdown` 生成 .md 到本仓；再用本仓根目录的 `git-add-n.sh` 分批 add/commit/push（见下方「大量文件时的推送」）。

## 作者简介（bio.md）生成与校验

在 **chinese-poetry-site** 仓库中设置环境变量后执行（示例路径请按本机调整）：

```bash
export POEMS_DIR=/path/to/chinese-poetry-md
export CHINESE_POETRY_DIR=/path/to/chinese-poetry

# 1. 从诗词 frontmatter 生成 author_slug_index.json（解决同音 slug 冲突）
npm run build:author-index

# 2. 从 authors JSON 安全写入 bio，并对仍缺失者生成推断简介
npm run gen_author_bio

# 3. 规范化 title / short_description / 正文
npm run normalize:bios

# 4. 审计覆盖率与质量分级（名家 slug 缺失会失败退出）
npm run audit:bios
```

推荐二次补全（拆分后释放 JSON 碰撞写入）：

```bash
npm run build:author-index
npm run gen_author_bio -- --fix-stubs --fill-missing
npm run normalize:bios
npm run audit:bios
```

常用参数：`--fix-stubs`（仅修近空简介）、`--fill-missing`、`--force`（慎用）、`--no-infer-missing`（不生成推断模板）。

产出报告：

- `bio_generation_report.json` — 写入/跳过统计（含 `written_by_canonical_match`）
- `bio_audit_report.json` — 缺失、stub、title 一致性
- `bio_quality_report.json` — 质量分级：`minimal` / `inferred` / `short` / `full`，及 orphan（有 bio 无诗词 index）清单

作者页链接一律使用**当前**目录 slug（如 `su-shi`、`su-shi-shi`），不做旧 slug 重定向。

若同一 `authorSlug` 目录内混有多个作者（同音不同字），在站点仓执行拆分（canonical 作者保留原 slug，其余迁至 `su-shi-shi` 等形式）：

```bash
npm run split:ambiguous-authors
npm run split:ambiguous-authors -- --all-multi-author
```

拆分过程记录见 `author_slug_split_map.json`（仅供追溯，站点不读取）。

## 如何参与

可增补译文、赏析、注释或纠错别字。

- 在 [chinese-poetry-site](https://github.com/daichangya/chinese-poetry-site) 诗词详情页点击「纠错与完善」可跳转到本仓对应文件的 GitHub 编辑页。
- 或直接在本仓提交 Pull Request；格式约定见站点的 [markdown-format](https://github.com/daichangya/chinese-poetry-site/blob/main/docs/markdown-format.md) 与 [CONTRIBUTING](https://github.com/daichangya/chinese-poetry-site/blob/main/CONTRIBUTING.md)。

## 大量文件时的推送

若未暂存文件很多（如首次全量生成或大批更新），可用仓库根目录下的 `git-add-n.sh` 分批提交：

```bash
./git-add-n.sh 500
```

表示本次最多 add 500 个文件并执行 commit + push。可多次运行直到 `git status` 无未暂存变更。不传参数时默认每次最多 100 个文件。
