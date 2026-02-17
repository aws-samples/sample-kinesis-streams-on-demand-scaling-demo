"""
Insight extractors for sentiment analysis consumer.

This package contains extractors that process sentiment results to generate
various types of insights (product sentiment, trending topics, engagement
correlation, geographic patterns, and viral events).
"""

from .product_sentiment import ProductSentimentExtractor
from .trending_topics import TrendingTopicsExtractor
from .engagement_correlator import EngagementSentimentCorrelator
from .geographic_analyzer import GeographicSentimentAnalyzer

__all__ = [
    'ProductSentimentExtractor',
    'TrendingTopicsExtractor',
    'EngagementSentimentCorrelator',
    'GeographicSentimentAnalyzer',
]
