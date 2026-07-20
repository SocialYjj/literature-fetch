# -*- coding: utf-8 -*-
"""阶段4：有头下载（反爬出版社：路由表 headed + 阶段2升级的）。
真实 Chrome(DrissionPage) + 遇人机验证等用户手动点一次/每域名；cf_clearance 存独立配置目录，同域名后续免验证。
下载方式：优先页内 fetch 取字节流（不走 Chrome 下载子系统——不弹另存为/多文件确认，IDM 等下载器也截不走），
锚点下载仅兜底。扫描页面链接只认与文章页同域名的，防止把参考文献 PDF 当正文下载。
用法: python 04_download_cloudflare.py [lo hi]"""
import sys, os, time, shutil, random, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (CFG, load_manifest, have, is_pdf, load_routes, save_routes, route_mode,
                 record_route, dp_fetch_pdf, same_host, dismiss_consent, add_turnstile_patch,
                 ensure_access, cleared_title, use_turnstile)
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions

RAW = CFG["raw_dir"]; DL = "_dl_tmp"; PROFILE = os.path.abspath("_cfprofile")
os.makedirs(RAW, exist_ok=True); os.makedirs(DL, exist_ok=True)
for f in os.listdir(DL):
    if f.endswith(('.pdf', '.crdownload')):
        try: os.remove(os.path.join(DL, f))
        except: pass

def chrome_path():
    for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe']:
        if os.path.exists(p): return p
    return None

page = None   # 由 main() 按分组建立(挂/不挂扩展)
def build_page(use_ext):
    """建有头浏览器；use_ext 决定是否挂 turnstilePatch（黑名单站如 ScienceDirect 不挂）。"""
    co = ChromiumOptions()
    cp = chrome_path()
    if cp: co.set_paths(browser_path=cp)
    co.set_user_data_path(PROFILE)               # 独立目录：新版 Chrome 禁止默认目录开调试端口
    co.set_download_path(os.path.abspath(DL))
    co.set_argument('--window-size=1250,950')
    co.set_pref('plugins.always_open_pdf_externally', True)   # PDF 强制下载不预览
    co.set_pref('download.prompt_for_download', False)        # 不弹另存为
    co.set_pref('download.default_directory', os.path.abspath(DL))
    co.set_pref('profile.default_content_setting_values.automatic_downloads', 1)  # 不弹"允许下载多个文件"
    if use_ext: add_turnstile_patch(co)          # CF Turnstile 自动过(抹指纹+自动点)，只 hCaptcha 才需真人
    return ChromiumPage(co)

def wait_user_cf(tag, secs=240):
    # 统一"第一步：确保过验证 + 人工兜底"（扩展自动过CF→失败提示转人工→死循环则跳过）
    return ensure_access(page, tag, manual_secs=secs)

def wait_dl(before, timeout=55):
    for _ in range(timeout):
        time.sleep(1); cur = os.listdir(DL)
        if any(f.endswith('.crdownload') for f in cur): continue
        new = [f for f in cur if f.endswith('.pdf') and f not in before]
        if new:
            p = os.path.join(DL, new[0])
            if os.path.getsize(p) > 20000:
                with open(p, 'rb') as fh:
                    if fh.read(4) == b'%PDF': return p
    return None

def anchor_dl(url):
    before = set(os.listdir(DL))
    try:
        page.run_js('const a=document.createElement("a");a.href=arguments[0];a.download="";'
                    'document.body.appendChild(a);a.click();', url)
    except Exception: return None
    return wait_dl(before, 55)

def get_pdf(url):
    """页内 fetch 优先（IDM截不走、无弹窗）；失败再锚点下载兜底。返回 bytes|None。"""
    if not url: return None
    if url.startswith('/'):
        from urllib.parse import urlparse
        pu = urlparse(page.url); url = f"{pu.scheme}://{pu.netloc}{url}"
    b = dp_fetch_pdf(page, url)
    if b: return b
    p = anchor_dl(url)
    if p:
        data = open(p, 'rb').read()
        try: os.remove(p)
        except: pass
        return data if is_pdf(data) else None
    return None

def save(num, data):
    with open(os.path.join(RAW, f"{num}.pdf"), 'wb') as f: f.write(data)

