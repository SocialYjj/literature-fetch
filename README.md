# literature-fetch

一个 Claude Code / Agent Skill：**按题目或 DOI 批量查找、查阅、正版下载学术文献 PDF**。

## 三种用法

| 场景 | 做法 |
|---|---|
| **① 主题调研** | 关键词 → OpenAlex 相关度检索（国内直连免代理）→ 题目/年份/期刊/被引/DOI/摘要清单，很多问题零下载就能答 |
| **② 单篇速查** | 给 DOI 或题目 → 下到临时缓存供 AI 直接读 PDF 讲内容，`--keep` 才正式留档 |
| **③ 批量下载** | 题目清单 xlsx/csv → 逐篇查 DOI、正版下载 → `参考文献/题目.pdf` |

## 安装

依赖两者通用：

```bash
pip install openpyxl playwright drissionpage
playwright install chromium          # 无头下载必需；有头下载走系统 Chrome
```

### Claude Code

克隆进全局 skills 目录，即被自动发现：

```bash
git clone https://github.com/SocialYjj/literature-fetch.git ~/.claude/skills/literature-fetch
```

之后说「下载一批论文 / 按题目找 PDF / 找找关于 X 的论文」或 `/literature-fetch` 即可触发。

### Codex CLI

Codex 支持全局/项目级 skills，克隆进对应目录：

```bash
# 全局（所有项目可用）
git clone https://github.com/SocialYjj/literature-fetch.git ~/.codex/skills/literature-fetch
# 或项目级
git clone https://github.com/SocialYjj/literature-fetch.git .codex/skills/literature-fetch
```

本 skill 本质是「`SKILL.md` 说明 + `scripts/` 纯 Python 脚本」，与具体 Agent 无关；若你的 Agent 没有 skills 目录约定，克隆到任意位置、让它读 `SKILL.md` 按流程调用脚本即可。

## 快速开始

```bash
# 主题检索（零下载）
python scripts/search_topic.py "quantum computing power system" --n 15 --from 2020

# 单篇速查/下载
python scripts/fetch_one.py 10.1109/TII.2023.3241234          # 下到临时缓存供阅读
python scripts/fetch_one.py "论文完整题目" --keep              # 正式留档到 参考文献/

# 批量流程（在一个工作目录里，含题目清单 xlsx）
python scripts/00_import_list.py 清单.xlsx      # → manifest.json
python scripts/01_resolve_doi.py                # 查 DOI + OA 直链
python scripts/02_download_institutional.py     # 无头下载(校园网直连)
python scripts/03_search_scholar.py             # (可选)谷歌学术补 DOI，需代理
python scripts/04_download_cloudflare.py        # 有头下载(CF反爬社)，扩展自动过/真人兜底
python scripts/05_collect.py                    # 整理成 参考文献/题目.pdf
```

## 工作原理

- **自适应路由**（`references/route_table.json`）：按 DOI 前缀记每家出版社走无头还是有头，**随运行结果自学习**，拷到新电脑经验带着走。已内置 **58 家**实测分类（IEEE/Elsevier/Springer/Wiley/Nature/ACS/RSC/AIP/APS/Cambridge/Oxford/SIAM/BMJ/JAMA… 及 arXiv/bioRxiv/Research Square/Authorea 等预印本平台）。
- **无头优先**：IEEE/Springer/Nature/AMS/Emerald… 机构 IP 直下，快、不打扰。
- **有头兜底**：Cloudflare 反爬社（Elsevier/Wiley/ACS…）用真实 Chrome + `assets/turnstilePatch` 扩展：温和 CF 零点击自动过，激进 CF（ScienceDirect）由用户真人点一次；`cf_clearance` 存 `_cfprofile`，同域名后续免验证。
- **验证类型**：CF Turnstile（最常见，扩展多能自动过）> 文本验证码（OPTICA）> reCAPTCHA+PerimeterX（ECS）> hCaptcha（IOP，最严）——后三种交用户手动。

详见 `SKILL.md`（完整流程与决策逻辑）和 `references/publishers.md`（各出版社路由表 + 实测普查）。

## 目录结构

```
literature-fetch/
├── SKILL.md                      # 主指南：正版原则 / 三种用法 / 5 阶段流程 / CF 处理
├── references/
│   ├── publishers.md             # 各出版社 PDF 直链规律 + 验证类型普查
│   └── route_table.json          # 自学习路由表（无头/有头/验证类型）
├── assets/turnstilePatch/        # CF Turnstile 辅助扩展（抹指纹+自动点；不做破解）
└── scripts/
    ├── lib.py                    # 共享库：路由/下载核心/限流/文件名/表头探测
    ├── 00_import_list.py         # 清单 → manifest
    ├── 01_resolve_doi.py         # OpenAlex+CrossRef 查 DOI（防 429）
    ├── 02_download_institutional.py  # 无头：机构权限+OA
    ├── 03_search_scholar.py      # 谷歌学术补 DOI（需代理）
    ├── 04_download_cloudflare.py # 有头：CF 反爬社
    ├── 05_collect.py             # 收尾整理
    ├── search_topic.py           # 主题/关键词检索
    ├── fetch_one.py              # 单篇速查/速取
    └── probe_publishers.py       # 出版社普查探针（复测/加新社）
```

## 免责声明

本工具仅用于访问**用户本人拥有合法权限**的学术内容（机构订阅、开放获取）。使用者须遵守所在机构的资源使用条款与各出版社的服务协议。作者不对任何越权或违规使用负责。
