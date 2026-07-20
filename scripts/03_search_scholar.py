# -*- coding: utf-8 -*-
"""阶段3(可选)：谷歌学术补 DOI（阶段1找不到 DOI 的英文论文）。真实 Chrome(DrissionPage)。
⚠️ 网络分工：谷歌学术常需【代理】；机构下载需【校园网直连】。二者互斥！
   正确姿势：开代理→本脚本只查链接/DOI(不下载)→关代理→再跑 02/04 下载。
用法: python 03_search_scholar.py"""
import sys, os, time, re, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load_manifest, save_manifest, is_cn
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions

def chrome_path():
    for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe']:
        if os.path.exists(p): return p
co = ChromiumOptions()
cp = chrome_path()
if cp: co.set_paths(browser_path=cp)
co.set_user_data_path(os.path.abspath("_cfprofile"))
co.set_argument('--window-size=1250,950')
page = ChromiumPage(co)

def scholar_ok():
    h = (page.html or '').lower(); u = page.url.lower()
    return 'scholar.google' in u and 'sorry' not in u and 'captcha' not in h and 'unusual traffic' not in h
def wait_scholar(secs=180):
    if scholar_ok(): return True
    print(">>> 谷歌学术出现验证，请手动过一下 <<<", flush=True)
    for _ in range(secs // 2):
        time.sleep(2)
        if scholar_ok(): return True
    return scholar_ok()

def search(title):
    page.get("https://scholar.google.com/scholar?q=" + urllib.parse.quote(title)); time.sleep(3)
    if not wait_scholar(): return None
    try: items = page.eles('css:div.gs_ri', timeout=6)[:2]
    except Exception: items = []
    for it in items:
        d = {'t': '', 'art': None, 'pdf': None}
        try:
            a = it.ele('css:h3.gs_rt a', timeout=1)
            if a: d['t'] = a.text; d['art'] = a.attr('href')
        except: pass
        try:
            pa = it.ele('css:div.gs_ggs a', timeout=1)
            if pa: d['pdf'] = pa.attr('href')
        except: pass
        doi = None
        for c in [d['art'] or '', d['pdf'] or '']:
            mm = re.search(r'10\.\d{4,9}/[^\s?&#"\'<>]+', urllib.parse.unquote(c))
            if mm: doi = mm.group(0).rstrip('.'); break
        return {**d, 'doi': doi}
    return None

def main():
    m = load_manifest(); by = {r['num']: r for r in m}
    todo = [r for r in m if not r.get('doi') and not r.get('skip') and not is_cn(r.get('excel_title', ''))]
    print(f"谷歌学术补 DOI：{len(todo)} 篇（仅英文、无DOI）。⚠️记得开代理。", flush=True)
    for r in todo:
        res = search(r['excel_title'])
        print(f"\n({r['num']}) {r['excel_title'][:50]}", flush=True)
        if not res:
            print("   无结果/被拦", flush=True); continue
        print(f"   命中: {res['t'][:50]}\n   文章: {res['art']}\n   PDF: {res['pdf']}\n   DOI: {res['doi']}", flush=True)
        if res.get('doi'): by[r['num']]['doi'] = res['doi']
        # 记录发现的出版社/[PDF]链接：多为机构库/作者主页的绿色OA副本，02 会尝试直下
        by[r['num']]['found'] = {'art': res['art'], 'pdf': res['pdf']}
        time.sleep(3)
    save_manifest([by[k] for k in sorted(by)])
    print("\n完成。关代理回校园网后：重跑 02（用新 DOI/直链下载）；CF 出版社(Elsevier/Wiley/ACS/IET)的跑 04。", flush=True)
    try: page.quit()
    except: pass

if __name__ == '__main__':
    main()
