#!/usr/bin/env python3
"""
fetch_bclc.py — BCLC Keno 数据抓取 + PC28 解析
用于 GitHub Actions 定时运行，输出 data.json
"""
import json, sys, os, time, random, hashlib
import urllib.request, urllib.parse, ssl
from datetime import datetime, timedelta, timezone

# ============================================================
# BCLC 规则常量
# ============================================================
DRAW_INTERVAL = 210  # 3分30秒
BJT = timezone(timedelta(hours=8))

# ============================================================
# 时间工具
# ============================================================
def is_dst_utc(utc_dt):
    """判断UTC时间是否处于北美夏令时"""
    year = utc_dt.year
    # 3月第二个周日 02:00 PST = 10:00 UTC
    march1 = datetime(year, 3, 1, tzinfo=timezone.utc)
    days = (6 - march1.weekday() + 7) % 7 + 7
    dst_start = march1 + timedelta(days=days, hours=10)
    # 11月第一个周日 02:00 PDT = 09:00 UTC
    nov1 = datetime(year, 11, 1, tzinfo=timezone.utc)
    days2 = (6 - nov1.weekday()) % 7
    dst_end = nov1 + timedelta(days=days2, hours=9)
    return dst_start <= utc_dt < dst_end

def bj_to_utc(bj_dt):
    return bj_dt.astimezone(timezone.utc)

def get_session_bounds(bj_dt):
    """返回当日开奖时段的 (start, end) 北京时间"""
    utc = bj_to_utc(bj_dt)
    dst = is_dst_utc(utc)
    if dst:
        start = bj_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=19, minute=0, second=0)
    else:
        start = bj_dt.replace(hour=21, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=20, minute=0, second=0)
    return start, end, dst

def is_open(bj_dt):
    s, e, _ = get_session_bounds(bj_dt)
    return s <= bj_dt <= e

def period_info(bj_dt):
    """返回 (期号, 倒计时秒, 下一期时间BJT)"""
    s, e, dst = get_session_bounds(bj_dt)
    
    if bj_dt < s:
        # 用前一天的start
        prev = bj_dt - timedelta(days=1)
        s, _, _ = get_session_bounds(prev)
    
    elapsed = (bj_dt - s).total_seconds()
    seq = max(1, int(elapsed / DRAW_INTERVAL) + 1)
    date_str = s.strftime('%y%m%d')
    period = f"{date_str}{seq:04d}"
    
    next_draw = s + timedelta(seconds=seq * DRAW_INTERVAL)
    cd = max(0, int((next_draw - bj_dt).total_seconds()))
    
    return period, cd, next_draw, seq, s

# ============================================================
# 核心：20码 → PC28
# ============================================================
def parse_20_to_pc28(nums_sorted):
    n = nums_sorted
    if len(n) != 20:
        raise ValueError(f"需要20个号码，得到{len(n)}")
    a = (n[1] + n[4] + n[7] + n[10] + n[13] + n[16]) % 10
    b = (n[2] + n[5] + n[8] + n[11] + n[14] + n[17]) % 10
    c = (n[3] + n[6] + n[9] + n[12] + n[15] + n[18]) % 10
    return {'a': a, 'b': b, 'c': c, 'sum': a+b+c}

def get_combo(sum_val):
    size = '小' if sum_val < 14 else '大'
    parity = '单' if sum_val % 2 == 1 else '双'
    return f"{size}{parity}"

def detect_pattern(a, b, c):
    s = sorted([a, b, c])
    if a == b == c: return '豹子'
    if a == b or b == c or a == c: return '对子'
    if s[1]-s[0] == 1 and s[2]-s[1] == 1: return '顺子'
    return '杂六'

# ============================================================
# 种子数据（接口全挂时兜底）
# ============================================================
def seeded_rng(seed_str, count=20, min_v=0, max_v=79):
    h = hashlib.md5(seed_str.encode()).digest()
    vals = set()
    for i in range(count * 3):
        v = (h[i % 16] * 37 + i * 131) % (max_v - min_v + 1) + min_v
        vals.add(v)
        if len(vals) >= count:
            break
    while len(vals) < count:
        vals.add(random.randint(min_v, max_v))
    return sorted(vals)

def generate_seed_draws(count=30):
    bj = datetime.now(BJT)
    draws = []
    for i in range(count):
        t = bj - timedelta(seconds=(count - i) * DRAW_INTERVAL)
        seed = f"bclc_{t.strftime('%Y%m%d%H%M%S')}_{i}"
        nums = seeded_rng(seed, 20)
        r = parse_20_to_pc28(nums)
        per, _, _, seq, sess_start = period_info(t)
        draws.append({
            'period': per,
            'date': t.strftime('%Y-%m-%d'),
            'time': t.strftime('%H:%M:%S'),
            'rawNums': nums,
            'a': r['a'], 'b': r['b'], 'c': r['c'],
            'sum': r['sum'],
            'combo': get_combo(r['sum']),
            'pattern': detect_pattern(r['a'], r['b'], r['c']),
            'source': 'seed',
        })
    return draws

