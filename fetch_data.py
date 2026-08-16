#!/usr/bin/env python3
"""V8 服务端数据抓取"""
import urllib.request, json, sys

def fetch_keno(n=100):
    req = urllib.request.Request(
        "https://pc28.help/api/keno.json?nbr=" + str(n),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

def parse_item(item):
    ns = [int(x) for x in item.get("nbrs", "").split(",") if x.strip()]
    if len(ns) < 19: return None
    s = sorted(ns)
    b1 = sum(s[i] for i in [1,4,7,10,13,16]) % 10
    b2 = sum(s[i] for i in [2,5,8,11,14,17]) % 10
    b3 = sum(s[i] for i in [3,6,9,12,15,18]) % 10
    total = b1 + b2 + b3
    combo = ("大" if total >= 14 else "小") + ("单" if total % 2 == 1 else "双")
    return {"nbr": str(item.get("nbr","")), "date": item.get("date",""),
            "time": item.get("time",""), "a": b1, "b": b2, "c": b3,
            "number": f"{b1}+{b2}+{b3}={total}", "sum": total, "combo": combo,
            "rawNums": ns}

def main():
    try:
        data = fetch_keno(100)
        items = data.get("data", [])
        records = []
        for it in items:
            r = parse_item(it)
            if r: records.append(r)
        seen = set()
        uniq = []
        for r in sorted(records, key=lambda x: int(x["nbr"])):
            if r["nbr"] not in seen:
                seen.add(r["nbr"])
                uniq.append(r)
        uniq = uniq[-200:]
        with open("data.json", "w") as f:
            json.dump({"data": uniq}, f, ensure_ascii=False, indent=2)
        print(f"✅ 更新 {len(uniq)} 期")
    except Exception as e:
        print(f"⚠️ 抓取失败: {e}", file=sys.stderr)
        sys.exit(0)

if __name__ == "__main__": main()
