# -*- coding: utf-8 -*-
"""工具·主题/关键词检索（调研第1层）：OpenAlex 相关度搜索，国内直连免代理、零下载。
输出候选清单（题目/年份/期刊/被引/DOI/OA/摘要）到屏幕 + topic_results.json，供挑选后用 fetch_one.py 或批量管线获取。
用法: python search_topic.py "quantum computing power system" [--n 15] [--from 2020] [--oa] [--sort cited]
     （关键词建议用英文；宽泛主题可换几组措辞多跑几次）"""
import sys, os, json, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import CFG, fetch_json, inv_abstract
sys.stdout.reconfigure(encoding='utf-8')

def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('--'):
        print(__doc__); return
    q = args[0]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
    n = int(opt('--n', 15)); yfrom = opt('--from')
    filt = []
    if yfrom: filt.append(f"from_publication_date:{yfrom}-01-01")
    if '--oa' in args: filt.append("open_access.is_oa:true")
    u = ("https://api.openalex.org/works?search=" + urllib.parse.quote(q)
         + (f"&filter={','.join(filt)}" if filt else "")
         + ("&sort=cited_by_count:desc" if opt('--sort') == 'cited' else "")
         + f"&per-page={min(n, 50)}&mailto={CFG['mailto']}"
         + "&select=doi,display_name,publication_year,cited_by_count,primary_location,open_access,best_oa_location,abstract_inverted_index")
    d = fetch_json(u)
    out = []
    for i, w in enumerate(d.get('results', []), 1):
        rec = {
            'rank': i,
            'title': w.get('display_name'),
            'year': w.get('publication_year'),
            'venue': ((w.get('primary_location') or {}).get('source') or {}).get('display_name'),
            'cited': w.get('cited_by_count'),
            'doi': (w.get('doi') or '').replace('https://doi.org/', '') or None,
            'is_oa': bool((w.get('open_access') or {}).get('is_oa')),
            'oa_url': (w.get('best_oa_location') or {}).get('pdf_url'),
            'abstract': inv_abstract(w.get('abstract_inverted_index')),
        }
        out.append(rec)
        print(f"[{i}] {rec['title']}  ({rec['year']}, 被引 {rec['cited']})")
        print(f"    {rec['venue'] or '?'} | DOI: {rec['doi'] or '无'} | OA: {'是' if rec['is_oa'] else '否'}")
        if rec['abstract']: print(f"    摘要: {rec['abstract'][:280]}…")
        print()
    json.dump(out, open("topic_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"共 {len(out)} 条 -> topic_results.json（挑中的可用 fetch_one.py <DOI> 获取，或写入 manifest 走批量管线）")

if __name__ == '__main__':
    main()
