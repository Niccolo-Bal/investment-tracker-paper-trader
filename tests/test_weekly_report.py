"""Focused tests for weekly reporting boundaries and cash-flow math."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import weekly_market as wm


class ReportingPeriodTests(unittest.TestCase):
    def test_friday_before_cutoff_uses_prior_week(self):
        local = datetime.now().astimezone().tzinfo
        friday_morning = datetime(2026, 7, 17, 10, 0, tzinfo=local)
        start, end = wm.reporting_period(friday_morning)
        self.assertEqual(end.weekday(), 4)
        self.assertEqual(end.hour, 16)
        self.assertEqual(end.minute, 30)
        self.assertEqual(start, end - timedelta(days=7))
        self.assertLess(end, friday_morning)

    def test_saturday_catchup_keeps_friday_window(self):
        local = datetime.now().astimezone().tzinfo
        saturday = datetime(2026, 7, 18, 12, 0, tzinfo=local)
        start, end = wm.reporting_period(saturday)
        self.assertEqual(end.date().isoformat(), "2026-07-17")
        self.assertEqual(start.date().isoformat(), "2026-07-10")


class ModifiedDietzTests(unittest.TestCase):
    def test_no_cash_flows_equals_simple_return(self):
        local = datetime.now().astimezone().tzinfo
        start = datetime(2026, 7, 10, 16, 30, tzinfo=local)
        end = datetime(2026, 7, 17, 16, 30, tzinfo=local)
        pct = wm._modified_dietz(1000.0, 50.0, [], start, end)
        self.assertAlmostEqual(pct, 5.0, places=4)

    def test_buy_midweek_weights_capital(self):
        local = datetime.now().astimezone().tzinfo
        start = datetime(2026, 7, 10, 16, 30, tzinfo=local)
        end = datetime(2026, 7, 17, 16, 30, tzinfo=local)
        mid = start + timedelta(days=3.5)
        # Start 1000, buy 1000 mid-period, end 2200 => pnl = 200
        pct = wm._modified_dietz(1000.0, 200.0, [(mid, 1000.0)], start, end)
        self.assertIsNotNone(pct)
        self.assertGreater(pct, 10.0)
        self.assertLess(pct, 20.0)

    def test_zero_denominator_returns_none(self):
        local = datetime.now().astimezone().tzinfo
        start = datetime(2026, 7, 10, 16, 30, tzinfo=local)
        end = datetime(2026, 7, 17, 16, 30, tzinfo=local)
        self.assertIsNone(wm._modified_dietz(0.0, 10.0, [], start, end))


class CashFlowPnlTests(unittest.TestCase):
    def test_buy_then_appreciation_is_not_full_end_value(self):
        # V0=0, buy 1000, end 1050 => pnl 50
        pnl = 1050.0 - 0.0 - 1000.0 + 0.0
        self.assertEqual(pnl, 50.0)

    def test_sale_above_start_value_is_gain(self):
        # V0=1000, sell 1100, V1=0 => pnl 100
        pnl = 0.0 - 1000.0 - 0.0 + 1100.0
        self.assertEqual(pnl, 100.0)


class PriceFallbackTests(unittest.TestCase):
    def test_price_on_or_before_skips_missing_days(self):
        from datetime import date

        closes = {
            date(2026, 7, 16): 100.0,  # Thursday
            date(2026, 7, 15): 99.0,
        }
        day, price = wm._price_on_or_before(closes, date(2026, 7, 17))  # Friday holiday-ish
        self.assertEqual(day, date(2026, 7, 16))
        self.assertEqual(price, 100.0)


class EnrichmentFallbackTests(unittest.TestCase):
    def test_enrichment_failure_returns_empty_bags(self):
        original = wm.yf.Ticker

        class Boom:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError("yahoo down")

        wm.yf.Ticker = Boom
        try:
            wm._ENRICHMENT_CACHE.clear()
            payload = wm._symbol_enrichment("AAPL")
            self.assertEqual(payload["news"], [])
            self.assertEqual(payload["events"], {})
        finally:
            wm.yf.Ticker = original


if __name__ == "__main__":
    unittest.main()
