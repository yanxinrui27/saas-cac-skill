# SaaS 获客成本（CAC）财务技能

`saas-cac` 是一个本地、无第三方依赖的财务技能，用统一口径计算 SaaS 公司的获客成本（CAC）、客均月收入（ARPA）、单客月毛利、毛利 CAC 回收期、简化毛利 LTV 和 LTV/CAC，并可拆解渠道、漏斗、趋势及客户批次（cohort）。适用于月度经营复盘、投放预算讨论、渠道效率比较和财务口径核验；不替代审计、现金流预测或预算审批。

## 快速使用

运行环境需要 Python 3.10 或更高版本，无需安装依赖。先准备 UTF-8 JSON 文件，例如 `input.json`：

```json
{
  "period": "2026-09",
  "currency": "CNY",
  "acquisition_costs": {
    "paid_media": 200000,
    "sales_payroll": 100000
  },
  "new_paying_customers": 100,
  "mrr": 500000,
  "active_paying_customers": 500,
  "gross_margin_rate": "60%",
  "monthly_logo_churn_rate": "2%"
}
```

在项目根目录调用：

```powershell
python saas-cac/scripts/calculate_cac.py input.json --format markdown --view summary
```

也可以从标准输入读取（将文件位置写成 `-`），或用 `--output result.md` 保存结果。

### 参数配置

| 参数 | 必填 | 说明 |
|---|---|---|
| `period` | 是 | 成本与新增付费客户共同覆盖的统计期间 |
| `currency` | 是 | 结果展示币种，例如 `CNY`、`USD`；程序不自动换汇 |
| `acquisition_costs` | 是 | 获客成本总额，或“成本类别: 金额”对象 |
| `new_paying_customers` | 是 | 同期新增付费客户数；不能用注册数、线索数或全部活跃客户代替 |
| `mrr` | 回收期需要 | 月度经常性收入 |
| `active_paying_customers` | 回收期需要 | 与 MRR 对应的活跃付费客户数 |
| `gross_margin_rate` | 回收期需要 | `0.6` 或 `"60%"`；为避免单位误判，不接受数字 `60` |
| `monthly_logo_churn_rate` | LTV 需要 | 月度客户流失率，例如 `"2%"` |
| `channels` | 否 | 渠道成本和新增客户明细 |
| `funnel` | 否 | 从访客到新增付费客户的漏斗阶段数量 |
| `history` | 否 | 多期同口径记录，用于趋势比较 |
| `cohorts` | 否 | 客户批次的成本、客户数和单客月毛利 |

命令参数：`--format` 可选 `markdown`、`json`、`csv`；`--view` 可选 `summary`、`channels`、`funnel`、`trend`、`cohorts`、`full`。

## 计算口径

- `CAC = 获客成本总额 ÷ 新增付费客户数`
- `ARPA = MRR ÷ 活跃付费客户数`
- `单客月毛利 = ARPA × 毛利率`
- `毛利 CAC 回收期 = CAC ÷ 单客月毛利`
- `简化毛利 LTV = 单客月毛利 ÷ 月度客户流失率`
- `LTV/CAC = 简化毛利 LTV ÷ CAC`

示例数据的 CAC 为 `300,000 ÷ 100 = CNY 3,000`，收入口径看似 3 个月回收，但毛利口径为 `3,000 ÷ (1,000 × 60%) = 5 个月`。技能使用后者，避免把收入等同于可回收毛利。

## 三种输出示例

### 1. Markdown 管理层摘要

调用：

```powershell
python saas-cac/scripts/calculate_cac.py input.json --format markdown --view summary
```

输出片段：

```markdown
| Metric | Value |
|---|---:|
| Acquisition cost | CNY 300,000.00 |
| New paying customers | 100 |
| CAC | CNY 3,000.00 |
| Gross-margin payback | 5.00 months |
| LTV / CAC | 10.00x |
```

### 2. JSON 系统对接结果

调用：

```powershell
python saas-cac/scripts/calculate_cac.py input.json --format json
```

输出片段：

```json
{
  "meta": {"period": "2026-09", "currency": "CNY"},
  "summary": {
    "total_acquisition_cost": 300000,
    "new_paying_customers": 100,
    "cac": 3000,
    "arpa": 1000,
    "monthly_gross_profit_per_customer": 600,
    "cac_payback_months": 5,
    "gross_margin_ltv": 30000,
    "ltv_to_cac": 10
  }
}
```

### 3. CSV 渠道明细

输入中增加 `channels` 后调用：

```powershell
python saas-cac/scripts/calculate_cac.py input.json --format csv --view channels
```

输出片段：

```csv
view,item,metric,value
channels,Paid search,total_acquisition_cost,180000.00
channels,Paid search,new_paying_customers,70
channels,Paid search,cac,2571.43
channels,Paid search,cost_share,0.6000
```

## 五种看板呈现模式

技能参考并实现了五种常见决策视图：管理层 KPI 卡片（`summary`）、渠道效率表（`channels`）、获客漏斗（`funnel`）、多期趋势（`trend`）和批次回收表（`cohorts`）。`--view full` 会合并全部视图；缺失的可选数据会明确显示为空，而不会臆造数值。

## 验证与注意事项

运行单元测试：

```powershell
python -m unittest discover -s saas-cac/tests -v
```

运行技能结构验证：

```powershell
python C:/Users/Sienna/.codex/skills/.system/skill-creator/scripts/quick_validate.py saas-cac
```

- 成本范围必须先约定，并说明是否包含销售/市场人员成本、佣金、代理商、工具、活动及分摊费用。
- 成本与新增客户必须使用同一期间、同一归因规则。渠道合计不一致时程序会提示。
- 零新增客户不会被强行除数计算，相关结果返回 `null` 并附警告。
- 回收期是基于平均活跃客户毛利的混合估算；投放决策仍需复核新客收入、留存、账期和现金回款。
