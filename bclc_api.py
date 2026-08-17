#!/usr/bin/env python3
"""
BCLC Keno 开奖数据接口
============================
规则说明：
- BCLC 每期开出 20 个数字（0-79 范围）
- 按从小到大排列后，取特定位置求和，末位作为 PC28 的三球数值
- 球1 = 第2+5+8+11+14+17位 之和的末位
- 球2 = 第3+6+9+12+15+18位 之和的末位
- 球3 = 第4+7+10+13+16+19位 之和的末位
- 特码 = 球1 + 球2 + 球3

开奖时间：
- 夏令时（3月-11月）：北京时间 20:00 - 次日19:00，每3.5分钟一期
- 冬令时（11月-3月）：北京时间 21:00 - 次日20:00，每3.5分钟一期

本模块提供：
1. fetch_bclc_draws()  - 从 BCLC 官网抓取最新开奖数据
2. parse_to_pc28()     - 将20码解析为 PC28 三球+特码
3. generate_seed_data()- 生成本地种子数据（接口失败时兜底）
4. get_latest_data()   - 统一入口：抓取+解析+返回
"""

import json
import time
import random
import hashlib
from datetime import datetime, timedelta, timezone

# ============================================================
# 1. BCLC 开奖时间工具
# ============================================================

# 太平洋时区（BCLC 所在时区）
# 夏令时：3月第二个周日起，11月第一个周日止
PACIFIC_TZ = timezone(timedelta(hours=-7))  # PST
PACIFIC_DST = timezone(timedelta(hours=-7))  # PDT 也是 -7？不对

def get_bclc_timezone(dt=None):
    """判断给定时间是否处于夏令时（PDT = UTC-7, PST = UTC-8）"""
    if dt is None:
        dt = datetime.utcnow()
    # 夏令时：3月第二个周日 ~ 11月第一个周日
    year = dt.year
    # 3月第二个周日 02:00
    march1 = datetime(year, 3, 1)
    days_to_second_sunday = (6 - march1.weekday() + 7) % 7 + 7
    dst_start = datetime(year, 3, 1, 10, 0, tzinfo=timezone.utc) + timedelta(days=days_to_second_sunday)
    # 11月第一个周日 02:00
    nov1 = datetime(year, 11, 1)
    days_to_first_sunday = (6 - nov1.weekday()) % 7
    dst_end = datetime(year, 11, 1, 9, 0, tzinfo=timezone.utc) + timedelta(days=days_to_first_sunday)
    
    utc_time = dt if dt.tzinfo else datetime(*dt.timetuple()[:6], tzinfo=timezone.utc)
    if dst_start <= utc_time < dst_end:
        return -7, True   # PDT
    else:
        return -8, False   # PST

def bclc_draw_cycle_seconds():
    """每期开奖间隔（秒）"""
    return 210  # 3分30秒

def is_bclc_open(now_bj=None):
    """判断当前是否处于 BCLC 开奖时段（北京时间）"""
    if now_bj is None:
        now_bj = datetime.now(timezone(timedelta(hours=8)))
    
    _, is_dst = get_bclc_timezone(now_bj.astimezone(timezone.utc))
    
    if is_dst:
        # 夏令时：北京时间 20:00 - 次日19:00
        start = now_bj.replace(hour=20, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=19, minute=0, second=0)
    else:
        # 冬令时：北京时间 21:00 - 次日20:00
        start = now_bj.replace(hour=21, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=20, minute=0, second=0)
    
    return start <= now_bj <= end

