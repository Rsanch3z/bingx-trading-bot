import unittest

from src.models import Signal, SignalSide
from src.risk import build_position_plan
from src.sizing import kelly_fraction


class SizingTest(unittest.TestCase):
    def test_kelly_fraction_positive_edge(self) -> None:
        self.assertEqual(round(kelly_fraction(0.5, 1.5), 4), 0.1667)

    def test_kelly_fraction_no_edge_returns_zero(self) -> None:
        self.assertEqual(kelly_fraction(0.4, 1.0), 0.0)

    def test_position_size_is_capped_by_risk_limit(self) -> None:
        signal = Signal(
            side=SignalSide.LONG,
            reason="test",
            entry_price=100.0,
            stop_loss_price=95.0,
            take_profit_price=110.0,
        )
        plan = build_position_plan(
            signal=signal,
            equity_usdt=10.0,
            win_rate=0.5,
            win_loss_ratio=1.5,
            max_kelly_fraction=0.05,
            max_risk_per_trade_pct=0.02,
            leverage=1,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(round(plan.risk_usdt, 4), 0.2)
        self.assertEqual(round(plan.notional_usdt, 4), 4.0)


if __name__ == "__main__":
    unittest.main()
