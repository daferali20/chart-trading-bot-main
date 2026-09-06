from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class RobustnessScore:
    score: float
    components: dict[str, float]
    warnings: tuple[str, ...]


class RobustnessScorer:
    """Score strategy quality with an explicit generalization penalty.

    Expected metric conventions:
      return: decimal return, e.g. 0.12 for +12%
      profit_factor: ratio
      win_rate: 0..1
      sharpe: ratio
      max_drawdown: positive decimal magnitude, e.g. 0.08
      stability: 0..1 (optional)
      trade_concentration: 0..1 (optional; lower is better)
    """

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    def score(
        self,
        in_sample: Mapping[str, float],
        out_of_sample: Mapping[str, float],
        *,
        stability: float | None = None,
        trade_concentration: float | None = None,
    ) -> RobustnessScore:
        oos_return = float(out_of_sample.get("return", 0.0))
        oos_pf = float(out_of_sample.get("profit_factor", 0.0))
        oos_win = float(out_of_sample.get("win_rate", 0.0))
        oos_sharpe = float(out_of_sample.get("sharpe", 0.0))
        oos_dd = abs(float(out_of_sample.get("max_drawdown", 0.0)))

        # Positive OOS return earns up to 20 points at +50% or above.
        return_points = 20.0 * self._clip(oos_return / 0.50, 0.0, 1.0)
        # PF 1.0 is break-even quality; 3.0+ receives full points.
        pf_points = 15.0 * self._clip((oos_pf - 1.0) / 2.0, 0.0, 1.0)
        win_points = 10.0 * self._clip(oos_win, 0.0, 1.0)
        sharpe_points = 15.0 * self._clip(oos_sharpe / 3.0, 0.0, 1.0)

        stability_value = (
            float(stability)
            if stability is not None
            else float(out_of_sample.get("stability", 0.5))
        )
        stability_points = 15.0 * self._clip(stability_value, 0.0, 1.0)

        concentration = (
            float(trade_concentration)
            if trade_concentration is not None
            else float(out_of_sample.get("trade_concentration", 0.0))
        )
        concentration_points = 10.0 * (1.0 - self._clip(concentration, 0.0, 1.0))

        # Drawdown receives a full 10 points at 0% DD and zero by 35% DD.
        drawdown_points = 10.0 * (1.0 - self._clip(oos_dd / 0.35, 0.0, 1.0))

        is_return = float(in_sample.get("return", 0.0))
        if is_return > 0:
            generalization_ratio = self._clip(oos_return / is_return, -1.0, 1.0)
            generalization_points = 5.0 * max(0.0, generalization_ratio)
            overfit_gap = max(0.0, is_return - oos_return)
        else:
            generalization_points = 5.0 if oos_return >= is_return else 0.0
            overfit_gap = max(0.0, is_return - oos_return)

        raw = (
            return_points
            + pf_points
            + win_points
            + sharpe_points
            + stability_points
            + concentration_points
            + drawdown_points
            + generalization_points
        )

        warnings: list[str] = []
        if oos_return < 0:
            warnings.append("Out-of-sample return is negative")
        if oos_pf < 1.0:
            warnings.append("Out-of-sample profit factor is below 1.0")
        if oos_dd >= 0.20:
            warnings.append("Out-of-sample drawdown is high")
        if is_return > 0 and oos_return < is_return * 0.50:
            warnings.append("Large in-sample to out-of-sample degradation")
        if concentration >= 0.50:
            warnings.append("Returns are concentrated in a small share of trades")

        # Additional explicit overfitting penalty, up to 15 points.
        overfit_penalty = 15.0 * self._clip(overfit_gap / 0.50, 0.0, 1.0)
        final = self._clip(raw - overfit_penalty, 0.0, 100.0)

        return RobustnessScore(
            score=round(final, 2),
            components={
                "return": round(return_points, 2),
                "profit_factor": round(pf_points, 2),
                "win_rate": round(win_points, 2),
                "sharpe": round(sharpe_points, 2),
                "stability": round(stability_points, 2),
                "trade_diversification": round(concentration_points, 2),
                "drawdown": round(drawdown_points, 2),
                "generalization": round(generalization_points, 2),
                "overfit_penalty": round(overfit_penalty, 2),
            },
            warnings=tuple(warnings),
        )


DEFAULT_ROBUSTNESS_SCORER = RobustnessScorer()
