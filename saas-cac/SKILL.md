---
name: saas-cac
description: Calculate and explain SaaS customer acquisition cost (CAC), gross-margin payback, LTV/CAC, channel efficiency, funnel conversion, trends, and cohort payback from finance and growth data. Use for SaaS acquisition-spend reviews, budget decisions, or CAC dashboard requests; do not use as a substitute for audited accounting or cash-flow forecasting.
---

# SaaS CAC

Turn an agreed acquisition-cost scope and customer denominator into reproducible SaaS unit economics. Use `scripts/calculate_cac.py` for arithmetic instead of estimating by hand.

## Workflow

1. Confirm the period, currency, cost scope, and that the denominator is **new paying customers acquired in the same period**. Do not silently replace it with leads, registrations, trials, or all active customers.
2. Ask for the minimum inputs: `acquisition_costs` and `new_paying_customers`. For payback, also obtain `mrr`, `active_paying_customers`, and `gross_margin_rate`.
3. Build a JSON input that follows [references/input-schema.md](references/input-schema.md). Keep missing values missing; never invent a zero or a benchmark.
4. Run:

   ```text
   python scripts/calculate_cac.py INPUT.json --format markdown --view full
   ```

5. Report the formula, substituted values, result, and any warnings. Label `cac_payback_months` as a blended gross-margin proxy when average active-customer economics are used.
6. Recommend a budget decision only after checking retention, collection timing, channel mix, and whether costs and customers reconcile to the same period and attribution rule.

## Parameters and outputs

- Required: `period`, `currency`, `acquisition_costs` (number or category map), `new_paying_customers`.
- Payback inputs: `mrr`, `active_paying_customers`, `gross_margin_rate` (`0.6` or `"60%"`).
- Optional LTV inputs: `monthly_logo_churn_rate`.
- Optional views: `channels`, `funnel`, `history`, and `cohorts`.
- CLI formats: `json`, `markdown`, or `csv`; views: `summary`, `channels`, `funnel`, `trend`, `cohorts`, or `full`.
- Primary outputs: total acquisition cost, CAC, ARPA, monthly gross profit per customer, gross-margin CAC payback, gross-margin LTV, and LTV/CAC.

Read [references/input-schema.md](references/input-schema.md) when preparing or validating data. Read [references/dashboard-patterns.md](references/dashboard-patterns.md) when choosing a presentation view or adapting the output for a dashboard.

## Guardrails

- Include only costs attributable to acquiring new customers under the chosen policy. State whether sales payroll, marketing payroll, commissions, agencies, tools, events, and allocated overhead are included.
- A zero customer count makes CAC undefined; preserve `null` and the warning rather than dividing by zero.
- Payback uses gross profit, not revenue: `CAC / (ARPA × gross margin)`.
- LTV based on logo churn is a simplified steady-state estimate. Do not present it as a valuation or realized cash return.
- Do not approve spend merely because blended payback is short. Surface missing retention, cohort, cash-collection, or attribution evidence.
- Preserve the input currency; do not convert currencies without an explicit rate and date.
