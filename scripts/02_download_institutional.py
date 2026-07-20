# -*- coding: utf-8 -*-
"""阶段2：机构权限 + OA 正版下载（无头）。headless Playwright，走校园网 IP（关代理）。
路由自学习：先查 references/route_table.json——已知 headed 的直接跳给04不浪费时间；
headless/未知的先无头试，结果回写路由表（成功=headless；遇反爬挑战=headed），逐步完善。
用法: python 02_download_institutional.py [lo hi]"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (CFG, load_manifest, save_manifest, have, UA, oa_direct, grab_via_doi,
                 load_routes, save_routes, route_mode, record_route)
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

RAW = CFG["raw_dir"]; os.makedirs(RAW, exist_ok=True)

def save(num, data):
    with open(os.path.join(RAW, f"{num}.pdf"), "wb") as f: f.write(data)

def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
    m = load_manifest(); rt = load_routes()
    todo = [r for r in m if lo <= r['num'] <= hi and not have(r['num']) and not r.get('skip')
            and (r.get('doi') or r.get('oa_url') or (r.get('found') or {}).get('pdf'))]
    print(f"机构/OA下载 {len(todo)} 篇 (headless, 校园网直连; 已知需有头的按路由表跳过)...", flush=True)
    ok = 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        ctx = b.new_context(user_agent=UA, viewport={'width': 1280, 'height': 900}, accept_downloads=True)
        page = ctx.new_page()
        for i, r in enumerate(todo):
            doi = r.get('doi') or ''
            slow = True   # 是否真动了网络（决定要不要 sleep）
            try:
                data = oa_direct([r.get('oa_url'), (r.get('found') or {}).get('pdf')])
                if data:
                    save(r['num'], data); st = 'ok_direct'
                elif not doi:
                    st = 'no_doi'; slow = False
                elif route_mode(doi, rt) == 'headed':
                    st = 'headed(表)'; r['route'] = 'headed'; slow = False
                else:
                    st, data = grab_via_doi(page, doi)
                    if data:
                        save(r['num'], data); record_route(doi, 'hl_ok', rt)
                    elif st in ('skip_cf', 'challenge'):
                        record_route(doi, 'hl_challenge', rt); r['route'] = 'headed'
                    elif st == 'fail':
                        record_route(doi, 'hl_fail', rt)   # 原因不明(可能无权限)，不改判 headed
            except Exception as e:
                st = f'err:{str(e)[:30]}'
            if st.startswith('ok'): ok += 1
            print(f"{'OK ' if st.startswith('ok') else '   '}({r['num']}) {st} [{i+1}/{len(todo)}] {doi or (r.get('oa_url') or '')[:50]}", flush=True)
            if slow: time.sleep(1.2)
        ctx.close(); b.close()
    save_routes(rt); save_manifest(m)
    hd = sum(1 for r in todo if r.get('route') == 'headed')
    print(f"\n完成: {ok}/{len(todo)} | 待有头(脚本04): {hd} | 无DOI待补查(脚本03): {sum(1 for r in todo if not r.get('doi'))}")

if __name__ == '__main__':
    main()