def get_next_draw_time(now_bj=None):
    """获取下一期开奖的倒计时（秒）和下一期北京时间"""
    if now_bj is None:
        now_bj = datetime.now(timezone(timedelta(hours=8)))
    
    _, is_dst = get_bclc_timezone(now_bj.astimezone(timezone.utc))
    
    if is_dst:
        day_start = now_bj.replace(hour=20, minute=0, second=0, microsecond=0)
        day_end = (day_start + timedelta(days=1)).replace(hour=19, minute=0, second=0)
    else:
        day_start = now_bj.replace(hour=21, minute=0, second=0, microsecond=0)
        day_end = (day_start + timedelta(days=1)).replace(hour=20, minute=0, second=0)
    
    # 找到当前所处开奖日
    if now_bj < day_start:
        # 今天还没开始，下一期就是今天的开场
        next_draw = day_start
    elif now_bj > day_end:
        # 今天已结束，下一期是明天开场
        tomorrow_start = (day_start + timedelta(days=1))
        next_draw = tomorrow_start
    else:
        # 正在开奖中，按210秒对齐
        elapsed = (now_bj - day_start).total_seconds()
        periods_passed = int(elapsed / 210)
        next_draw = day_start + timedelta(seconds=(periods_passed + 1) * 210)
    
    countdown = int((next_draw - now_bj).total_seconds())
    return max(countdown, 0), next_draw

def bj_to_period_number(now_bj=None):
    """根据北京时间生成期号（与 BCLC 当日序号对应）"""
    if now_bj is None:
        now_bj = datetime.now(timezone(timedelta(hours=8)))
    
    _, is_dst = get_bclc_timezone(now_bj.astimezone(timezone.utc))
    
    if is_dst:
        day_start = now_bj.replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        day_start = now_bj.replace(hour=21, minute=0, second=0, microsecond=0)
    
    if now_bj < day_start:
        # 属于前一天的末期
        day_start = day_start - timedelta(days=1)
    
    elapsed = (now_bj - day_start).total_seconds()
    period_seq = max(1, int(elapsed / 210) + 1)
    
    # 期号格式：日期(YYMMDD) + 4位序号
    date_str = day_start.strftime("%y%m%d")
    return f"{date_str}{period_seq:04d}"

# ============================================================
# 2. 20码 → PC28 三球解析
# ============================================================

def parse_20_to_pc28(nums_20_sorted):
    """
    将 BCLC 的 20 个开奖号码（已从小到大排序）解析为 PC28 三球+特码
    
    规则：
    球1 = (第2+5+8+11+14+17位) 之和的末位  ← 索引 1,4,7,10,13,16
    球2 = (第3+6+9+12+15+18位) 之和的末位  ← 索引 2,5,8,11,14,17
    球3 = (第4+7+10+13+16+19位) 之和的末位 ← 索引 3,6,9,12,15,18
    特码 = 球1 + 球2 + 球3
    """
    if len(nums_20_sorted) != 20:
        raise ValueError(f"需要20个号码，收到 {len(nums_20_sorted)} 个")
    
    n = nums_20_sorted  # 已排序
    
    ball1 = (n[1] + n[4] + n[7] + n[10] + n[13] + n[16]) % 10
    ball2 = (n[2] + n[5] + n[8] + n[11] + n[14] + n[17]) % 10
    ball3 = (n[3] + n[6] + n[9] + n[12] + n[15] + n[18]) % 10
    
    sum_val = ball1 + ball2 + ball3
    
    return {
        'a': ball1,
        'b': ball2,
        'c': ball3,
        'sum': sum_val,
        'raw': list(n)  # 原始20码
    }

# ============================================================
# 3. 内置种子数据生成（接口失败时的真实感兜底）
# ============================================================

def _seeded_random(seed_str, min_val=0, max_val=79):
    """基于字符串种子的确定性随机（保证每次生成一样）"""
    h = hashlib.md5(seed_str.encode()).digest()
    vals = []
    for i in range(20):
        v = h[i % 16] ^ (i * 37)
        vals.append(min_val + (v % (max_val - min_val + 1)))
    return sorted(set(vals))  # 可能不足20，需要补

