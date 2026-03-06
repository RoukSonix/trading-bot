"""News sentiment analysis and trading signal correlation.

Analyzes stored news articles for sentiment and correlates
with market conditions to generate trading signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import numpy as np
from loguru import logger


class SentimentLevel(str, Enum):
    """Sentiment classification."""

    VERY_BEARISH = "very_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    VERY_BULLISH = "very_bullish"


@dataclass
class SentimentResult:
    """Sentiment analysis result."""

    level: SentimentLevel
    score: float  # [-1, 1]: -1 = very bearish, 1 = very bullish
    confidence: float  # [0, 1]
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    summary: str
    top_headlines: list[str]


# Keyword-based sentiment lexicon for crypto
_BULLISH_KEYWORDS = {
    # Strong bullish
    "rally": 2.0, "surge": 2.0, "soar": 2.0, "breakout": 1.8, "all-time high": 2.0,
    "ath": 2.0, "moon": 1.5, "parabolic": 1.8, "adoption": 1.5, "institutional": 1.3,
    # Moderate bullish
    "bullish": 1.5, "gain": 1.0, "rise": 1.0, "jump": 1.2, "pump": 1.2,
    "recover": 1.0, "bounce": 1.0, "upgrade": 1.2, "partnership": 1.0,
    "accumulate": 1.0, "buy": 0.8, "approval": 1.5, "etf": 1.0,
    "growth": 1.0, "outperform": 1.2, "positive": 0.8, "up": 0.5,
}

_BEARISH_KEYWORDS = {
    # Strong bearish
    "crash": -2.0, "collapse": -2.0, "plunge": -2.0, "liquidat": -1.8,
    "ban": -2.0, "hack": -2.0, "exploit": -1.8, "rug pull": -2.0,
    # Moderate bearish
    "bearish": -1.5, "drop": -1.0, "fall": -1.0, "decline": -1.0, "dump": -1.2,
    "sell": -0.8, "fear": -1.0, "panic": -1.5, "regulation": -0.8,
    "warning": -1.0, "risk": -0.5, "concern": -0.8, "investigation": -1.0,
    "lawsuit": -1.2, "fraud": -1.8, "down": -0.5, "loss": -0.8,
}


class SentimentAnalyzer:
    """Analyze news sentiment for trading signals."""

    def __init__(
        self,
        bullish_keywords: dict[str, float] | None = None,
        bearish_keywords: dict[str, float] | None = None,
    ):
        """Initialize sentiment analyzer.

        Args:
            bullish_keywords: Custom bullish keyword weights.
            bearish_keywords: Custom bearish keyword weights.
        """
        self.bullish_kw = bullish_keywords or _BULLISH_KEYWORDS
        self.bearish_kw = bearish_keywords or _BEARISH_KEYWORDS

    def analyze_text(self, text: str) -> tuple[float, float]:
        """Analyze sentiment of a single text.

        Args:
            text: Text to analyze.

        Returns:
            Tuple of (score [-1, 1], confidence [0, 1]).
        """
        text_lower = text.lower()
        total_score = 0.0
        match_count = 0

        for keyword, weight in self.bullish_kw.items():
            count = text_lower.count(keyword)
            if count > 0:
                total_score += weight * count
                match_count += count

        for keyword, weight in self.bearish_kw.items():
            count = text_lower.count(keyword)
            if count > 0:
                total_score += weight * count  # weight is already negative
                match_count += count

        if match_count == 0:
            return 0.0, 0.0

        # Normalize score to [-1, 1]
        normalized = float(np.clip(total_score / (match_count * 1.5), -1.0, 1.0))

        # Confidence based on number of keyword matches
        confidence = float(np.clip(match_count / 5.0, 0.1, 1.0))

        return normalized, confidence

    def analyze_articles(
        self,
        articles: list[dict],
        max_age_hours: int = 24,
    ) -> SentimentResult:
        """Analyze sentiment across multiple news articles.

        Args:
            articles: List of article dicts from VectorStore (with text, metadata).
            max_age_hours: Only consider articles from the last N hours.

        Returns:
            SentimentResult with aggregate sentiment.
        """
        if not articles:
            return SentimentResult(
                level=SentimentLevel.NEUTRAL,
                score=0.0,
                confidence=0.0,
                article_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                summary="No articles available for analysis.",
                top_headlines=[],
            )

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        scores = []
        confidences = []
        positive = 0
        negative = 0
        neutral = 0
        headlines = []

        for article in articles:
            text = article.get("text", "")
            metadata = article.get("metadata", {})

            # Check age
            pub_str = metadata.get("published_at", "")
            if pub_str:
                try:
                    pub_dt = datetime.fromisoformat(pub_str)
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            score, confidence = self.analyze_text(text)
            scores.append(score)
            confidences.append(confidence)

            title = metadata.get("title", text[:80])
            headlines.append(title)

            if score > 0.1:
                positive += 1
            elif score < -0.1:
                negative += 1
            else:
                neutral += 1

        if not scores:
            return SentimentResult(
                level=SentimentLevel.NEUTRAL,
                score=0.0,
                confidence=0.0,
                article_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                summary="No recent articles within time window.",
                top_headlines=[],
            )

        # Weighted average score
        weights = np.array(confidences)
        if weights.sum() > 0:
            avg_score = float(np.average(scores, weights=weights))
        else:
            avg_score = float(np.mean(scores))

        avg_confidence = float(np.mean(confidences))

        # Classify sentiment level
        level = self._classify(avg_score)

        # Build summary
        total = positive + negative + neutral
        summary = (
            f"Analyzed {total} articles: "
            f"{positive} positive, {negative} negative, {neutral} neutral. "
            f"Overall sentiment: {level.value} (score: {avg_score:+.2f})."
        )

        return SentimentResult(
            level=level,
            score=avg_score,
            confidence=avg_confidence,
            article_count=total,
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            summary=summary,
            top_headlines=headlines[:5],
        )

    def _classify(self, score: float) -> SentimentLevel:
        """Classify a sentiment score into a level."""
        if score >= 0.5:
            return SentimentLevel.VERY_BULLISH
        elif score >= 0.15:
            return SentimentLevel.BULLISH
        elif score <= -0.5:
            return SentimentLevel.VERY_BEARISH
        elif score <= -0.15:
            return SentimentLevel.BEARISH
        return SentimentLevel.NEUTRAL

    def get_trading_signal(
        self,
        sentiment: SentimentResult,
        current_rsi: float = 50.0,
    ) -> dict:
        """Convert sentiment to a trading signal.

        Combines news sentiment with RSI for signal generation.

        Args:
            sentiment: Sentiment analysis result.
            current_rsi: Current RSI value for confluence.

        Returns:
            Dict with signal, strength, and reasoning.
        """
        signal = "NEUTRAL"
        strength = 0.0
        reasons = []

        # Sentiment-based signal
        if sentiment.score > 0.15 and sentiment.confidence > 0.3:
            signal = "BULLISH"
            strength = sentiment.score * sentiment.confidence
            reasons.append(f"Positive news sentiment ({sentiment.score:+.2f})")
        elif sentiment.score < -0.15 and sentiment.confidence > 0.3:
            signal = "BEARISH"
            strength = abs(sentiment.score) * sentiment.confidence
            reasons.append(f"Negative news sentiment ({sentiment.score:+.2f})")

        # RSI confluence
        if current_rsi < 30 and signal != "BEARISH":
            signal = "BULLISH"
            strength += 0.2
            reasons.append(f"RSI oversold ({current_rsi:.0f})")
        elif current_rsi > 70 and signal != "BULLISH":
            signal = "BEARISH"
            strength += 0.2
            reasons.append(f"RSI overbought ({current_rsi:.0f})")

        # Contrarian: extreme sentiment often reverses
        if sentiment.level == SentimentLevel.VERY_BEARISH:
            reasons.append("Extreme fear - potential contrarian buy")
        elif sentiment.level == SentimentLevel.VERY_BULLISH:
            reasons.append("Extreme greed - potential contrarian sell")

        strength = float(np.clip(strength, 0.0, 1.0))

        return {
            "signal": signal,
            "strength": strength,
            "sentiment_level": sentiment.level.value,
            "sentiment_score": sentiment.score,
            "confidence": sentiment.confidence,
            "article_count": sentiment.article_count,
            "reasoning": "; ".join(reasons) if reasons else "Insufficient data",
        }

    def to_ai_context(self, sentiment: SentimentResult) -> str:
        """Format sentiment for AI agent consumption.

        Returns a string suitable for including in AI prompts.
        """
        headlines_str = "\n".join(
            f"  - {h}" for h in sentiment.top_headlines
        ) or "  None available"

        return f"""## News Sentiment Analysis
- Overall: {sentiment.level.value} (score: {sentiment.score:+.2f})
- Confidence: {sentiment.confidence:.0%}
- Articles Analyzed: {sentiment.article_count}
- Breakdown: {sentiment.positive_count} positive, {sentiment.negative_count} negative, {sentiment.neutral_count} neutral

### Top Headlines
{headlines_str}

### Summary
{sentiment.summary}
"""


# Global instance
sentiment_analyzer = SentimentAnalyzer()
