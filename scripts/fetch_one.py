# -*- coding: utf-8 -*-
"""工具·单篇快速获取（调研第2层 / 单篇留档）。输入 DOI 或论文题目。
默认【查阅模式】：PDF 下到系统临时缓存并打印路径（AI 用 Read 工具直接读它讲内容），不污染工作目录；
加 --keep 才复制到 参考文献\\题目.pdf 正式留档。

获取策略（自适应路由）：
  查路由表(references/route_table.json) → 已知 headless：OA 白名单直下 → headless 机构渠道；
  已知 headed（反爬社）：不浪费时间，提示加 --headed；未知出版社：先无头试，结果回写路由表。
  --headed：起有头真实 Chrome(DrissionPage)，遇人机验证【等用户手动点一次】；下载走页内 fetch
  （不经过 Chrome 下载子系统：不弹另存为/多文件确认，IDM 等下载器也截不走），锚点下载仅兜底。
用法:
  python fetch_one.py 10.1109/TII.2023.3241234
  python fetch_one.py "论文完整题目" [--keep] [--headed]"""
import sys, os, re, time, tempfile, shutil, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (CFG, fetch_json, sanitize, clean_query, pick_best, inv_abstract,
                 oa_direct, grab_via_doi, route_mode, record_route, UA, is_pdf,
                 dp_fetch_pdf, same_host, dismiss_consent, add_turnstile_patch, ensure_access)
sys.stdout.reconfigure(encoding='utf-8')

CACHE = os.path.join(tempfile.gettempdir(), "literature-cache")
os.makedirs(CACHE, exist_ok=True)
MAILTO = CFG["mailto"]

def openalex_work(query):
    """DOI 或题目 -> (OpenAlex work, 相似度)。"""
    if re.match(r'^10\.\d{4,9}/\S+$', query):
        try:
            return fetch_json(f"https://api.openalex.org/works/doi:{urllib.parse.quote(query)}?mailto={MAILTO}"), 1.0
        except Exception:
            return {'doi': 'https://doi.org/' + query}, 1.0   # OpenAlex 未收录也无妨，DOI 本身够路由
    for q in (query, clean_query(query)):
        try:
            d = fetch_json(f"https://api.openalex.org/works?filter=title.search:{urllib.parse.quote(q)}"
                           f"&per-page=5&mailto={MAILTO}")
            if d.get('results'):
                return pick_best(query, d['results'])
        except Exception:
            continue
    return None, 0.0

def headless_grab(doi):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = b.new_context(user_agent=UA).new_page()
        st, data = grab_via_doi(page, doi)
        b.close()
    return st, data

def headed_grab(doi):
    """有头真实 Chrome：开文章页 → 遇人机验证等用户手点 → 页内 fetch 取 PDF（锚点兜底）。"""
    from DrissionPage import ChromiumPage, ChromiumOptions
    dl = os.path.join(tempfile.gettempdir(), "literature-dl"); os.makedirs(dl, exist_ok=True)
    co = ChromiumOptions()
    for pth in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe']:
        if os.path.exists(pth): co.set_paths(browser_path=pth); break
    co.set_user_data_path(os.path.join(tempfile.gettempdir(), "literature-cfprofile"))  # 非默认目录+cf_clearance持久化
    co.set_download_path(dl); co.set_argument('--window-size=1250,950')
    co.set_pref('download.default_directory', dl)   # 必须设原生偏好：仅 set_download_path 时锚点下载会落到系统默认"下载"目录
    co.set_pref('plugins.always_open_pdf_externally', True)
    co.set_pref('download.prompt_for_download', False)
    co.set_pref('profile.default_content_setting_values.automatic_downloads', 1)  # 不弹"允许下载多个文件"
    add_turnstile_patch(co, doi)   # 扩展全程挂着：能自动过CF最好；过不了(如SD)用户手点仍有效
    page = ChromiumPage(co)
    def wait_pdf(before, timeout=55):
        for _ in range(timeout):
            time.sleep(1); cur = os.listdir(dl)
            if any(f.endswith('.crdownload') for f in cur): continue
            for f in cur:
                if f.endswith('.pdf') and f not in before:
                    fp = os.path.join(dl, f)
                    if os.path.getsize(fp) > 20000 and open(fp, 'rb').read(4) == b'%PDF':
                        data = open(fp, 'rb').read()
                        try: os.remove(fp)
                        except Exception: pass
                        return data
        return None
    def anchor_fallback(u):
        before = set(os.listdir(dl))
        try:
            page.run_js('const a=document.createElement("a");a.href=arguments[0];a.download="";'
                        'document.body.appendChild(a);a.click();', u)
        except Exception:
            return None
        return wait_pdf(before)
    try:
        page.get(f"https://doi.org/{doi}"); time.sleep(3)
        # 第一步：确保过验证（扩展自动过CF → 失败提示转人工 → 死循环则本篇跳过）
        if not ensure_access(page, tag=doi.split('/')[0], manual_secs=180):
            return None
        dismiss_consent(page)   # 自动关掉 Cookie 同意横幅（合规弹窗，非人机验证）
        reg = doi.split('/')[0]
        if reg == '10.1016':
            # SD 的 pdfft 是 HTML 中转页：必须真实点击/导航才会跳到真 PDF（fetch/带download属性的锚点只会拿到 HTML）
            el = page.ele('x://a[contains(@href,"pdfft")]', timeout=6)
            if not el: return None   # 无 View PDF = 无权限；不要乱试页面其他链接（多为相关文章的PDF）
            href = (el.attr('href') or '').split('#')[0]
            before = set(os.listdir(dl))
            try: el.click(by_js=None)
            except Exception: pass
            data = wait_pdf(before)
            if not data and href:
                if href.startswith('/'): href = 'https://www.sciencedirect.com' + href
                before = set(os.listdir(dl))
                try: page.get(href)
                except Exception: pass
                data = wait_pdf(before)
            return data
        # 其余出版社：候选 = 专用直链 > citation_pdf_url > {文章页}/pdf > 本站且与本文相关的扫描链接
        cands = []
        if reg in ('10.1002', '10.1049'):
            base = 'ietresearch.onlinelibrary.wiley.com' if reg == '10.1049' else 'onlinelibrary.wiley.com'
            cands.append(f"https://{base}/doi/pdfdirect/{doi}?download=true")
        elif reg == '10.1021':
            cands.append(f"https://pubs.acs.org/doi/pdf/{doi}")
        elif reg == '10.1145':
            cands.append(f"https://dl.acm.org/doi/pdf/{doi}")
        try:
            cp = page.run_js('return document.querySelector(\'meta[name="citation_pdf_url"]\')?.content||null;')
            if cp and cp not in cands: cands.append(cp)
        except Exception: pass
        cands.append(page.url.split('?')[0].rstrip('/') + '/pdf')
        try:
            hs = page.run_js('return [...document.querySelectorAll("a")].map(a=>a.href)'
                             '.filter(h=>h&&/pdfft|pdfdirect|article-pdf|\\.pdf(\\?|$)|\\/pdf(\\/|\\?|$)/i.test(h)).slice(0,8);')
            pbase = page.url.split('?')[0].rstrip('/')
            rel = lambda h: h.startswith(pbase) or (doi.lower() in urllib.parse.unquote(h).lower())
            cands += [h for h in (hs or []) if h not in cands and same_host(h, page.url) and rel(h)]  # 防下到相关文章/参考文献
        except Exception: pass
        for u in cands:
            if not u: continue
            if u.startswith('/'):
                pu = urllib.parse.urlparse(page.url); u = f"{pu.scheme}://{pu.netloc}{u}"
            data = dp_fetch_pdf(page, u) or anchor_fallback(u)
            if data and is_pdf(data): return data
        return None
    finally:
        try: page.quit()
        except Exception: pass

