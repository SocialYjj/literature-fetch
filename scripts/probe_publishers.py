# -*- coding: utf-8 -*-
"""出版社普查探针：每家一个样本DOI，无头访问，分类：无头OK / 拦截(CF/reCAPTCHA/PerimeterX/DataDome) / 无拦截但没取到。
结果写入 skill 的 route_table.json。用法: python probe_publishers.py <组号 1|2a|2b|3 或 10.xxxx 前缀 [名称]>"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
import lib
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse

GROUPS = {
 '1':  [('10.1063', 'AIP'), ('10.1103', 'APS'), ('10.1061', 'ASCE'), ('10.1115', 'ASME'),
        ('10.1128', 'ASM'), ('10.1090', 'AMS'), ('10.1287', 'INFORMS')],
 '2a': [('10.1108', 'Emerald'), ('10.1364', 'OPTICA'), ('10.1073', 'PNAS'),
        ('10.1039', 'RSC'), ('10.4271', 'SAE')],
 '2b': [('10.1126', 'Science'), ('10.1117', 'SPIE'), ('10.1080', 'T-F'),
        ('10.1177', 'SAGE'), ('10.1088', 'IOP')],
 '3':  [('10.1371', 'PLOS'), ('10.3389', 'Frontiers'), ('10.1155', 'Hindawi')],
 '3b': [('10.3389', 'Frontiers'), ('10.1155', 'Hindawi')],
}
KNOWN = {'10.1063': '10.1063/5.0206472', '10.1039': '10.1039/d3ta01736b',
         '10.1177': '10.1177/09596518251341923', '10.1088': '10.1088/1361-6463/acd64a'}
CONTAINER = {'10.3389': 'Frontiers in Psychology', '10.1155': 'Mathematical Problems in Engineering'}

def sample_doi(prefix):
    if prefix in KNOWN: return KNOWN[prefix]
    import urllib.parse as up
    tries = []
    if prefix in CONTAINER:
        tries.append(f"https://api.crossref.org/works?query.container-title={up.quote(CONTAINER[prefix])}"
                     f"&rows=20&select=DOI&mailto={lib.CFG['mailto']}")
    for filt in (',type:journal-article,from-pub-date:2019-01-01', ''):
        tries.append(f"https://api.crossref.org/works?filter=prefix:{prefix}{filt}"
                     f"&rows=20&select=DOI&mailto={lib.CFG['mailto']}")
    for u in tries:
        try:
            items = lib.fetch_json(u).get('message', {}).get('items', [])
            for it in items:   # 客户端校验：DOI 必须真以该前缀开头（防期刊转移的属主混淆）
                if it['DOI'].startswith(prefix + '/'): return it['DOI']
        except Exception:
            continue
    return None

def classify(html, title):
    h = html.lower(); t = (title or '').lower()
    marks = []
    if 'px-captcha' in h or 'perimeterx' in h or 'press & hold' in h or 'press and hold' in h: marks.append('PerimeterX')
    if 'cf-turnstile' in h or '__cf_chl' in h or 'challenge-platform' in h or 'just a moment' in t or '请稍候' in (title or ''): marks.append('Cloudflare')
    if 'datadome' in h: marks.append('DataDome')
    if 'g-recaptcha' in h or 'grecaptcha' in h or 'recaptcha' in h: marks.append('reCAPTCHA')
    return marks

def probe(page, prefix, name, rt):
    doi = sample_doi(prefix)
    if not doi: return {'name': name, 'doi': '-', 'st': '找不到样本DOI', 'host': ''}
    r = {'name': name, 'doi': doi, 'host': ''}
    try:
        page.goto(f"https://doi.org/{doi}", wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        r['st'] = f'打不开({str(e)[:25]})'; return r
    page.wait_for_timeout(2500)
    r['host'] = urlparse(page.url).netloc
    title = page.title() or ''
    try: html = page.content()[:300000]
    except Exception: html = ''
    marks = classify(html, title)
    tl = title.lower()
    blockpage = ('moment' in tl or '请稍候' in title or 'captcha' in tl or 'denied' in tl
                 or 'not a robot' in html.lower()[:8000] or len(html) < 15000)
    data = None
    if not blockpage:
        for u in lib.pdf_candidates(page.url, doi, page):
            data = lib.fetch_pdf(page, u)
            if data: break
    if data:
        r['st'] = f'无头OK({len(data)//1024}KB)'
        lib.record_route(doi, 'hl_ok', rt, name=name)
    elif blockpage and marks:
        r['st'] = '拦截:' + '+'.join(marks)
        lib.record_route(doi, 'hl_challenge', rt, name=name)
        rt[lib._registrant(doi)]['challenge'] = '+'.join(marks)   # 用DOI实际前缀(可能≠查询前缀)
    elif blockpage:
        r['st'] = '拦截:类型未识别(标题=' + title[:20] + ')'
        lib.record_route(doi, 'hl_challenge', rt, name=name)
    else:
        note = ('页面含' + '+'.join(marks) + '组件') if marks else '可能无订阅/规律缺口'
        r['st'] = f'页面能开但无头没取到PDF({note})'
        lib.record_route(doi, 'hl_fail', rt, name=name)
    return r

def main():
    g = sys.argv[1] if len(sys.argv) > 1 else '1'
    rt = lib.load_routes()
    if g.startswith('10.'):   # 单前缀模式: probe_publishers.py 10.xxxx [名称]
        GROUPS[g] = [(g, sys.argv[2] if len(sys.argv) > 2 else g)]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = b.new_context(user_agent=lib.UA, viewport={'width': 1280, 'height': 900}).new_page()
        for prefix, name in GROUPS[g]:
            r = probe(page, prefix, name, rt)
            print(f"{r['name']:9s} {r['doi']:36s} -> {r['st']}  [{r['host']}]", flush=True)
            time.sleep(2)
        b.close()
    lib.save_routes(rt)
    print('组', g, '完成，路由表已更新')

if __name__ == '__main__':
    main()
