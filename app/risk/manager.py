from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    risk_amount: float = 0.0
    risk_per_share: float = 0.0
    reward_per_share: float = 0.0
    reward_risk: float = 0.0


def validate_trade(
    entry: float,
    stop: float,
    target: float,
    quantity: int,
    account_value: float,
    risk_fraction: float,
) -> RiskDecision:
    if entry <= 0 or stop <= 0 or target <= 0:
        return RiskDecision(False, "Entry/stop/target must be positive")
    if quantity <= 0:
        return RiskDecision(False, "Quantity must be positive")
    if account_value <= 0:
        return RiskDecision(False, "Account value must be positive")
    if not 0 < risk_fraction <= 1:
        return RiskDecision(False, "risk_fraction must be between 0 and 1")
    if stop >= entry:
        return RiskDecision(False, "For BUY, stop must be below entry")
    if target <= entry:
        return RiskDecision(False, "For BUY, target must be above entry")

    risk_per_share = entry - stop
    reward_per_share = target - entry
    risk_amount = risk_per_share * quantity
    allowed_risk = account_value * risk_fraction
    rr = reward_per_share / risk_per_share if risk_per_share else 0.0

    if risk_amount > allowed_risk:
        return RiskDecision(
            False,
            f"Risk too high: ${risk_amount:.2f} > ${allowed_risk:.2f}",
            risk_amount,
            risk_per_share,
            reward_per_share,
            rr,
        )

    return RiskDecision(True, "OK", risk_amount, risk_per_share, reward_per_share, rr)
