# 千金星轨 · PC28 星轨引擎

> BCLK Keno 算法 · 直连 pc28.help · 期号日期实时同步

## 数据源

**pc28.help/api/keno.json** — 每次返回最新一期开奖数据，包含：
- `nbr` 期号
- `date` 日期（如 2026-08-16）
- `time` 时间（如 23:31:00）
- `nbrs` 20个原始号码（逗号分隔）
- `bonus` 特码
- `countdown` 距下期倒计时

## 工作原理

```
pc28.help 接口（浏览器直连）
       ↓ 返回原始20码
前端 JS 实时计算三球（calcBalls）
       ↓ b1+b2+b3 = 和值
分析大小单双/组合/形态
       ↓
QianJinU V4 预测引擎（多信号融合）
       ↓
渲染到页面 + 存入 localStorage
```

## 部署

### GitHub Pages（纯前端，推荐）

1. Fork/Clone 本仓库
2. Settings → Pages → Source: `GitHub Actions`
3. 推送代码后自动部署
4. 访问 `https://<user>.github.io/<repo>/`

### 本地运行

直接用浏览器打开 `index.html` 即可（需联网访问 pc28.help）

## 文件说明

| 文件 | 作用 |
|------|------|
| `index.html` | 主页面（单文件，CSS+JS全内联） |
| `fetch_data.py` | GitHub Actions 用数据抓取脚本 |
| `_seed_data.py` | 生成初始 data.json |
| `predict.py` | 独立预测模块（可单独运行测试） |
| `data.json` | 初始种子数据（前端运行时自动更新） |

## 算法说明

- **calcBalls**: 20码排序 → 3组间隔位置求和取末位 → 三球
- **analyze**: 三球求和 → 大小单双/组合/极值/形态(豹子/对子/顺子/杂六)
- **predictNextV4**: 5路信号加权投票（衰减频率/马尔可夫/和值趋势/连号反转/奇偶交替）
- **置信度诚实标注**: 上限55%，PC28本质近似均匀分布

## 注意事项

- pc28.help 对部分服务端IP有 Cloudflare WAF 限制
- 前端浏览器直连不受影响
- Actions 抓取失败时保留旧 data.json（不会清空数据）
- localStorage 在浏览器端累积历史（最多500期）

## 免责声明

仅供算法研究参考，不构成任何投注建议。