def main():
    pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    keep = '--keep' in sys.argv; headed = '--headed' in sys.argv
    if not pos:
        print(__doc__); return
    w, s = openalex_work(pos[0])
    if not w or (s < 0.55 and not w.get('doi')):
        print("未找到该论文（低相似度/无结果）。可换措辞重试，或用 03_search_scholar.py 谷歌学术兜底。"); return
    doi = (w.get('doi') or '').replace('https://doi.org/', '') or None
    title = w.get('display_name') or pos[0]
    mode = route_mode(doi) if doi else 'unknown'
    print(f"匹配: {title}")
    print(f"  DOI: {doi or '无'} | 年份: {w.get('publication_year')} | 被引: {w.get('cited_by_count')} | 相似度: {round(s, 2)} | 路由: {mode}")
    dst = os.path.join(CACHE, sanitize((doi or title).replace('/', '_'))[:100] + ".pdf")
    if os.path.exists(dst) and os.path.getsize(dst) > 20000:
        print(f"命中缓存: {dst}")
    else:
        # 1) OA 副本（best_oa_location + 各 location，白名单直下，与出版社反爬无关）
        urls = [(w.get('best_oa_location') or {}).get('pdf_url')]
        for loc in (w.get('locations') or []):
            u = loc.get('pdf_url')
            if u and u not in urls: urls.append(u)
        data = oa_direct(urls); src = 'OA副本'
        # 2) 按路由表升级：headless / headed
        if not data and doi:
            if mode != 'headed':                     # headless 或 unknown：先无头
                try:
                    st, data = headless_grab(doi)
                except Exception as e:
                    st, data = f'err:{str(e)[:40]}', None
                if data:
                    record_route(doi, 'hl_ok'); src = '机构/出版社(无头)'
                elif st in ('skip_cf', 'challenge'):
                    record_route(doi, 'hl_challenge'); mode = 'headed'
                    print(f"  无头遇反爬({st})，已记入路由表：该社需有头。")
                else:
                    record_route(doi, 'hl_fail')
                    print(f"  无头未取到({st})。可能非校园网无授权；也可再试 --headed。")
            if not data and (mode == 'headed' or headed):
                if headed:
                    print("  起有头 Chrome（遇验证请手动点一次）...", flush=True)
                    data = headed_grab(doi)
                    if data: record_route(doi, 'hd_ok'); src = '有头浏览器'
                    else: print("  有头也未取到（无权限/无该文入口）。")
                else:
                    print("  该社需有头浏览器。加 --headed 重跑（会弹 Chrome 窗口，遇验证你手动点一次）。")
        if data:
            open(dst, 'wb').write(data)
            print(f"已下到缓存({src}): {dst}")
    if not (os.path.exists(dst) and os.path.getsize(dst) > 20000):
        ab = inv_abstract(w.get('abstract_inverted_index'))
        print(f"\nPDF 未获取。摘要：\n{ab}" if ab else "\nPDF 未获取，OpenAlex 也无摘要。")
        return
    if keep:
        outdir = CFG["pdf_dir"]; os.makedirs(outdir, exist_ok=True)
        final = os.path.join(outdir, sanitize(title)[:120] + ".pdf")
        shutil.copyfile(dst, final)
        print(f"已留档: {final}")
    else:
        print("（查阅模式：用 Read 工具直接读上面的缓存 PDF；要留档就加 --keep 重跑，或把缓存文件复制进 参考文献 目录）")

if __name__ == '__main__':
    main()