# ============================================================
# HTTP 抓取（多路降级）
# ============================================================
def http_get(url, timeout=10, headers=None):
    import urllib.request, urllib.parse, ssl
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode('utf-8')

def fetch_bclc_official():
    """尝试 BCLC 官方接口"""
    endpoints = [
        'https://lotto.bclc.com/keno/results.json',
        'https://www.bclc.com/content/dam/bclc/keno/results.json',
        'https://www.bclc.com/etc/designs/bclc/keno/latest.json',
    ]
    for url in endpoints:
        try:
            data = http_get(url, 8)
            parsed = json.loads(data)
            draws = normalize_bclc(parsed)
            if draws:
                print(f"  [BCLC官方] {url} ✓ {len(draws)}期", flush=True)
                return draws
        except Exception as e:
            print(f"  [BCLC官方] {url} ✗ {e}", flush=True)
    return None

def fetch_mirrors():
    """尝试第三方镜像"""
    mirrors = [
        ('yu28.top', 'https://yu28.top/api/bclc?count=30', 'yu28'),
        ('pc28.help', 'https://pc28.help/api/bclc.json', 'pc28help'),
        ('corsproxy', f'https://corsproxy.io/?https://lotto.bclc.com/keno/results.json', 'cors'),
        ('allorigins', f'https://api.allorigins.win/raw?url={urllib.parse.quote("https://lotto.bclc.com/keno/results.json")}', 'cors2'),
    ]
    for name, url, ptype in mirrors:
        try:
            data = http_get(url, 8)
            parsed = json.loads(data)
            if ptype == 'yu28':
                draws = parse_yu28(parsed)
            elif ptype == 'pc28help':
                draws = parse_pc28help(parsed)
            else:
                draws = normalize_bclc(parsed)
            if draws:
                print(f"  [镜像] {name} ✓ {len(draws)}期", flush=True)
                return draws, name
        except Exception as e:
            print(f"  [镜像] {name} ✗ {e}", flush=True)
    return None, None

def normalize_bclc(data):
    draws = []
    items = data.get('draws', data.get('results', data.get('data', [])))
    if not items and isinstance(data, list): items = data
    for item in items[:50]:
        try:
            nums = item.get('numbers', item.get('nums', item.get('drawNumbers', [])))
            if isinstance(nums, str): nums = [int(x) for x in nums.split(',')]
            nums = sorted(int(x) for x in nums)
            if len(nums) != 20: continue
            r = parse_20_to_pc28(nums)
            draws.append({
                'period': str(item.get('drawNumber', item.get('period', ''))),
                'date': str(item.get('drawDate', item.get('date', ''))),
                'time': str(item.get('drawTime', item.get('time', ''))),
                'rawNums': nums,
                'a': r['a'], 'b': r['b'], 'c': r['c'],
                'sum': r['sum'],
                'combo': get_combo(r['sum']),
                'pattern': detect_pattern(r['a'], r['b'], r['c']),
                'source': 'bclc_official',
            })
        except: continue
    return draws

def parse_yu28(data):
    draws = []
    items = data.get('data', data.get('list', []))
    if not items and isinstance(data, list): items = data
    for item in items[:50]:
        try:
            nums = item.get('nums', item.get('numbers', []))
            if isinstance(nums, str): nums = [int(x) for x in nums.split(',')]
            nums = sorted(int(x) for x in nums)
            if len(nums) != 20: continue
            r = parse_20_to_pc28(nums)
            draws.append({
                'period': str(item.get('qihao', item.get('period', ''))),
                'date': str(item.get('date', '')),
                'time': str(item.get('time', '')),
                'rawNums': nums,
                'a': r['a'], 'b': r['b'], 'c': r['c'],
                'sum': r['sum'],
                'combo': get_combo(r['sum']),
                'pattern': detect_pattern(r['a'], r['b'], r['c']),
                'source': 'yu28',
            })
        except: continue
    return draws

def parse_pc28help(data):
    draws = []
    items = data.get('data', data.get('list', []))
    if not items and isinstance(data, list): items = data
    for item in items[:50]:
        try:
            nums = item.get('rawNums', item.get('nums', []))
            if isinstance(nums, str): nums = [int(x) for x in nums.split(',')]
            nums = sorted(int(x) for x in nums)
            if len(nums) != 20: continue
            r = parse_20_to_pc28(nums)
            draws.append({
                'period': str(item.get('nbr', item.get('period', ''))),
                'date': str(item.get('date', '')),
                'time': str(item.get('time', '')),
                'rawNums': nums,
                'a': r['a'], 'b': r['b'], 'c': r['c'],
                'sum': r['sum'],
                'combo': get_combo(r['sum']),
                'pattern': detect_pattern(r['a'], r['b'], r['c']),
                'source': 'pc28help',
            })
        except: continue
    return draws

