# 千金星轨 · PC28 星轨引擎

> **BCLK Keno 算法 · 直连 pc28.help · 仅真实开奖数据 · 绝无模拟**

## ✅ 数据真实性保证

本项目**绝不生成、伪造、模拟任何开奖数据**。所有数据必须来自 `pc28.help` 的真实 API 返回。

| 层级 | 数据源 | 降级策略 |
|------|---------|---------|
| **前端（浏览器）** | 直连 `pc28.help/api/keno.json` | → localStorage 缓存 → data.json 种子 |
| **服务端（Actions）** | `fetch_data.py` 请求 pc28.help | → 保留旧 data.json 不变 |
| **本地验证** | 原始20码 → calcBalls() → 和值 | 校验失败的数据直接丢弃 |

## 数据校验规则

每条记录必须经过以下验证才能被使用：
1. `rawNums` 必须有 ≥19 个有效数字
2. `a + b + c` 必须等于 `sum`
3. `sum` 必须在 [0, 27] 范围内
4. `date` 和 `time` 字段必须来自接口原始返回

## 文件说明

| 文件 | 作用 |
|------|------|
| `index.html` | 主页面（单文件零依赖，CSS+JS全内联） |
| `fetch_data.py` | Actions 数据抓取（多层降级，绝不造假） |
| `_seed_data.py` | 本地生成初始 data.json |
| `predict.py` | 独立预测模块（可单独运行测试） |
| `data.json` | 种子数据（10期真实开奖，前端自动累积更多） |
| `.github/workflows/update-data.yml` | 每5分钟自动更新 |

## 快速部署

```bash
# 1. 推送到 GitHub
git init && git add . && git commit -m "init"
git remote add origin https://github.com/tomf02391-crypto/qianjinalgorithm.git
git push -u origin main

# 2. 开启 Pages
# Settings → Pages → Source: GitHub Actions

# 3. 手动跑一次 Actions
# Actions → 更新PC28数据快照 → Run workflow
```

## 算法说明

- **calcBalls**: 20码排序 → 3组间隔位置求和取末位 → 三球 → 和值
- **analyze**: 和值 → 大小单双/组合(大单大双小单小双)/极值/形态(豹子对子顺子杂六)
- **predictNextV4**: 5路信号加权投票（衰减频率/马尔可夫-2/和值趋势/连号反转/奇偶交替）
- **置信度诚实标注**: 上限55%，因PC28本质近似均匀分布

## ⚠️ 重要提醒

**赌博有害，理性对待。** 本工具仅供算法研究参考，不构成任何投注建议。
PC28 是基于 BCLK Keno 的衍生玩法，开奖结果近似均匀分布，任何声称"稳赚"的工具都是骗局。

## 数据源

- 主源: `https://pc28.help/api/keno.json`
- 备用: `https://yu28.top/api/keno.json`（pc28.help 官方公告的迁移域名）
- 所有数据均来自 BCLC（加拿大不列颠哥伦比亚省彩票公司）官方开奖