def generate_seed_draws(count=30, base_time=None):
    """
    生成本地种子数据（模拟 BCLC 真实分布）
    每个号码是 0-79 范围的 20 个不重复数字
    """
    if base_time is None:
        base_time = datetime.now(timezone(timedelta(hours=8)))
    
    draws = []
    for i in range(count):
        # 往回推 count-i 期
        t = base_time - timedelta(seconds=(count - i) * 210)
        
        seed_str = f"bclc_{t.strftime('%Y%m%d%H%M%S')}_{i}"
        random.seed(int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16))
        
        # 生成20个不重复号码 0-79
        nums = sorted(random.sample(range(0, 80), 20))
        
        # 解析为 PC28
        result = parse_20_to_pc28(nums)
        
        period = bj_to_period_number(t)
        
        draw = {
            'period': period,
            'date': t.strftime('%Y-%m-%d'),
            'time': t.strftime('%H:%M:%S'),
            'rawNums': nums,
            'a': result['a'],
            'b': result['b'],
            'c': result['c'],
            'sum': result['sum'],
            'source': 'seed'
        }
        draws.append(draw)
    
    return draws

# ============================================================
# 4. BCLC 官网抓取（带多路降级）
# ============================================================

import urllib.request
import ssl

def _http_get(url, timeout=10, headers=None):
    """简单的 HTTP GET（兼容沙盒环境）"""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode('utf-8')

def fetch_bclc_official():
    """
    从 BCLC 官方抓取最新开奖数据
    尝试多个已知接口端点
    """
    endpoints = [
        'https://www.bclc.com/content/dam/bclc/keno/results.json',
        'https://lotto.bclc.com/keno/results.json',
        'https://www.bclc.com/etc/designs/bclc/keno/latest.json',
    ]
    
    for url in endpoints:
        try:
            data = _http_get(url, timeout=8)
            parsed = json.loads(data)
            return _normalize_bclc_response(parsed)
        except Exception as e:
            print(f"  [BCLC] {url} 失败: {e}")
            continue
    
    return None

def _normalize_bclc_response(data):
    """将 BCLC 返回的各种格式统一为标准结构"""
    draws = []
    
    # BCLC 格式可能有多种，尝试适配
    items = data.get('draws', data.get('results', data.get('data', [])))
    if not items:
        # 可能直接是数组
        if isinstance(data, list):
            items = data
        else:
            return draws
    
    for item in items[:50]:
        try:
            # 尝试提取20个号码
            nums = item.get('numbers', item.get('nums', item.get('drawNumbers', [])))
            if isinstance(nums, str):
                nums = [int(x) for x in nums.split(',')]
            nums = sorted([int(x) for x in nums])
            
            if len(nums) != 20:
                continue
            
            result = parse_20_to_pc28(nums)
            
            draw_time = item.get('drawTime', item.get('time', ''))
            draw_date = item.get('drawDate', item.get('date', ''))
            
            draws.append({
                'period': item.get('drawNumber', item.get('period', '')),
                'date': draw_date,
                'time': draw_time,
                'rawNums': nums,
                'a': result['a'],
                'b': result['b'],
                'c': result['c'],
                'sum': result['sum'],
                'source': 'bclc_official'
            })
        except Exception as e:
            print(f"  [BCLC] 解析单条失败: {e}")
            continue
    
    return draws

# ============================================================
# 5. 第三方镜像接口（BCLC 数据转发）
# ============================================================

def fetch_bclc_mirror():
    """
    尝试从第三方镜像获取 BCLC Keno 数据
    这些站点转发 BCLC 开奖结果
    """
    mirrors = [
        {
            'name': 'yu28.top',
            'url': 'https://yu28.top/api/bclc?count=20',
            'parser': _parse_yu28
        },
        {
            'name': 'pc28.help bclc',
            'url': 'https://pc28.help/api/bclc.json',
            'parser': _parse_pc28help_bclc
        },
        {
            'name': 'corsproxy bclc',
            'url': 'https://corsproxy.io/?https://www.bclc.com/content/dam/bclc/keno/results.json',
            'parser': _normalize_bclc_response
        },
    ]
    
    for m in mirrors:
        try:
            print(f"  [Mirror] 尝试 {m['name']}...")
            data = _http_get(m['url'], timeout=8)
            parsed = json.loads(data)
            draws = m['parser'](parsed)
            if draws:
                print(f"  [Mirror] {m['name']} 成功: {len(draws)} 期")
                return draws
        except Exception as e:
            print(f"  [Mirror] {m['name']} 失败: {e}")
            continue
    
    return None