# ============================================================
# 预测引擎（简化版，与前端一致）
# ============================================================
def predict(draws, max_hist=50):
    if not draws or len(draws) < 5:
        return None
    recent = draws[:max_hist]
    sums = [d['sum'] for d in recent]
    
    # EMA
    k = 0.3
    ema = sums[0]
    for s in sums[1:]: ema = k * s + (1-k) * ema
    
    # 加权频率
    freq = {}
    for i, s in enumerate(sums):
        w = 1 + (len(sums) - i) * 0.05
        freq[s] = freq.get(s, 0) + w
    
    center = round(ema)
    cands = []
    for v in range(max(0, center-3), min(28, center+4)):
        score = freq.get(v, 0) + (3 if v==center else 0) + (2 if abs(v-center)<=1 else 0)
        cands.append((v, score))
    cands.sort(key=lambda x: -x[1])
    
    main3 = [c[0] for c in cands[:3]]
    backup2 = [c[0] for c in cands[3:5]]
    
    # 杀5（频率最低）
    all_freq = {i: freq.get(i,0) for i in range(28)}
    kill5 = sorted(all_freq.items(), key=lambda x: x[1])[:5]
    kill5 = [x[0] for x in kill5]
    
    # 组合
    combo_freq = {}
    for d in recent:
        c = d.get('combo', get_combo(d['sum']))
        combo_freq[c] = combo_freq.get(c, 0) + 1
    sorted_combos = sorted(combo_freq.items(), key=lambda x: -x[1])
    pick_combos = [x[0] for x in sorted_combos[:2]]
    kill_combo = sorted_combos[-1][0] if sorted_combos else '大双'
    
    spread = cands[0][1] - cands[-1][1] if cands else 0
    conf = min(55, 25 + int(spread * 8))
    
    return {
        'mainBalls': main3,
        'backupBalls': backup2,
        'killBalls': kill5,
        'pickCombos': pick_combos,
        'killCombo': kill_combo,
        'center': center,
        'ema': round(ema, 1),
        'confidence': conf,
        'voteDetails': [{'v':c[0], 's':round(c[1],1)} for c in cands[:8]],
    }

# ============================================================
# 主流程
# ============================================================
def main():
    bj = datetime.now(BJT)
    per, cd, next_draw, seq, sess_start = period_info(bj)
    _, _, dst = get_session_bounds(bj)
    tz_name = 'PDT' if dst else 'PST'
    
    print(f"[BCLC] 北京时间: {bj.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"[BCLC] 时区: {tz_name}  开奖中: {is_open(bj)}  倒计时: {cd}秒", flush=True)
    print(f"[BCLC] 当期期号: {per}", flush=True)
    
    draws = []
    source = 'none'
    msg = ''
    
    # 1. 官方
    print("--- 尝试 BCLC 官方 ---", flush=True)
    d = fetch_bclc_official()
    if d: draws, source = d, 'bclc_official'
    
    # 2. 镜像
    if not draws:
        print("--- 尝试第三方镜像 ---", flush=True)
        d, name = fetch_mirrors()
        if d: draws, source = d, name or 'mirror'
    
    # 3. 种子兜底
    if not draws:
        print("--- 使用本地种子 ---", flush=True)
        draws = generate_seed_draws(30)
        source = 'seed'
        msg = '接口不可用，使用本地种子数据'
    
    # 去重排序
    seen = set()
    unique = []
    for d in draws:
        if d['period'] in seen: continue
        seen.add(d['period'])
        unique.append(d)
    unique.sort(key=lambda x: x['period'], reverse=True)
    
    # 预测
    pred = predict(unique)
    
    # 构建输出
    output = {
        'success': True,
        'source': source,
        'message': msg or f'数据来源: {source}',
        'timezone': tz_name,
        'isOpen': is_open(bj),
        'countdown': cd,
        'nextDraw': next_draw.strftime('%Y-%m-%d %H:%M:%S'),
        'currentPeriod': per,
        'updateTime': bj.strftime('%Y-%m-%d %H:%M:%S'),
        'drawCount': len(unique),
        'draws': unique[:50],
        'prediction': pred,
    }
    
    # 写入
    out_path = os.path.join(os.path.dirname(__file__), 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 写入 {out_path}: {len(unique)}期  来源={source}", flush=True)
    if pred:
        print(f"   预测: 主推{pred['mainBalls']} 候补{pred['backupBalls']} 杀{pred['killBalls']}", flush=True)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
