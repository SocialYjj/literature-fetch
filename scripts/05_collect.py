# -*- coding: utf-8 -*-
"""阶段5：收尾整理。_raw/<序号>.pdf 复制成 参考文献/题目.pdf（重名题目才加序号后缀），并报告未获取/跳过清单。
用法: python 05_collect.py"""
import sys, os, shutil
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import CFG, load_manifest, have, simple_name
sys.stdout.reconfigure(encoding='utf-8')

def main():
    out = CFG["pdf_dir"]; os.makedirs(out, exist_ok=True)
    m = load_manifest(); ok = 0
    # 按目标目录路径长度反推可用文件名长度；预留 8 字符给重名后缀"(123)"
    names = {r['num']: simple_name(r, outdir=out, reserve=8) for r in m}
    dup = Counter(names.values())
    for r in sorted(m, key=lambda x: x['num']):
        if not have(r['num']): continue
        name = names[r['num']]
        if dup[name] > 1: name = f"{name}({r['num']})"   # 同名题目防覆盖
        dst = os.path.join(out, name + ".pdf")
        if not os.path.exists(dst):
            try:
                shutil.copyfile(os.path.join(CFG["raw_dir"], f"{r['num']}.pdf"), dst)
            except OSError as e:   # 路径仍过长/非法等：退回用序号命名，保证不丢文件
                dst = os.path.join(out, f"paper_{r['num']}.pdf")
                shutil.copyfile(os.path.join(CFG["raw_dir"], f"{r['num']}.pdf"), dst)
                print(f"  ({r['num']}) 题目命名失败({str(e)[:40]})，改用 {os.path.basename(dst)}")
        ok += 1
    miss = [r['num'] for r in m if not have(r['num']) and not r.get('skip')]
    skipped = [r['num'] for r in m if r.get('skip')]
    print(f"已整理 {ok}/{len(m)} 篇 -> {out}{chr(92)}")
    if skipped: print(f"跳过(中文等) {len(skipped)} 篇: {skipped}")
    if miss: print(f"未获取 {len(miss)} 篇: {miss}")
    else: print("英文论文全部获取完毕 ✔")

if __name__ == '__main__':
    main()
