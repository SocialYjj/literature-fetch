# -*- coding: utf-8 -*-
"""阶段1：按题目查 DOI（OpenAlex 主 + CrossRef 备），顺带记录 OA 免费直链。
限流安全：低并发 + mailto 礼貌池 + 429 退避。中文题目自动标记跳过。
用法: python 01_resolve_doi.py [--only-missing]"""
import sys, os, time, urllib.parse, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import CFG, load_manifest, save_manifest, fetch_json, sim, is_cn, clean_query, pick_best
sys.stdout.reconfigure(encoding='utf-8')
import re

MAILTO = CFG["mailto"]
_oa_lock = threading.Lock(); _oa_last = [0.0]; OA_GAP = 0.3   # OpenAlex 全局最小间隔
def oa_throttle():
    with _oa_lock:
        w = OA_GAP - (time.time() - _oa_last[0])
        if w > 0: time.sleep(w)
        _oa_last[0] = time.time()

def openalex_by_title(title):
    for q in (title, clean_query(title)):
        oa_throttle()
        try:
            d = fetch_json(f"https://api.openalex.org/works?filter=title.search:{urllib.parse.quote(q)}"
                           f"&per-page=5&mailto={MAILTO}")
            if d.get('results'): return d['results']
        except Exception:
            continue
    return []

def crossref_find_doi(rec):
    """OpenAlex 没匹配到时，用 CrossRef 书目检索补 DOI。"""
    try:
        d = fetch_json("https://api.crossref.org/works?query.bibliographic="
                       f"{urllib.parse.quote(rec['excel_title'])}&rows=5"
                       f"&select=DOI,title&mailto={MAILTO}")
    except Exception:
        return False
    best, bs = None, 0
    for it in d.get('message', {}).get('items', []):
        t = (it.get('title') or [''])
        s = sim(rec['excel_title'], t[0] if t else '')
        if s > bs: bs, best = s, it
    rec['match_sim'] = round(bs, 3)
    if best and bs >= 0.72:
        rec['doi'] = best.get('DOI'); rec['src'] = 'crossref'
        return True
    return False

def resolve(rec):
    title = rec['excel_title']
    best, s = pick_best(title, openalex_by_title(title))
    rec['match_sim'] = round(s, 3)
    if best and s >= 0.55:
        w = best
        doi = (w.get('doi') or '')
        rec['doi'] = doi.replace('https://doi.org/', '') if doi else None
        rec['year'] = w.get('publication_year')
        rec['title'] = w.get('display_name')
        oa = w.get('best_oa_location') or {}
        if oa.get('pdf_url'): rec['oa_url'] = oa['pdf_url']
        rec['src'] = 'openalex'
    if not rec.get('doi'):
        crossref_find_doi(rec)
    return rec

def main():
    only_missing = '--only-missing' in sys.argv
    m = load_manifest()
    for r in m:
        if is_cn(r.get('excel_title', '')): r['skip'] = 'cn'
    todo = [r for r in m if not r.get('skip') and not (only_missing and r.get('doi'))]
    print(f"查 DOI {len(todo)} 篇 (OpenAlex+CrossRef, 低并发防429)...", flush=True)
    by = {r['num']: r for r in m}
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(resolve, r): r for r in todo}
        for fu in as_completed(futs):
            try: r = fu.result(); by[r['num']] = r
            except Exception: pass
            done += 1
            if done % 20 == 0:
                print(f"  ...{done}/{len(todo)}", flush=True)
                save_manifest([by[k] for k in sorted(by)])
    save_manifest([by[k] for k in sorted(by)])
    ok = sum(1 for r in m if r.get('doi')); oa = sum(1 for r in m if r.get('oa_url'))
    cn = sum(1 for r in m if r.get('skip'))
    print(f"\n完成: {ok}/{len(m)} 有DOI | {oa} 有OA直链 | {cn} 中文跳过")
    print("无DOI(留待谷歌学术 03):", [r['num'] for r in m if not r.get('doi') and not r.get('skip')])

if __name__ == '__main__':
    main()
