---
name: literature-fetch
description: >-
  学术文献的查找、查阅与【正版】下载。三种用法：①主题/关键词调研（"找找关于X的论文"，
  OpenAlex 免代理检索+摘要，选中的可下到临时缓存供 AI 直接阅读讲解）；②单篇速查/速取
  （给定 DOI 或题目）；③批量下载留档（题目清单 xlsx/csv → 参考文献 文件夹）。
  下载只走"校园网机构权限 / 开放获取 OA / 出版社官网"，明确不使用任何盗版/侵权来源；
  Cloudflare 人机验证由用户本人手动通过。
  触发词：找/查关于某主题的论文、查文献、读一下这篇论文、下载这篇/一批论文、按题目找 PDF、
  批量查 DOI、literature search/download、fetch/read paper。
---

# 文献查找·查阅·正版下载 (literature-fetch)

## 🧭 自适应路由（无头优先，失败升级有头，结果记表自学习）

`references/route_table.json` 记录每家出版社（按 DOI 前缀）该走哪条路，**随运行结果自动完善**：

- **headless**：无头浏览器/直链就能下（IEEE、Springer、Nature、arXiv…）——批量快、不打扰用户。
- **headed**：有反爬（Cloudflare/PerimeterX），必须有头真实 Chrome + turnstilePatch 扩展（Elsevier、Wiley、IET、ACS、MDPI、AIP、RSC…）。
- **遇到表里没有的新出版社**：先无头试 → 成功记 `headless`；落到反爬挑战页记 `headed`；单纯失败（可能只是没权限）记失败次数不改判 → 有头成功后记 `headed`。表跟着 skill 走，拷到新电脑经验也带过去。

## 🔓 CF 验证怎么过（turnstilePatch 扩展 + 真人兜底）

有头浏览器全程挂 `assets/turnstilePatch` 扩展（抹掉自动化指纹 + 尝试自动点 Turnstile）。`ensure_access()` 统一处理：

1. **扩展先自动过 CF**（约 25s）——温和 CF（ACS/Wiley/MDPI/ACM 实测）**零点击自动过**。
2. **过不了 → 提示用户手点一次**——激进 CF（如 ScienceDirect）扩展自动点会卡"请稍候"，但**用户真人点击仍立刻通过**（CF 认可可信点击，不受扩展无效合成点击影响；已实测）。
3. **hCaptcha（如 IOP）/ 文本验证码（如 OPTICA）** → 扩展无效，直接等用户手动过。
4. `cf_clearance` 存进独立配置目录 `_cfprofile`，**同域名后续免验证**——过一次下一批。**别删 `_cfprofile`**。
- ⚠️ 原理：扩展只抹指纹、不做密码学破解，靠 CF 自身风控引擎放行；坚持要真人时仍需真人。等同于用户正常浏览器访问自己有权限的内容。

## ⚖️ 正版原则（硬性）

- **绝不使用任何盗版/侵权镜像**，不绕过付费墙抓取。
- 只用三条合法渠道：
  1. **机构订阅权限**（校园网/单位 IP 授权，等同于用户在浏览器里正常点"下载 PDF"）；
  2. **开放获取 OA**（arXiv、PMC、MDPI、机构知识库等作者/出版社授权的免费副本；自动直下仅限白名单正版 OA 站，来路不明的镜像不碰）；
  3. **出版社官网正版下载**（IEEE Xplore、ScienceDirect、Wiley、Springer 等官方入口）。
- Cloudflare「验证您是真人」由**用户本人手动点击**通过；脚本只在验证后的会话里正常下载。
- 既无 OA、机构又无权限的 → **如实标记未获取**，不强行绕过。

## 三种用法（按用户意图选路径）

