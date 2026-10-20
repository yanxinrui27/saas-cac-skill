import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "calculate_cac.py"
SPEC = importlib.util.spec_from_file_location("calculate_cac", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def base_payload():
    return {
        "period": "2026-09",
        "currency": "CNY",
        "acquisition_costs": {"paid_media": 200000, "sales_payroll": 100000},
        "new_paying_customers": 100,
        "mrr": 500000,
        "active_paying_customers": 500,
        "gross_margin_rate": "60%",
        "monthly_logo_churn_rate": "2%",
    }


class CalculationTests(unittest.TestCase):
    def test_reference_case_uses_gross_profit_for_five_month_payback(self):
        result = MODULE.calculate(base_payload())
        summary = result["summary"]
        self.assertEqual(summary["cac"], Decimal("3000.00"))
        self.assertEqual(summary["arpa"], Decimal("1000.00"))
        self.assertEqual(
            summary["monthly_gross_profit_per_customer"], Decimal("600.00")
        )
        self.assertEqual(summary["cac_payback_months"], Decimal("5.00"))
        self.assertEqual(summary["gross_margin_ltv"], Decimal("30000.00"))
        self.assertEqual(summary["ltv_to_cac"], Decimal("10.0000"))

    def test_zero_new_customers_returns_null_with_warning(self):
        payload = base_payload()
        payload["new_paying_customers"] = 0
        result = MODULE.calculate(payload)
        self.assertIsNone(result["summary"]["cac"])
        self.assertIsNone(result["summary"]["cac_payback_months"])
        self.assertTrue(any("undefined" in item for item in result["warnings"]))

    def test_ambiguous_numeric_percentage_is_rejected(self):
        payload = base_payload()
        payload["gross_margin_rate"] = 60
        with self.assertRaisesRegex(MODULE.InputError, "percentage string"):
            MODULE.calculate(payload)

    def test_channel_reconciliation_and_all_five_views(self):
        payload = base_payload()
        payload.update(
            {
                "channels": [
                    {"name": "Search", "acquisition_costs": 180000, "new_paying_customers": 70},
                    {"name": "Events", "acquisition_costs": 100000, "new_paying_customers": 25},
                ],
                "funnel": {"leads": 2000, "mqls": 800, "new_paying_customers": 100},
                "history": [
                    {
                        "period": "2026-08",
                        "acquisition_costs": 250000,
                        "new_paying_customers": 100,
                        "mrr": 480000,
                        "active_paying_customers": 480,
                        "gross_margin_rate": "60%",
                    }
                ],
                "cohorts": [
                    {
                        "cohort": "2026-09",
                        "acquisition_costs": 300000,
                        "new_paying_customers": 100,
                        "monthly_gross_profit_per_customer": 600,
                    }
                ],
            }
        )
        result = MODULE.calculate(payload)
        self.assertEqual(len(result["channels"]), 2)
        self.assertEqual(len(result["funnel"]), 3)
        self.assertEqual(len(result["trend"]), 2)
        self.assertEqual(result["cohorts"][0]["cac_payback_months"], Decimal("5.00"))
        self.assertTrue(any("do not reconcile" in item for item in result["warnings"]))
        dashboard = MODULE.render_markdown(result, "full")
        for heading in (
            "Executive scorecard",
            "Channel efficiency",
            "Acquisition funnel",
            "Period trend",
            "Cohort payback",
        ):
            self.assertIn(heading, dashboard)

    def test_cli_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(base_payload()), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--format", "json"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        output = json.loads(completed.stdout)
        self.assertEqual(output["summary"]["cac_payback_months"], 5)

    def test_csv_output_is_tidy_and_parseable(self):
        payload = base_payload()
        payload["channels"] = [
            {"name": "Paid search", "acquisition_costs": 300000, "new_paying_customers": 100}
        ]
        result = MODULE.calculate(payload)
        output = MODULE.render_csv(result, "channels")
        self.assertIn("view,item,metric,value", output)
        self.assertIn("channels,Paid search,cac,3000.00", output)

    def test_negative_cost_is_rejected(self):
        payload = base_payload()
        payload["acquisition_costs"] = -1
        with self.assertRaisesRegex(MODULE.InputError, "non-negative"):
            MODULE.calculate(payload)


if __name__ == "__main__":
    unittest.main()
