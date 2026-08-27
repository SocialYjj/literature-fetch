# 出版社下载路由表 & 直链规律

按 DOI 前缀 / 落地域名判断走哪条正版渠道。**校园网机构 IP 授权 = 用户正常浏览器点"下载 PDF"**，合法。

## 一、机构权限 / OA，headless 直下（阶段 2）

| 出版社 | DOI 前缀 | 落地域名 | PDF 获取方式 |
|---|---|---|---|
| **IEEE**（含落到 Xplore 的 IET/CSEE JPES） | 10.1109 / 10.17775 | ieeexplore.ieee.org | 文章页取 `/document/(arnumber)` → 页内 `fetch("stampPDF/getPDF.jsp?tp=&arnumber=<arn>&ref=")` 取 base64。**机构 IP 命中率极高** |
| **Springer** | 10.1007 | link.springer.com | `https://link.springer.com/content/pdf/{doi}.pdf` |
| **IOP** | 10.1088 | iopscience.iop.org | `article/{doi}/pdf`（注意可能有 PerimeterX，headless 失败就用阶段4的真实浏览器） |
| **ACM** | 10.1145 | dl.acm.org | `https://dl.acm.org/doi/pdf/{doi}` |
| **AIP** | 10.1063 | pubs.aip.org | 读页面 `<meta name="citation_pdf_url">` 的官方直链；PerimeterX 拦非浏览器，**必须走浏览器本身**（curl 403） |
| **Nature** | 10.1038 | nature.com | `{article_url}.pdf`（多为 OA/机构） |
| **RSC** | 10.1039 | pubs.rsc.org | `en/content/articlepdf/{year}/{jrnl}/{doi后缀}`；有反爬，失败走阶段4 |
| **MDPI**(OA) | 10.3390 | mdpi.com | `{article_url}/pdf`（Cloudflare 轻，headless 常失败→有头浏览器 download-capture） |
| **Frontiers/Hindawi**(OA) | 10.3389 / 10.1155 | — | OA 直链 |
| **CPSS**(半开放) | 10.24295 | file.cpss.org.cn | DOI 直接 302 到 `.pdf` 文件，urllib 直下即可 |
| **arXiv**(OA) | 10.48550 | arxiv.org | `arxiv.org/pdf/{id}` |
| **SAGE** | 10.1177 | journals.sagepub.com | `doi/pdf/{doi}`（可能有 CF，失败走阶段4） |

## 二、Cloudflare 反爬，真实浏览器 + 用户手动过验证（阶段 4）

| 出版社 | DOI 前缀 | 域名 | PDF 触发方式 |
|---|---|---|---|
| **Elsevier / ScienceDirect** | 10.1016 | sciencedirect.com | 文章页点带 token 的 `pdfft` 链接（`a[href*=pdfft]`）→ 浏览器自动下载 |
| **Wiley** | 10.1002 | onlinelibrary.wiley.com | `doi/pdfdirect/{doi}?download=true` |
| **IET**（现托管在 Wiley） | 10.1049 | ietresearch.onlinelibrary.wiley.com | 同 Wiley `pdfdirect` |
| **ACS** | 10.1021 | pubs.acs.org | `doi/pdf/{doi}` |
| **MDPI**(OA) | 10.3390 | mdpi.com | 轻量CF：urllib/headless 常被挡（实测 418/挑战页）→ 有头浏览器开文章页后 `{url}/pdf` 锚点下载 |

**要点**：
- 这些站的 Cloudflare Turnstile 会识别"被程序控制的浏览器"，`curl_cffi` 带 cookie 也吃 403 → **只能走真实浏览器本身**。
- DrissionPage 启动的 Chrome 无 `navigator.webdriver` 特征，配合**真人点一次**验证框即过；`cf_clearance` 存进独立配置目录，**同域名后续免验证**，一个会话把该域名全下完。
- 若挂代理（datacenter IP）会让 Turnstile 更难过 → 下载时**关代理走校园网**。