def _parse_yu28(data):
    """解析 yu28.top 返回格式"""
    draws = []
    items = data.get('data', data.get('list', []))
    if not items and isinstance(data, list):
        items = data
    for item in items[:50]:
        try:
            nums = item.get('nums', item.get('numbers', []))
            if isinstance(nums, str):
                nums = [int(x) for x in nums.split(',')]
            nums = sorted([int(x) for x in nums])
            if len(nums) != 20:
                continue
            r = parse_20_to_pc28(nums)
            draws.append({
                'period': item.get('qihao', item.get('period', '')),
                'date': item.get('date', ''),
                'time': item.get('time', ''),
                'rawNums': nums,
                'a': r['a'], 'b': r['b'], 'c': r['c'],
                'sum': r['sum'],
                'source': 'yu28'
            })
        except:
            continue
    return draws

def _parse_pc28help_bclc(data):
    """解析 pc28.help 的 bclc 格式"""
    draws = []
    items = data.get('data', data.get('list', []))
    if not items and isinstance(data, list):
        items = data
    for item in items[:50]:
        try:
            nums = item.get('rawNums', item.get('nums', []))
            if isinstance(nums, str):
                nums = [int(x) for x in nums.split(',')]
            nums = sorted([int(x) for x in nums])
            if len(nums) != 20:
                continue
            r = parse_20_to_pc28(nums)
            draws.append({
                'period': item.get('nbr', item.get('period', '')),
                'date': item.get('date', ''),
                'time': item.get('time', ''),
                'rawNums': nums,
                'a': r['a'], 'b': r['b'], 'c': r['c'],
                'sum': r['sum'],
                'source': 'pc28help_bclc'
            })
        except:
            continue
    return draws

# ============================================================
# 6. 统一入口
# ============================================================

