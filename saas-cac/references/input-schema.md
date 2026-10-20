# Input schema

All money values use the top-level `currency`. Costs and customer counts must cover the same acquisition period and attribution rule.

## Required fields

| Field | Type | Meaning |
|---|---|---|
| `period` | string | Reporting period, for example `2026-09` |
| `currency` | string | ISO-style display code, for example `CNY` |
| `acquisition_costs` | number or object | Total acquisition cost or a category-to-amount map |
| `new_paying_customers` | integer | Newly acquired paying customers in the period |

## Payback and LTV fields

| Field | Type | Meaning |
|---|---|---|
| `mrr` | number | Period-end or average monthly recurring revenue; state the policy consistently |
| `active_paying_customers` | integer | Paying customers represented by MRR |
| `gross_margin_rate` | decimal or percent string | `0.6` or `"60%"`; numeric `60` is rejected |
| `monthly_logo_churn_rate` | decimal or percent string | Optional simplified steady-state LTV input |

Recommended cost categories are `paid_media`, `sales_payroll`, `marketing_payroll`, `commissions`, `agencies`, `tools`, `events`, and `allocated_overhead`. Other names are accepted.

## Optional dashboard arrays

- `channels`: rows with `name`, `acquisition_costs`, and `new_paying_customers`. Payback fields may also be supplied per channel.
- `funnel`: an object using any ordered subset of `visitors`, `leads`, `mqls`, `sqls`, `opportunities`, and `new_paying_customers`.
- `history`: rows with `period` plus the same metric fields as the top-level summary.
- `cohorts`: rows with `cohort`, `acquisition_costs`, `new_paying_customers`, and `monthly_gross_profit_per_customer`.

## Complete example

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
  "monthly_logo_churn_rate": "2%",
  "channels": [
    {"name": "Paid search", "acquisition_costs": 180000, "new_paying_customers": 70},
    {"name": "Events", "acquisition_costs": 120000, "new_paying_customers": 30}
  ],
  "funnel": {"visitors": 20000, "leads": 2000, "mqls": 800, "sqls": 300, "opportunities": 160, "new_paying_customers": 100},
  "cohorts": [
    {"cohort": "2026-09", "acquisition_costs": 300000, "new_paying_customers": 100, "monthly_gross_profit_per_customer": 600}
  ]
}
```

The calculator rejects negative money or counts, fractional customer counts, booleans, non-finite values, duplicate channel names, and ambiguous numeric percentage values greater than 1.
