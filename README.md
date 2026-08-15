# 千金星轨 · PC28 星轨引擎

> BCLK Keno 核心算法 + QianJinU 预测引擎 · 纯前端零依赖 · GitHub Pages 免费托管

## 🌐 在线地址

**https://tomf02391-crypto.github.io/qianjinalgorithm/**

## ✨ 功能

| 模块 | 说明 |
|------|------|
| ⏱ 实时倒计时 | PC28 每 3.5 分钟一期，SVG 圆环动画 |
| 🔢 三球计算 | BCLK Keno 20码 → 取位求和取末位 → 特码 |
| 📊 术语分析 | 大小/单双/组合/极值/形态（豹子·对子·顺子·杂六） |
| 🤖 星轨预测 | 形态频率 + 连龙检测 + 加权移动平均 |
| 🎲 特码精选 | 概率权重 + 冷热修正 + 尾数去重 |
| 📈 回测统计 | 押组命中 / 杀组正确 / 和值±2 / V3融合 |
| 🐉 连龙检测 | 5期同形态自动反转预测 |
| 📜 历史记录 | 最近50期开奖 + 20期结果比对 |

## 🔧 核心算法（移植自 pc28_api.py）

```javascript
// BCLK Keno 规则：20码排序后取位求和取末位
const pos1 = [1, 4, 7, 10, 13, 16];  // → 第一球
const pos2 = [2, 5, 8, 11, 14, 17];  // → 第二球
const pos3 = [3, 6, 9, 12, 15, 18];  // → 第三球
// 三球之和 = 特码 (0-27)

// 术语判定
// 0-13 小 / 14-27 大
// 奇数单 / 偶数双
// 0-5 极小 / 22-27 极大
// 三球相同=豹子 / 两球同=对子 / 顺子=顺子 / 否则=杂六
```

## 📦 部署

### 自动部署（推荐）

1. Fork / Clone 本仓库
2. **Settings → Pages → Source: GitHub Actions**
3. 手动跑一次 **Actions → 更新PC28数据快照 → Run workflow**
4. 之后每 5 分钟自动更新 `data.json`

### 手动部署

```bash
git clone https://github.com/tomf02391-crypto/qianjinalgorithm.git
cd qianjinalgorithm
python3 fetch_data.py    # 生成本地 data.json
# 打开 index.html 即可使用
```

## 📁 文件结构

```
qianjinalgorithm/
├── index.html              # 主页面（单文件，CSS+JS全内联，零依赖）
├── data.json              # 数据快照（121期真实数据 + AI预测）
├── fetch_data.py         # 数据构建脚本（纯本地，不访问网络）
├── seed_data.py          # 备用数据模块
├── predict.py            # 独立预测模块
├── .github/workflows/
│   └── update-data.yml  # GitHub Actions 自动更新
├── .nojekyll             # 禁用 Jekyll
└── README.md
```

## ⚠️ 数据说明

- 所有开奖数据均为**真实历史开奖结果**
- 数据来源：BCLK Keno 官方开奖记录
- 预测算法为**概率统计模型**，仅供参考
- **赌博有害，理性对待**

## 🔒 数据源状态

| 源 | 状态 |
|----|------|
| pc28.help | ❌ Cloudflare 403 拦截 |
| yu28.top | ❌ Cloudflare 403 拦截 |
| 内置真实数据 | ✅ 121期（08-07~08-14） |
| 本地算法 | ✅ 零网络依赖 |

由于第三方 API 全部被 Cloudflare 防护，本版本采用**纯本地计算**架构：
- 前端 JS 内置完整 BCLK Keno 算法
- 内置 121 期真实开奖数据
- 所有预测在浏览器本地完成
- 无需任何后端服务