### ① 主题/关键词调研 —— "找找关于量子计算在电力系统应用的论文"
1. 把宽泛提示词转成英文检索式（必要时换几组措辞多跑几轮）：
   `python scripts/search_topic.py "quantum computing power system" --n 15 [--from 2020] [--oa] [--sort cited]`
   走 OpenAlex 相关度搜索（**国内直连免代理**，不用谷歌学术），返回题目/年份/期刊/被引/DOI/**摘要**，同时写 `topic_results.json`。
2. 按相关度+被引筛选，整理清单给用户——**很多问题读摘要就能答，零下载**。
3. 用户要深读的，用 `fetch_one.py <DOI>` 下到**临时缓存**，再用 Read 工具直接读 PDF 讲内容。
4. **读完主动问一句要不要留档**；要才 `--keep` 或复制进 `参考文献\`。

### ② 单篇速查/速取 —— 给了具体题目或 DOI
`python scripts/fetch_one.py <DOI或"题目"> [--keep] [--headed]`
- 默认查阅模式：下到 `%TEMP%\literature-cache\`（按 DOI 命名，命中缓存不重下），打印路径供 Read 阅读，不污染工作目录。
- 获取顺序（自适应路由）：**OA 副本优先**（付费墙论文常有 arXiv 等 OA 版，读内容足够且免过反爬）→ 查路由表 → headless/未知社先**无头**试 → 已知/升级为 headed 的提示加 `--headed` 起有头 Chrome，**遇验证等用户手动点一次**后下载；结果都回写路由表。
- 全都拿不到：如实报告并给摘要。
- `--keep`：复制到 `参考文献\题目.pdf` 留档。

### ③ 批量下载留档 —— 给了题目清单
阶段 0→5 管线（下节），成品在 `参考文献\题目.pdf`。

## 批量管线（scripts/ 按序跑；出版社细节见 references/publishers.md）

工作目录里运行；`manifest.json` 记录状态可断点续跑；可选 `config.json`：`{"mailto": "你的真实邮箱", "pdf_dir": "参考文献"}`。

### 阶段 0 — 导入清单
`python scripts/00_import_list.py <输入.xlsx> [题目列(1起)] [表头行(1起)]`
自动探测表头行/题目列，生成 manifest。单篇/少量也可直接手写：`[{"num":1,"excel_title":"..."}]`。

### 阶段 1 — 查 DOI（+OA 直链）
`python scripts/01_resolve_doi.py [--only-missing]`
- OpenAlex 按题目搜（主）→ DOI + OA 直链；CrossRef 书目检索兜底。
- 相似度把关（OpenAlex ≥0.55，CrossRef ≥0.72），同分按**被引量决胜**（避开同名镜像/克隆记录）；中文题目自动标 `skip=cn`（无海外正版渠道，按需提示走知网）。
- ⚠️ **限流**：≤3 并发 + `mailto` 礼貌池 + 429 指数退避。**切勿 8+ 并发猛刷**，会被封 IP 数十分钟。

### 阶段 2 — 机构/OA 无头下载（headless，校园网直连=关代理）
`python scripts/02_download_institutional.py [lo hi]`
- 先试 OA/发现直链（**仅白名单正版 OA 站**：arXiv/PMC/MDPI/Frontiers 等）；
- 路由表已知 **headed** 的直接跳过（打标交给阶段 4，不浪费时间）；headless/未知的走 doi.org 跳出版社页：**IEEE** 页内 `fetch(getPDF.jsp?arnumber=…)` 取 base64（机构 IP 命中率极高）；其余读 `<meta name="citation_pdf_url">` / 按各社规律构造直链。
- 结果回写路由表：成功→headless；落反爬挑战页→headed；单纯失败只记次数（可能是没权限，不冤枉出版社）。

### 阶段 3 —（可选）谷歌学术补查
`python scripts/03_search_scholar.py`
阶段 1 查不到 DOI 的，按题目搜谷歌学术，抓出版社链接/DOI/[PDF] 直链回填。
⚠️ **网络分工（易错）**：谷歌学术要**开代理**；机构下载要**校园网直连（关代理）**。互斥！开代理→只查不下→关代理→重跑阶段 2/4。**明确提示用户切网络**。

### 阶段 4 — 有头下载（反爬出版社，需用户在场）
`python scripts/04_download_cloudflare.py [lo hi]`（**有头真实 Chrome + 用户手动过验证**）
- 处理对象：路由表 headed 的 + 阶段 2 无头失败升级上来的。
- DrissionPage 启 Chrome：`user-data-dir` 必须指**非默认**目录（新版 Chrome 禁止默认目录开调试端口）；无 `navigator.webdriver` 特征。
- 首遇某域名人机验证 → **提示用户在窗口里手动勾一次**；`cf_clearance` 存配置目录，**同域名后续免验证**，脚本按域名排序一口气下完。
- `always_open_pdf_externally=True` + `prompt_for_download=False` → 点下载直接落盘不弹"另存为"。
- 已知社走专用姿势：Elsevier 点带 token 的 `pdfft`；Wiley/IET 用 `pdfdirect/{doi}?download=true`；ACS 用 `doi/pdf/{doi}`；MDPI 用 `{文章页}/pdf`。**新出版社走通用兜底**（citation_pdf_url/扫页面 PDF 链接锚点下载），成功后记入路由表。
- **curl/requests 带 cookie 也被 CF 判 403，必须浏览器本身下载**。

### 阶段 5 — 收尾
`python scripts/05_collect.py`
`_raw/<序号>.pdf` → `参考文献\题目.pdf`（非法字符全角化、超长截断；重名题目加序号后缀防覆盖），打印未获取/跳过清单。

## 常见坑速查
- **各家 API 全 429**（OpenAlex/SemanticScholar/谷歌）：低并发+退避+mailto；被封等十几分钟或换 CrossRef/arXiv。
- **超热门/同名标题错配**：OpenAlex 可能给同名克隆记录（已按被引量决胜 + OA 白名单兜底）；下载完抽查 PDF 是否对题，错的重查。
- **装了 IDM 等下载器的电脑**：IDM 的浏览器接管是**系统级**的，连脚本启动的独立配置 Chrome 的下载也会被截走（文件进 IDM 目录，脚本等不到误判失败）。skill 已优先用**页内 fetch** 绕开下载子系统（IDM 截不走）；若锚点兜底仍被 IDM 抢，临时退出 IDM 或在其设置里取消对 Chrome 的接管。
- **页面上的 .pdf 链接≠本文 PDF**：文章页参考文献区常有第三方 PDF 链接（如作者主页），乱点会下错文件——扫描链接只认与文章页**同域名**的（已内置）。
- **换电脑**：拷贝本 skill 文件夹到 `~/.claude/skills/` + 装依赖即可（路由表经验随文件夹带走）；但**机构权限取决于那台电脑的网络**（校园网内全能用，网外只剩 OA/arXiv）。
- **DrissionPage 连不上/默认配置报错**：换独立 user-data-dir；启动前清理残留 chrome 进程和 `SingletonLock`。
- **下载弹"另存为"/"允许下载多个文件"**：prefs（`prompt_for_download=False`、`automatic_downloads=1`）未生效（浏览器没重启）→ 干净重启浏览器。
- **开着代理去下载**：datacenter IP 让 CF 更难过、机构授权失效 → 下载一律关代理走校园网。
- **中文文献**：无海外正版渠道，自动跳过；按需提示用户走知网/维普。

## 关键依赖
查询/调研（search_topic、01）零依赖即可跑；下载需 `pip install openpyxl playwright drissionpage` + 系统 Chrome；`playwright install chromium`（或复用系统 Chrome）。
