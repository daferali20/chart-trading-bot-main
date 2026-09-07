"""Research scoring models with explicit robustness/overfitting penalties."""

from app.research.scoring.alpha_breadth import (
    DEFAULT_ALPHA_BREADTH_EVALUATOR,
    AlphaBreadthEvidence,
    AlphaBreadthEvaluator,
    SymbolAlphaEvidence,
)
from app.research.scoring.event_aware import (
    DEFAULT_EVENT_AWARE_BACKTEST_ANALYZER,
    EventAwareBacktestAnalyzer,
    EventAwarePerformanceReport,
    EventAwareTrade,
)
from app.research.scoring.normal_market import (
    DEFAULT_NORMAL_MARKET_ANALYZER,
    ClassifiedTradeReturn,
    NormalMarketPerformance,
    NormalMarketPerformanceAnalyzer,
)
from app.research.scoring.robustness import (
    DEFAULT_ROBUSTNESS_SCORER,
    RobustnessScore,
    RobustnessScorer,
)

__all__ = [
    "RobustnessScore",
    "RobustnessScorer",
    "DEFAULT_ROBUSTNESS_SCORER",
    "ClassifiedTradeReturn",
    "NormalMarketPerformance",
    "NormalMarketPerformanceAnalyzer",
    "DEFAULT_NORMAL_MARKET_ANALYZER",
    "EventAwareTrade",
    "EventAwarePerformanceReport",
    "EventAwareBacktestAnalyzer",
    "DEFAULT_EVENT_AWARE_BACKTEST_ANALYZER",
    "SymbolAlphaEvidence",
    "AlphaBreadthEvidence",
    "AlphaBreadthEvaluator",
    "DEFAULT_ALPHA_BREADTH_EVALUATOR",
]