### turnstilePatch 扩展自动过 CF（assets/turnstilePatch，`add_turnstile_patch()` 挂载，全程挂着）
- 原理：内容脚本在 `document_start` 抹掉自动化指纹（webdriver/plugins/languages）+ 轮询自动点 Turnstile 复选框。**不做任何破解**，只是让真实 Chrome 不露自动化马脚，依赖 CF 风控引擎自行放行。
- **只对 CF Turnstile 有效，对 hCaptcha（IOP"我是真实访客"）/reCAPTCHA/文本验证码（OPTICA）无效**——`ensure_access()` 检测到后立即交还用户手动。
- 实测边界（2026-07，Chrome 150 + 校园网）：CF 两种形态——
  - **嵌入式复选框 / 静默挑战**（ACS/Wiley/MDPI/ACM 实测）：扩展自动点/CF 自动放行 → **零点击自动过**。
  - **激进整页挑战**（ScienceDirect）：扩展的**合成点击**被 CF 判为"机器点击"→ 卡"请稍候"；但**用户真人点击仍立刻通过**（15s 实测；CF 认可可信事件，不受扩展无效点击拖累）。
- **最终策略：扩展全程挂着**（`EXT_BACKFIRE` 留空）——能自动过的零点击；过不了的由 `ensure_access` 提示、用户手点必过。真人手点在扩展挂着时依然有效，已实测确认。
- 真正让批量顺畅的是 **cf_clearance 持久化**：某域名过一次后 `_cfprofile` 记住，后续免验证。**别删 `_cfprofile`/`literature-cfprofile`**。

## 三、找不到 DOI 时（阶段 3，谷歌学术）

- 数据库(OpenAlex/CrossRef)按题目匹配不到的，多为：预印本、会议论文、很新、或题目与出版版本略有出入。
- 谷歌学术搜题目 → 第一条的出版社链接常能反推 DOI（`10.xxxx/...`）或落到 IEEE/Elsevier/Wiley 等已知站。
- **网络分工**：谷歌学术在国内通常要代理；下载要校园网。**开代理查链接 → 关代理下载**，两步分开。

## 四、限流自保

- OpenAlex：加 `mailto` 进礼貌池，≤3 并发，429 指数退避。**别开 8+ 并发**，会被封几十分钟。
- Semantic Scholar / 谷歌网页搜索：匿名限流很严，作为备用。
- CrossRef：相对宽松，是补 DOI 的主力备胎。
- arXiv API：`export.arxiv.org/api/query`，控制类/物理类预印本的好来源。

## 五、依赖与环境
```
pip install openpyxl playwright drissionpage
playwright install chromium   # 或让 DrissionPage 复用系统 Chrome
```
Windows 路径含空格/中文无碍；跑前清理残留 chrome 进程与 `_cfprofile/SingletonLock`。

## 六、出版社普查实测（2026-07，某高校校园网；活数据在 route_table.json，用 scripts/probe_publishers.py 可复测）