def get_latest_data(prefer_count=30):
    """
    统一数据获取入口
    优先级：BCLC官方 → 第三方镜像 → 本地种子
    
    返回：
    {
        'success': bool,
        'source': 'bclc_official' | 'mirror' | 'seed',
        'draws': [...],
        'countdown': int,
        'nextDraw': 'YYYY-MM-DD HH:MM:SS',
        'isOpen': bool,
        'timezone': 'PDT' | 'PST',
        'message': str
    }
    """
    now_bj = datetime.now(timezone(timedelta(hours=8)))
    _, is_dst = get_bclc_timezone(now_bj.astimezone(timezone.utc))
    tz_name = 'PDT' if is_dst else 'PST'
    
    result = {
        'success': False,
        'source': 'none',
        'draws': [],
        'countdown': 0,
        'nextDraw': '',
        'isOpen': is_bclc_open(now_bj),
        'timezone': tz_name,
        'message': ''
    }
    
    # 倒计时
    cd, next_t = get_next_draw_time(now_bj)
    result['countdown'] = cd
    result['nextDraw'] = next_t.strftime('%Y-%m-%d %H:%M:%S')
    
    # 1️⃣ 尝试 BCLC 官方
    print("[Data] 尝试 BCLC 官方接口...")
    draws = fetch_bclc_official()
    if draws:
        result['success'] = True
        result['source'] = 'bclc_official'
        result['draws'] = draws[:prefer_count]
        result['message'] = f'BCLC官方数据 {len(result["draws"])}期'
        return result
    
    # 2️⃣ 尝试第三方镜像
    print("[Data] 尝试第三方镜像...")
    draws = fetch_bclc_mirror()
    if draws:
        result['success'] = True
        result['source'] = draws[0].get('source', 'mirror')
        result['draws'] = draws[:prefer_count]
        result['message'] = f'镜像数据 {len(result["draws"])}期'
        return result
    
    # 3️⃣ 本地种子兜底
    print("[Data] 使用本地种子数据...")
    seed_draws = generate_seed_draws(prefer_count, now_bj)
    # 补齐期号
    for d in seed_draws:
        if not d['period']:
            d['period'] = bj_to_period_number(
                datetime.strptime(f"{d['date']} {d['time']}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=8)))
            )
        d['source'] = 'seed'
    result['success'] = True
    result['source'] = 'seed'
    result['draws'] = seed_draws
    result['message'] = f'本地种子数据 {len(seed_draws)}期（接口不可用）'
    
    return result

# ============================================================
# 7. PC28 辅助函数
# ============================================================

def sum_to_combo(sum_val):
    """和值 → 大小单双组合"""
    if sum_val < 14:
        size = '小'
    else:
        size = '大'
    parity = '单' if sum_val % 2 == 1 else '双'
    return f"{size}{parity}"

def detect_pattern(a, b, c):
    """检测形态：豹子/对子/顺子/杂六"""
    nums = sorted([a, b, c])
    if a == b == c:
        return '豹子'
    if a == b or b == c or a == c:
        return '对子'
    # 顺子检测
    if nums[1] - nums[0] == 1 and nums[2] - nums[1] == 1:
        return '顺子'
    return '杂六'

# ============================================================
# 8. 测试入口
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("BCLC Keno → PC28 数据接口测试")
    print("=" * 60)
    
    # 测试1：解析逻辑
    print("\n【测试1】20码→PC28解析")
    test_nums = sorted(random.sample(range(0, 80), 20))
    print(f"  20码: {test_nums}")
    r = parse_20_to_pc28(test_nums)
    print(f"  球1={r['a']} 球2={r['b']} 球3={r['c']} 特码={r['sum']}")
    print(f"  组合: {sum_to_combo(r['sum'])}  形态: {detect_pattern(r['a'],r['b'],r['c'])}")
    
    # 测试2：开奖时间
    print("\n【测试2】开奖时间判断")
    now = datetime.now(timezone(timedelta(hours=8)))
    _, is_dst = get_bclc_timezone(now.astimezone(timezone.utc))
    print(f"  当前北京时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  时区: {'PDT(夏令时)' if is_dst else 'PST(冬令时)'}")
    print(f"  是否开奖中: {is_bclc_open(now)}")
    cd, next_t = get_next_draw_time(now)
    print(f"  下一期: {next_t.strftime('%Y-%m-%d %H:%M:%S')} (倒计时 {cd}秒)")
    print(f"  当期期号: {bj_to_period_number(now)}")
    
    # 测试3：种子数据
    print("\n【测试3】本地种子数据生成")
    seeds = generate_seed_draws(5)
    for s in seeds:
        combo = sum_to_combo(s['sum'])
        pattern = detect_pattern(s['a'], s['b'], s['c'])
        print(f"  {s['period']} | {s['date']} {s['time']} | "
              f"20码前5={s['rawNums'][:5]}... | "
              f"球={s['a']}{s['b']}{s['c']} 和={s['sum']} {combo} {pattern}")
    
    # 测试4：完整数据获取
    print("\n【测试4】完整数据获取流程")
    data = get_latest_data(10)
    print(f"  成功: {data['success']}")
    print(f"  来源: {data['source']}")
    print(f"  信息: {data['message']}")
    print(f"  开奖中: {data['isOpen']}  时区: {data['timezone']}")
    print(f"  倒计时: {data['countdown']}秒")
    print(f"  下一期: {data['nextDraw']}")
    print(f"  数据条数: {len(data['draws'])}")
    for d in data['draws'][:3]:
        print(f"    {d['period']} | {d.get('date','')} {d.get('time','')} | "
              f"球={d['a']}{d['b']}{d['c']} 和={d['sum']} 来源={d['source']}")
    
    print("\n" + "=" * 60)
    print("✅ 接口模块测试完成")
    print("=" * 60)
