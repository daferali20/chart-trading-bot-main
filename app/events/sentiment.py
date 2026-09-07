from __future__ import annotations


class FinancialHeadlineSentiment:
    """Small dependency-free financial headline sentiment model.

    This is intentionally conservative and replaceable. It provides a usable
    first-pass score for SerpAPI headlines without adding a heavy NLP runtime.
    A future FinBERT/LLM implementation can expose the same ``score`` method.
    """

    POSITIVE_PHRASES: tuple[tuple[str, float], ...] = (
        ("beats estimates", 1.20),
        ("beats expectations", 1.20),
        ("earnings beat", 1.10),
        ("revenue beat", 1.00),
        ("raises guidance", 1.20),
        ("raises outlook", 1.10),
        ("record revenue", 0.90),
        ("record profit", 0.90),
        ("strong demand", 0.75),
        ("wins contract", 0.85),
        ("contract award", 0.85),
        ("fda approval", 1.20),
        ("price target raised", 0.70),
        ("analyst upgrade", 0.75),
        ("share buyback", 0.65),
        ("strategic partnership", 0.55),
    )

    NEGATIVE_PHRASES: tuple[tuple[str, float], ...] = (
        ("misses estimates", -1.20),
        ("misses expectations", -1.20),
        ("earnings miss", -1.10),
        ("revenue miss", -1.00),
        ("cuts guidance", -1.20),
        ("cuts outlook", -1.10),
        ("profit warning", -1.10),
        ("secondary offering", -0.95),
        ("dilutive offering", -1.10),
        ("share offering", -0.80),
        ("sec investigation", -0.95),
        ("regulatory probe", -0.90),
        ("analyst downgrade", -0.75),
        ("price target cut", -0.70),
        ("ceo resigns", -0.65),
        ("bankruptcy", -1.30),
        ("default", -1.10),
        ("recall", -0.70),
    )

    POSITIVE_WORDS = {
        "beat", "beats", "surge", "surges", "jump", "jumps", "growth",
        "strong", "upgrade", "upgraded", "approval", "approved", "record",
        "profit", "profitable", "award", "wins", "bullish", "rebound",
    }
    NEGATIVE_WORDS = {
        "miss", "misses", "plunge", "plunges", "drop", "drops", "weak",
        "downgrade", "downgraded", "loss", "losses", "probe", "lawsuit",
        "offering", "dilution", "recall", "warning", "bearish", "fraud",
    }

    @staticmethod
    def _clip(value: float) -> float:
        return max(-1.0, min(1.0, float(value)))

    def score(self, headline: str, body: str = "") -> float:
        text = f"{headline} {body}".lower()
        raw = 0.0

        matched_phrases: set[str] = set()
        for phrase, weight in self.POSITIVE_PHRASES + self.NEGATIVE_PHRASES:
            if phrase in text:
                raw += weight
                matched_phrases.add(phrase)

        # Remove matched phrases before token scoring to reduce double-counting.
        residual = text
        for phrase in matched_phrases:
            residual = residual.replace(phrase, " ")

        tokens = {
            token.strip(".,:;!?()[]{}'\"")
            for token in residual.split()
        }
        raw += 0.18 * len(tokens & self.POSITIVE_WORDS)
        raw -= 0.18 * len(tokens & self.NEGATIVE_WORDS)

        # Conservative normalization: one generic positive word should not
        # generate a high-confidence directional forecast.
        return round(self._clip(raw / 1.8), 4)


DEFAULT_FINANCIAL_SENTIMENT = FinancialHeadlineSentiment()