- **无头可下**（无反爬，机构IP/OA 直通）：IEEE、Springer、Nature（含子刊）、PLOS、Frontiers、arXiv、CPSS、MPCE、**AMS**（文章页 PDF 按钮直下，无任何验证，订阅可用）
- **IOP 特殊：hCaptcha 风控触发型**——平时无头能直下，但按 IP 信誉/频率/浏览器指纹动态弹 hCaptcha（"我是真实访客"，比 CF/reCAPTCHA 都严）；被弹时走有头+用户手点（cleared() 已识别其 apologize 道歉页标题）。⚠️ 各家拦截策略都是动态的，本分类是"主要防线"而非保证，自适应路由会兜底。
- **Cloudflare 拦截 → 有头，多数扩展自动过（ACS/Wiley/MDPI/ACM 实测零点击），少数要真人点一次**：Elsevier、Wiley（10.1002 和 10.1111 两个前缀）、IET、ACS、MDPI、RSC、AIP、APS、ASCE、ASME、ASM、INFORMS、PNAS、Science(AAAS)、Hindawi、SPIE、SAE、T&F、SAGE
- **turnstilePatch 扩展全程挂着（最终定论）**：温和 CF（ACS/Wiley/MDPI/ACM）扩展**零点击自动过**；激进 CF（ScienceDirect）扩展合成点击会卡"请稍候"，但**用户真人手点仍立刻通过**（15s 实测，扩展挂着不影响真人点击有效性）。故不做域名黑名单，扩展全挂 + `ensure_access` 真人兜底。
- **OPTICA 用文本验证码（第 5 种类型）**：opg.optica.org 下 PDF 弹"输入框手打字母"（如 mmdon）+ Submit，**非 CF/hCaptcha/reCAPTCHA**，扩展和 CF 逻辑都不认，**必须真人手输**。route_table 已标 headed+challenge。
- **样本未取到 PDF 多为订购范围问题**（非下载方法问题）：Emerald 样本是 purchase-only 案例研究（标题带🛒，需单独购买）；T&F 校订**仅"科技期刊专辑库"**，人文社科刊（如 Ming Studies）显示 "Content unavailable 此内容在某高校内不可用"——理工科 T&F 正常可下；SPIE/SAE 学校只订电子书。
- **首屏 reCAPTCHA：极少但存在**——文章页反爬 CF 占绝对多数；**例外：ECS 电化学学会（10.1149）用 reCAPTCHA + PerimeterX**（跳 `validate.perfdrive.com`），扩展无效必须真人。此外 reCAPTCHA 多出现在登录表单/图书馆代理入口（EBSCO/ProQuest/校外VPN），校园网 IP 走 DOI 直达一般碰不到
- **验证类型总览（按严格度）**：① CF Turnstile（最常见，扩展多能自动过）② 文本验证码（OPTICA，手输）③ reCAPTCHA+PerimeterX（ECS，必须真人）④ hCaptcha（IOP 风控触发，最严，手点）⑤ WAF 直接 Access Denied（Preprints.org）
- **国内代理平台落地**：SAGE、IOS Press 在国内会落到 `sage.cnpereading.com` 的在线阅读器，需有头点进 viewer 取 PDF

## 七、第二轮出版社扩充实测（2026-08，共 59 家）

**新增无头可下**：Cambridge（10.1017）、De Gruyter（10.1515，落 degruyterbrill.com）、Copernicus/EGU（10.5194，OA）

**新增 CF 拦截 → 有头**：Oxford OUP（10.1093）、World Scientific（10.1142）、Inderscience（10.1504）、SIAM（10.1137）、PeerJ（10.7717）、CSHL bioRxiv/medRxiv（10.1101）、Royal Society（10.1098）、BMJ（10.1136）、JAMA（10.1001）、Wolters Kluwer LWW（10.1097）、Annual Reviews（10.1146）、ASA 声学（10.1121，托管在 pubs.aip.org 同 AIP）

**新增非 CF 的特殊拦截**：
- **ECS 电化学（10.1149）**：reCAPTCHA + PerimeterX → `validate.perfdrive.com`，必须真人
- **JMIR（10.2196）**：Human Verification 页
- **Preprints.org（10.20944）**：WAF 直接 Access Denied

**新增"页面可开但 PDF 在 JS 后"→ 有头**：IOS Press（10.3233，落国内 cnpereading 代理）、Research Square（10.21203）、eLife（10.7554）、Trans Tech/scientific.net（10.4028）、IEICE（10.1587，落 J-Stage）

**SSRN（10.2139）待定**：实测 doi.org 跳转直接连不上（国内直连不通），需代理或去 papers.ssrn.com 手动取。

**踩坑提醒**：普查取样本 DOI 时要校验前缀真属于该社——Annual Reviews 首次抽到的是其科普杂志 Knowable（非正刊），换成含 `annurev` 的正刊 DOI 才测出真实的 CF 拦截。
- **预印本平台**：arXiv（10.48550）无头直下；**Authorea（10.22541，Wiley 旗下）有 Cloudflare → 有头，扩展可过**（实测 2.1MB 成功）。SSRN（10.2139）等同类平台按未知社走"先无头后有头"自适应。
- **检索/平台型库（无 DOI 直达全文，不适用本流程）**：Web of Science、Scopus、EI Compendex、Inspec、JCR、InCites、ESI、SciFinder、MathSciNet、EDS、EBSCO、ProQuest、PQDT、DDS、NSTL、Total Materia 等——这些是"查目录/查指标"，找到目标后仍回到出版社/DOI 渠道下全文
