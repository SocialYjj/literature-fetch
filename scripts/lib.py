# -*- coding: utf-8 -*-
"""literature-fetch 共享库：配置、清单、文件名清洗、限流请求、OpenAlex 辅助、下载核心、表头探测。"""
import os, sys, json, re, time, urllib.request, urllib.error, urllib.parse
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ---------- 配置 ----------
DEFAULTS = {
    "raw_dir": "_raw",                 # 批量流程下载落盘：_raw/<序号>.pdf
    "pdf_dir": "参考文献",              # 留档成品目录
    "manifest": "manifest.json",
    "mailto": "research@example.com",  # 进 OpenAlex/CrossRef 礼貌池，换成真实邮箱更好
}
def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists("config.json"):
        try: cfg.update(json.load(open("config.json", encoding="utf-8")))
        except Exception: pass
    return cfg
CFG = load_config()

def load_manifest():
    return json.load(open(CFG["manifest"], encoding="utf-8"))
def save_manifest(m):
    json.dump(m, open(CFG["manifest"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def have(num):
    p = os.path.join(CFG["raw_dir"], f"{num}.pdf")
    return os.path.exists(p) and os.path.getsize(p) > 20000

def is_cn(t):
    return bool(re.search(r'[一-鿿]', t or ''))

# ---------- 文件名 ----------
def sanitize(s):
    """Windows 非法字符 -> 全角/安全字符。"""
    out = []; tog = True
    for ch in s:
        if ch == '"': out.append('“' if tog else '”'); tog = not tog
        elif ch == ':': out.append('：')
        elif ch == '/' or ch == chr(92): out.append('-')
        elif ch == '*': out.append('＊')
        elif ch == '?': out.append('？')
        elif ch == '<': out.append('＜')
        elif ch == '>': out.append('＞')
        elif ch == '|': out.append('｜')
        elif ch in '\r\n\t': out.append(' ')
        else: out.append(ch)
    return ''.join(out).strip().rstrip('.')

def simple_name(rec, maxlen=120):
    """成品命名：题目（超长截断；空题目兜底用序号）。"""
    t = str(rec.get('excel_title') or rec.get('title') or '').strip() or f"paper_{rec['num']}"
    if len(t) > maxlen: t = t[:maxlen - 1] + '…'
    return sanitize(t)

# ---------- 标题相似度 ----------
import difflib
def norm(t): return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', (t or '').lower())).strip()
def sim(a, b): return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()

# ---------- 限流 HTTP ----------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
def fetch_json(url, tries=5, timeout=40, polite=0.0):
    """带 429 指数退避的 JSON 请求。"""
    last = None
    for i in range(tries):
        if polite: time.sleep(polite)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': f'ResearchBot/1.0 (mailto:{CFG["mailto"]})'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429: time.sleep([3, 8, 15, 25, 40][min(i, 4)])
            elif e.code in (400, 404): raise
            else: time.sleep(2 * (i + 1))
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    raise last

def fetch_bytes(url, tries=3, timeout=60):
    """urllib 直下，用于 OA 等无需登录的正版直链。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    raise last

def is_pdf(data):
    return isinstance(data, (bytes, bytearray)) and data[:4] == b'%PDF' and len(data) > 20000

# ---------- OpenAlex 辅助 ----------
def clean_query(t):
    t = re.sub(r'[^0-9A-Za-z一-鿿 ]+', ' ', t)
    return ' '.join(re.sub(r'\s+', ' ', t).strip().split()[:18])

def pick_best(title, results):
    """按 (标题相似度, 被引量) 选最优——同分时选被引高的，避开同名镜像/预印本克隆。返回 (work, sim)。"""
    best, bs = None, (0.0, -1)
    for w in results or []:
        s = sim(title, w.get('display_name') or w.get('title') or '')
        key = (s, w.get('cited_by_count') or 0)
        if key > bs: bs, best = key, w
    return best, bs[0]

def inv_abstract(inv, maxlen=1500):
    """OpenAlex abstract_inverted_index -> 摘要文本。"""
    if not inv: return ''
    pos = {}
    for w, ps in inv.items():
        for p in ps: pos[p] = w
    return ' '.join(pos[i] for i in sorted(pos))[:maxlen]

# ---------- 下载核心（page 参数为 Playwright Page，由调用方创建/关闭） ----------
CF_HOSTS = ('sciencedirect', 'elsevier', 'onlinelibrary.wiley', 'pubs.acs.org', 'ietresearch')
# 允许 urllib 直下的正版 OA 站白名单；其余（含来路不明的镜像）一律走 doi.org 出版社页
OA_HOSTS = ('arxiv.org', 'ncbi.nlm.nih.gov', 'europepmc.org', 'mdpi.com', 'frontiersin.org',
            'hindawi.com', 'plos.org', 'springeropen.com', 'biomedcentral.com', 'file.cpss.org.cn')

def oa_direct(urls):
    """仅白名单正版 OA 站 urllib 直下。命中返回 PDF bytes，否则 None。"""
    for u in urls:
        if not u: continue
        if not any(h in urllib.parse.urlparse(u).netloc.lower() for h in OA_HOSTS): continue
        try:
            b = fetch_bytes(u)
            if is_pdf(b): return b
        except Exception: pass
    return None

FETCH_JS = """
async (u) => { try {
  const r = await fetch(u, {credentials:'include'});
  if(!r.ok) return {ok:false,status:r.status};
  const ct=r.headers.get('content-type')||'';
  if(!ct.includes('pdf')&&!ct.includes('octet')) return {ok:false,ct};
  const b=new Uint8Array(await r.arrayBuffer()); let s=''; const c=0x8000;
  for(let i=0;i<b.length;i+=c) s+=String.fromCharCode.apply(null,b.subarray(i,i+c));
  return {ok:true, b64:btoa(s)};
} catch(e){ return {ok:false, err:String(e)}; } }
"""

def fetch_pdf(page, url):
    """页内 fetch 拿 PDF（带登录态 cookie），base64 回传。"""
    import base64
    try: res = page.evaluate(FETCH_JS, url)
    except Exception: return None
    if res and res.get('ok') and res.get('b64'):
        try: b = base64.b64decode(res['b64'])
        except Exception: return None
        if is_pdf(b): return b
    return None

def pdf_candidates(final_url, doi, page):
    """按落地域名生成 PDF 直链候选（各出版社规律见 references/publishers.md）。"""
    h = urllib.parse.urlparse(final_url).netloc.lower()
    base = final_url.split('?')[0].split('#')[0].rstrip('/')
    c = []
    if 'ieee' in h:
        mm = re.search(r'/document/(\d+)', final_url)
        if mm: c.append(f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={mm.group(1)}&ref=")
    elif 'springer' in h:
        c += [f"https://link.springer.com/content/pdf/{doi}.pdf"]
    elif 'iopscience' in h:
        c += [base + "/pdf", f"https://iopscience.iop.org/article/{doi}/pdf"]
    elif 'acm.org' in h:
        c += [f"https://dl.acm.org/doi/pdf/{doi}"]
    elif 'nature.com' in h:
        c += [base + ".pdf"]
    elif 'mdpi.com' in h:
        c += [base + "/pdf"]
    elif 'tandfonline' in h:
        c += [f"https://www.tandfonline.com/doi/pdf/{doi}?download=true"]
    elif 'emerald.com' in h:
        c += [f"https://www.emerald.com/insight/content/doi/{doi}/full/pdf"]
    elif 'sagepub.com' in h:
        c += [f"https://journals.sagepub.com/doi/pdf/{doi}?download=true"]
    # 通用：citation_pdf_url meta + 扫页面 pdf 链接
    try:
        cp = page.evaluate("()=>document.querySelector('meta[name=\"citation_pdf_url\"]')?.content||null")
        if cp and cp not in c: c.append(cp)
    except Exception: pass
    try:
        hrefs = page.evaluate("""()=>[...document.querySelectorAll('a')].map(a=>a.href)
            .filter(h=>h&&/\\.pdf(\\?|$)|\\/pdf(\\?|$|\\/)|getpdf|article-pdf/i.test(h)).slice(0,8)""")
        for u in hrefs:
            uu = urllib.parse.unquote(u)
            if (u not in c and same_host(u, final_url)
                    and (u.startswith(base) or (doi and doi.lower() in uu.lower()))):
                c.append(u)   # 本站+与本文相关：防把相关文章/参考文献的 PDF 当成本文
    except Exception: pass
    return c

def grab_via_doi(page, doi):
    """doi.org 跳出版社页取 PDF（机构权限/OA）。返回 (status, bytes|None)；CF 反爬社返回 skip_cf。"""
    try:
        page.goto(f"https://doi.org/{doi}", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        return 'goto_fail', None
    page.wait_for_timeout(2800)   # 给慢渲染站(如Emerald)足够时间把PDF链接铺进DOM
    try: t = page.title() or ''
    except Exception: t = ''
    if any(x in t for x in ('Just a moment', '请稍候', 'Attention Required', 'apologize', 'inconvenience')):
        return 'challenge', None   # 反爬挑战页(CF/hCaptcha等)：无头过不去，升级有头
    host = urllib.parse.urlparse(page.url).netloc.lower()
    if any(x in host for x in CF_HOSTS):
        return 'skip_cf', None
    # AMS: PDF 在 www.ams.org 子域(与落地 pubs.ams.org 跨域,页内fetch被CORS挡)→urllib服务端直取
    if 'ams.org' in host:
        m = re.search(r'/journals/([^/]+)/([^/]+)/([^/?#]+)', page.url)
        if m:
            jr, iss, aid = m.groups()
            try:
                b = fetch_bytes(f"https://www.ams.org/journals/{jr}/{iss}/{aid}/{aid}.pdf")
                if is_pdf(b): return 'ok', b
            except Exception: pass
    for u in pdf_candidates(page.url, doi, page):
        b = fetch_pdf(page, u)
        if b: return 'ok', b
    return 'fail', None

# ---------- 出版社路由表（自学习：无头优先，失败升级有头，结果回写） ----------
ROUTE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'references', 'route_table.json')
_ROUTE_SEED = {   # 初始经验（212篇项目 + 实测）；之后由运行结果自动完善
    "10.1109": ("IEEE", "headless"),   "10.1007": ("Springer", "headless"),
    "10.1038": ("Nature", "headless"), "10.1088": ("IOP", "headless"),
    "10.1145": ("ACM", "headless"),    "10.48550": ("arXiv", "headless"),
    "10.24295": ("CPSS-TPEA", "headless"), "10.35833": ("MPCE", "headless"),
    "10.17775": ("CSEE-JPES", "headless"),
    "10.1016": ("Elsevier", "headed"), "10.1002": ("Wiley", "headed"),
    "10.1049": ("IET", "headed"),      "10.1021": ("ACS", "headed"),
    "10.3390": ("MDPI", "headed"),     "10.1063": ("AIP", "headed"),
    "10.1039": ("RSC", "headed"),
}
def _registrant(doi):
    return (doi or '').split('/')[0].lower()

def load_routes():
    if os.path.exists(ROUTE_FILE):
        try: return json.load(open(ROUTE_FILE, encoding='utf-8'))
        except Exception: pass
    rt = {k: {"name": n, "mode": md, "hl_ok": 0, "hl_fail": 0, "hd_ok": 0}
          for k, (n, md) in _ROUTE_SEED.items()}
    save_routes(rt)
    return rt

def save_routes(rt):
    os.makedirs(os.path.dirname(ROUTE_FILE), exist_ok=True)
    json.dump(rt, open(ROUTE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def route_mode(doi, rt=None):
    """headless=已知无头可下 | headed=已知需有头 | unknown=新出版社(先无头试)"""
    rt = load_routes() if rt is None else rt
    e = rt.get(_registrant(doi))
    return e['mode'] if e else 'unknown'

def record_route(doi, event, rt=None, name=None):
    """event: hl_ok(无头成功) / hl_fail(无头失败,原因不明不改判) / hl_challenge(遇反爬,判headed) / hd_ok(有头成功)。
    传 rt 则只改内存(批量跑完统一 save_routes)；不传则立即落盘。"""
    own = rt is None
    rt = load_routes() if rt is None else rt
    k = _registrant(doi)
    if not k: return rt
    e = rt.setdefault(k, {"name": name or k, "mode": "unknown", "hl_ok": 0, "hl_fail": 0, "hd_ok": 0})
    if event == 'hl_ok': e['hl_ok'] += 1; e['mode'] = 'headless'
    elif event == 'hl_fail': e['hl_fail'] += 1
    elif event == 'hl_challenge': e['hl_fail'] += 1; e['mode'] = 'headed'
    elif event == 'hd_ok':
        e['hd_ok'] += 1
        if e['mode'] != 'headless': e['mode'] = 'headed'
    if own: save_routes(rt)
    return rt

# ---------- DrissionPage 页内 fetch 取 PDF（有头场景首选下载方式） ----------
def dp_fetch_pdf(page, url, timeout=90):
    """在真实 Chrome 页面里用 JS fetch 取 PDF（base64 轮询回传）。
    不经过 Chrome 下载子系统：不弹另存为/多文件确认，IDM 等下载器也截不走。
    带 credentials（cf_clearance/机构登录态都生效）。失败返回 None（调用方可锚点下载兜底）。"""
    import base64
    try:
        page.run_js(
            'window.__pdfb64=undefined;'
            'fetch(arguments[0],{credentials:"include"})'
            '.then(r=>{if(!r.ok)throw "http"+r.status;'
            'const ct=r.headers.get("content-type")||"";'
            'if(!(ct.includes("pdf")||ct.includes("octet")))throw "ct:"+ct;'
            'return r.arrayBuffer()})'
            '.then(b=>{const u=new Uint8Array(b);let s="";const c=0x8000;'
            'for(let i=0;i<u.length;i+=c)s+=String.fromCharCode.apply(null,u.subarray(i,i+c));'
            'window.__pdfb64=btoa(s)})'
            '.catch(e=>{window.__pdfb64="ERR:"+String(e)});', url)
    except Exception:
        return None
    for _ in range(timeout):
        time.sleep(1)
        try:
            r = page.run_js('return window.__pdfb64===undefined?null:window.__pdfb64;')
        except Exception:
            return None
        if r is None: continue
        if isinstance(r, str) and not r.startswith('ERR:'):
            try: b = base64.b64decode(r)
            except Exception: return None
            return b if is_pdf(b) else None
        return None
    return None

def same_host(u, page_url):
    """扫描到的链接仅接受与文章页同域名的——防止把参考文献/第三方 PDF 当成本文下载。"""
    try:
        return urllib.parse.urlparse(u).netloc.lower() == urllib.parse.urlparse(page_url).netloc.lower()
    except Exception:
        return False

# Cookie/隐私同意横幅按钮文案（合规弹窗，非人机验证——可自动点掉；绝不匹配验证框）
_CONSENT_TXT = ['accept all', 'accept cookies', 'i accept', 'accept & close', 'allow all',
                'agree', 'i agree', 'got it', 'ok', 'continue', 'consent',
                '接受', '同意', '全部接受', '允许全部', '知道了', '我知道了']
def dismiss_consent(page):
    """DrissionPage 页面：只点 Cookie/隐私同意横幅（Accept All 等），清掉遮挡下载入口的合规弹窗。
    刻意不碰任何含 robot/human/verify/captcha/真实访客/验证 字样的元素——人机验证一律留给用户手动。"""
    js = ('const words=' + json.dumps(_CONSENT_TXT) + ';'
          'const bad=/robot|human|verify|verif|captcha|真人|真实访客|验证|不是机器/i;'
          'const btns=[...document.querySelectorAll("button,a,[role=button],input[type=button],input[type=submit]")];'
          'for(const b of btns){'
          '  const t=((b.innerText||b.textContent||b.value||"")+"").trim().toLowerCase();'
          '  if(!t||t.length>24) continue;'
          '  if(bad.test(t)) continue;'                       # 绝不点验证类控件
          '  if(words.some(w=>t===w||t===w+"!"||t.replace(/\\s+/g,"")===w.replace(/\\s+/g,""))){b.click();return t;}'
          '}'
          'return null;')
    try:
        r = page.run_js(js)
        if r: time.sleep(0.8)
        return r
    except Exception:
        return None

# ---------- Turnstile 自动过：扩展 + 智能等待（只对 CF Turnstile 有效，hCaptcha 仍需真人） ----------
TURNSTILE_EXT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'assets', 'turnstilePatch')
# 挂 turnstilePatch 反而触发 CF 死循环的出版社(DOI前缀)黑名单。
# 实测结论：扩展全程挂着即可——能自动过的(ACS/Wiley/MDPI)零点击；过不了的(如ScienceDirect)
# 扩展自动点会卡"请稍候",但用户真人手点仍有效、立刻通过(可信点击不受扩展无效合成点击影响)。
# 故黑名单留空(扩展全挂);若某站将来被证实真人手点也被扩展带死,再把其前缀加进来。
EXT_BACKFIRE = set()
def use_turnstile(doi):
    """该 DOI 的出版社是否该挂 turnstilePatch 扩展（黑名单内的挂了反而坏事→不挂）。"""
    return _registrant(doi) not in EXT_BACKFIRE

def add_turnstile_patch(co, doi=None):
    """给 DrissionPage ChromiumOptions 挂 turnstilePatch 扩展：抹掉 webdriver 指纹 + 自动点 Turnstile 复选框。
    使真实 Chrome 不暴露自动化特征，让 CF 风控引擎按普通浏览器自动放行；不做任何密码学破解。
    传 doi 时，黑名单出版社(如 ScienceDirect)不挂——挂了反被 CF 判篡改、死循环。返回是否挂了。"""
    if doi is not None and not use_turnstile(doi):
        return False
    try:
        if os.path.isdir(TURNSTILE_EXT):
            co.add_extension(TURNSTILE_EXT); return True
    except Exception:
        pass
    return False

def _page_title(page):
    """兼容取标题：DrissionPage 的 title 是属性，Playwright 的是方法。"""
    t = getattr(page, 'title', '')
    if callable(t):
        try: t = t()
        except Exception: t = ''
    return t or ''

def _cf_state(page):
    """判断当前页拦截状态：ok(已放行) / turnstile(CF挑战) / hcaptcha(需真人) / recaptcha(需真人)。"""
    t = _page_title(page)
    tl = t.lower()
    h = ''
    try: h = (page.html or '')[:200000]
    except Exception: pass
    hl = h.lower()
    if 'hcaptcha' in hl or '真实访客' in h or 'inconvenience' in tl or 'apologize' in tl:
        return 'hcaptcha'
    if 'g-recaptcha' in hl or 'recaptcha/api' in hl:
        return 'recaptcha'
    # 只认 CF 挑战页的确切特征；不用裸 'turnstile' 关键词（正文含该词的论文会被误判为拦截）
    blocked = ('just a moment' in tl or '请稍候' in t or 'attention required' in tl
               or 'moment' in tl or len(t.strip()) == 0)
    if blocked or 'cf-turnstile' in hl or 'challenge-platform' in hl or '__cf_chl' in hl:
        return 'turnstile'
    return 'ok'

def pass_cf_auto(page, auto_secs=25):
    """有头 + turnstilePatch 扩展下，先自动等 CF Turnstile 放行（扩展会自动点复选框）。
    返回: 'ok'(已放行) / 'need_user_turnstile'(CF没自动过,需真人点) / 'hcaptcha' / 'recaptcha'（后两者必须真人）。"""
    for _ in range(auto_secs):
        st = _cf_state(page)
        if st == 'ok': return 'ok'
        if st in ('hcaptcha', 'recaptcha'): return st   # 扩展搞不定，立即交人
        time.sleep(1)
    return 'ok' if _cf_state(page) == 'ok' else 'need_user_turnstile'

def cleared_title(page):
    """标题法判断当前页是否已过拦截（无 Just a moment / 请稍候 / 道歉页 / robot）。"""
    t = _page_title(page)
    return (all(x not in t for x in ('请稍候', 'Just a moment', 'Attention Required', 'moment',
                                     'apologize', 'inconvenience')) and 'robot' not in t.lower())

_CF_GIVEUP = set()   # 本次运行中人工验证已超时的域名：同域名后续快速跳过，不再逐篇空等

def ensure_access(page, tag='', manual_secs=180):
    """【统一第一步：确保过验证，带人工兜底】进出版社文章页后调用。
    ① 先让 turnstilePatch 扩展自动过 CF Turnstile；成功即返回 True（顺手关 Cookie 横幅）。
    ② 自动没过 → 明确提示验证类型 + 请用户在弹出窗口手动过；轮询等待，过了继续。
    ③ manual_secs 内仍没过 → 返回 False，并把该域名记入本次运行的放弃名单：
       同域名后续论文直接快速跳过（避免无人值守时每篇都空等 3 分钟）。
    返回 True=可继续下载，False=没过（如实标记未获取，别硬闯）。"""
    host = ''
    try: host = urllib.parse.urlparse(page.url).netloc.lower()
    except Exception: pass
    st = pass_cf_auto(page, auto_secs=25)
    if st == 'ok':
        _CF_GIVEUP.discard(host)      # 本轮该域名已能过，解除放弃标记
        dismiss_consent(page); return True
    if host and host in _CF_GIVEUP:   # 该域名本轮已确认过不去 → 不再空等
        print(f"    [{host}] 本轮已确认验证过不去，快速跳过（换网络/稍后重跑该批）。", flush=True)
        return False
    kind = {'hcaptcha': 'hCaptcha（最严，必须真人）',
            'recaptcha': 'reCAPTCHA（必须真人）',
            'need_user_turnstile': 'Cloudflare（扩展没自动过）'}.get(st, st)
    prefix = f"[{tag}] " if tag else ""
    print(f"\n>>> {prefix}出现 {kind}，请在弹出的 Chrome 窗口里手动完成验证；"
          f"完成后脚本会自动继续（最多等 {manual_secs}s）<<<\n", flush=True)
    for _ in range(manual_secs // 2):
        time.sleep(2)
        if cleared_title(page):
            print("    验证已过，继续。", flush=True)
            _CF_GIVEUP.discard(host)
            dismiss_consent(page); return True
    if host: _CF_GIVEUP.add(host)
    print(f"    {prefix}仍未通过。若是 CF 整页'请稍候'死循环 → 换网络/稍后再试；"
          f"或复用已过验证的配置目录（cf_clearance）。该域名本轮后续论文将快速跳过。", flush=True)
    return False

# ---------- 表头/题目列自动探测 ----------
_HDR_KW = ['序号', '编号', '类型', '年份', '发表', '题目', '标题', 'title', 'doi', 'type', 'year', 'author', '作者']
def find_header(rows):
    """在前若干行里选'表头关键词最多'的一行作表头，返回 (表头行idx0, 题目列idx0, 序号列idx0)。"""
    best_ri, best_score = 0, -1
    for ri, row in enumerate(rows[:25]):
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        score = sum(1 for c in cells if len(c) < 15 and any(k in c.lower() for k in _HDR_KW))
        if score > best_score and score >= 2:
            best_score, best_ri = score, ri
    row = rows[best_ri]
    tcol = None
    for ci, c in enumerate(row):
        if c and re.search(r'题目|标题|title', str(c), re.I) and len(str(c)) < 15:
            tcol = ci; break
    if tcol is None:   # 兜底：数据区最长文本列
        below = rows[best_ri + 1: best_ri + 25]
        width = max((len(r) for r in below), default=len(row))
        tcol = max(range(width), key=lambda c: sum(len(str((r[c] if c < len(r) else '') or '')) for r in below))
    ncol = None
    for ci, c in enumerate(row):
        if c and re.search(r'序号|编号|No\b|^ID$', str(c), re.I) and len(str(c)) < 10:
            ncol = ci; break
    return best_ri, tcol, ncol