def download(num, doi):
    if have(num): return 'cached'
    reg = doi.split('/')[0]
    # 先开文章页(过反爬)
    if reg == '10.1016':                 # Elsevier：pdfft 是HTML中转页 → 必须真实点击/导航（fetch/download锚点只会拿到HTML）
        page.get(f"https://doi.org/{doi}"); time.sleep(3)
        if not wait_user_cf(f"Elsevier {num}"): return 'cf_fail'
        el = page.ele('x://a[contains(@href,"pdfft")]', timeout=6)
        if not el: return 'no_pdf_link'   # 无 View PDF = 无权限；不乱试其他链接(多为相关文章)
        href = (el.attr('href') or '').split('#')[0]
        before = set(os.listdir(DL))
        try: el.click(by_js=None)
        except Exception: pass
        p = wait_dl(before, 55)
        if not p and href:
            if href.startswith('/'): href = 'https://www.sciencedirect.com' + href
            before = set(os.listdir(DL))
            try: page.get(href)
            except Exception: pass
            p = wait_dl(before, 55)
        if p: shutil.move(p, f"{RAW}/{num}.pdf"); return 'ok'
        return 'no_file'
    elif reg in ('10.1002', '10.1049'):  # Wiley / IET
        base = 'ietresearch.onlinelibrary.wiley.com' if reg == '10.1049' else 'onlinelibrary.wiley.com'
        page.get(f"https://{base}/doi/{doi}"); time.sleep(3)
        if not wait_user_cf(f"Wiley {num}"): return 'cf_fail'
        data = get_pdf(f"https://{base}/doi/pdfdirect/{doi}?download=true")
        if data: save(num, data); return 'ok'
        return 'no_file'
    elif reg == '10.1021':               # ACS
        page.get(f"https://pubs.acs.org/doi/{doi}"); time.sleep(3)
        if not wait_user_cf(f"ACS {num}"): return 'cf_fail'
        data = get_pdf(f"https://pubs.acs.org/doi/pdf/{doi}")
        if data: save(num, data); return 'ok'
        return 'no_file'
    elif reg == '10.3390':               # MDPI（OA 但轻量CF挡无头；真实Chrome页内fetch即可）
        page.get(f"https://doi.org/{doi}"); time.sleep(3)
        if not wait_user_cf(f"MDPI {num}"): return 'cf_fail'
        data = get_pdf(page.url.split('?')[0].rstrip('/') + "/pdf")
        if data: save(num, data); return 'ok'
        return 'no_file'
    # 通用有头兜底（路由表判 headed 的新出版社）：开文章页→等验证→citation_pdf_url/本站PDF链接
    page.get(f"https://doi.org/{doi}"); time.sleep(3)
    if not wait_user_cf(f"{reg} {num}"): return 'cf_fail'
    cands = []
    if reg == '10.1145': cands.append(f"https://dl.acm.org/doi/pdf/{doi}")   # ACM: pdf 在路径中段
    try:
        cp2 = page.run_js('return document.querySelector(\'meta[name="citation_pdf_url"]\')?.content||null;')
        if cp2 and cp2 not in cands: cands.append(cp2)
    except Exception: pass
    cands.append(page.url.split('?')[0].rstrip('/') + '/pdf')
    try:
        hs = page.run_js('return [...document.querySelectorAll("a")].map(a=>a.href)'
                         '.filter(h=>h&&/pdfft|pdfdirect|article-pdf|\\.pdf(\\?|$)|\\/pdf(\\/|\\?|$)/i.test(h)).slice(0,8);')
        pbase = page.url.split('?')[0].rstrip('/')
        rel = lambda h: h.startswith(pbase) or (doi.lower() in urllib.parse.unquote(h).lower())
        cands += [h for h in (hs or []) if h not in cands and same_host(h, page.url) and rel(h)]  # 本站+与本文相关，防下到相关文章/参考文献
    except Exception: pass
    for u in cands:
        data = get_pdf(u)
        if data: save(num, data); return 'ok'
    return 'no_file'

def run_group(todo, use_ext, rt):
    """在一个浏览器(挂/不挂扩展)里把一组论文下完。返回成功数。"""
    global page
    if not todo: return 0
    page = build_page(use_ext)
    tag = "挂扩展" if use_ext else "不挂扩展(黑名单站)"
    print(f"\n--- {tag} 组：{len(todo)} 篇 ---", flush=True)
    ok = 0
    for i, r in enumerate(todo):
        try: st = download(r['num'], r['doi'])
        except Exception as e: st = f'err:{str(e)[:30]}'
        if st in ('ok', 'cached'): ok += 1
        if st == 'ok': record_route(r['doi'], 'hd_ok', rt)
        print(f"{'OK ' if st in ('ok','cached') else '   '}({r['num']}) {st} [{i+1}/{len(todo)}] {r['doi']}", flush=True)
        time.sleep(random.uniform(2, 4))
    time.sleep(6)
    try: page.quit()
    except: pass
    return ok

def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
    m = load_manifest(); rt = load_routes()
    todo = sorted([r for r in m if r.get('doi') and lo <= r['num'] <= hi and not have(r['num'])
                   and not r.get('skip')
                   and (route_mode(r['doi'], rt) == 'headed' or r.get('route') == 'headed')],
                  key=lambda r: (r['doi'].split('/')[0], r['num']))   # 同域名相邻，一次验证下完
    # 拆两组：黑名单站(ScienceDirect)不挂扩展(挂了反死循环)，其余挂扩展自动过CF
    ext_todo   = [r for r in todo if use_turnstile(r['doi'])]
    noext_todo = [r for r in todo if not use_turnstile(r['doi'])]
    print(f"有头下载 {len(todo)} 篇（挂扩展 {len(ext_todo)} + 不挂 {len(noext_todo)}）。首遇域名可能要你手动过一次验证。", flush=True)
    ok = run_group(ext_todo, True, rt)          # 先挂扩展组（ACS/Wiley/MDPI… 多自动过）
    ok += run_group(noext_todo, False, rt)      # 再不挂扩展组（ScienceDirect 靠原生过CF）
    save_routes(rt)
    print(f"\n完成: {ok}/{len(todo)}")

if __name__ == '__main__':
    main()
