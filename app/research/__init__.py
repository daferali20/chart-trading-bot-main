"""Research-only subsystem.

This package must remain broker/execution agnostic. Research code may read
strategy definitions and historical data, but it must not import or call the
IBKR execution stack.
"""

from app.research.experiments.runner import ExperimentRunner
from app.research.registry.strategy_registry import StrategyRegistry

__all__ = ["ExperimentRunner", "StrategyRegistry"]
