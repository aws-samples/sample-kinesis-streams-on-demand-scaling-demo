"""
Data models for sentiment analysis consumer.

This module defines the data structures used throughout the sentiment analysis
pipeline, including sentiment results, various insight types, and processing metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SentimentResult:
    """
    Result from Bedrock sentiment analysis for a single post.
    
    Attributes:
        post_id: Unique identifier of the analyzed post
        sentiment: Classification (positive, negative, or neutral)
        sentiment_score: Intensity score from -1.0 (very negative) to 1.0 (very positive)
        confidence: Confidence level from 0.0 to 1.0
        timestamp: When the analysis was performed
        analysis_duration_ms: Time taken for Bedrock API call in milliseconds
    """
    post_id: str
    sentiment: str  # "positive", "negative", "neutral"
    sentiment_score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    analysis_duration_ms: float = 0.0

    def __post_init__(self):
        """Validate sentiment result data."""
        valid_sentiments = {"positive", "negative", "neutral"}
        if self.sentiment not in valid_sentiments:
            raise ValueError(
                f"Invalid sentiment '{self.sentiment}'. Must be one of: {valid_sentiments}"
            )
        if not -1.0 <= self.sentiment_score <= 1.0:
            raise ValueError(
                f"Invalid sentiment_score {self.sentiment_score}. Must be between -1.0 and 1.0"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Invalid confidence {self.confidence}. Must be between 0.0 and 1.0"
            )
        if self.analysis_duration_ms < 0:
            raise ValueError("Analysis duration cannot be negative")


@dataclass
class ProductInsight:
    """
    Product-specific sentiment aggregation.
    
    Tracks sentiment metrics for mentions of a specific product across
    multiple social media posts.
    
    Attributes:
        product_name: Name of the product being tracked
        average_sentiment: Mean sentiment score across all mentions
        post_count: Total number of posts mentioning this product
        positive_count: Number of posts with positive sentiment
        negative_count: Number of posts with negative sentiment
        neutral_count: Number of posts with neutral sentiment
        average_engagement: Mean engagement score across all mentions
        timestamp: When this insight was generated
    """
    product_name: str
    average_sentiment: float
    post_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    average_engagement: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate product insight data."""
        if not self.product_name:
            raise ValueError("Product name cannot be empty")
        if not -1.0 <= self.average_sentiment <= 1.0:
            raise ValueError(
                f"Invalid average_sentiment {self.average_sentiment}. Must be between -1.0 and 1.0"
            )
        if self.post_count < 0:
            raise ValueError("Post count cannot be negative")
        if self.positive_count < 0:
            raise ValueError("Positive count cannot be negative")
        if self.negative_count < 0:
            raise ValueError("Negative count cannot be negative")
        if self.neutral_count < 0:
            raise ValueError("Neutral count cannot be negative")
        if self.average_engagement < 0:
            raise ValueError("Average engagement cannot be negative")
        # Validate that counts sum to total
        if self.positive_count + self.negative_count + self.neutral_count != self.post_count:
            raise ValueError(
                "Sum of positive, negative, and neutral counts must equal post_count"
            )


@dataclass
class TopicInsight:
    """
    Trending topic analysis for hashtags.
    
    Tracks frequency and sentiment for hashtags appearing in social media posts.
    
    Attributes:
        hashtag: The hashtag being tracked (without # symbol)
        post_count: Number of posts containing this hashtag
        average_sentiment: Mean sentiment score for posts with this hashtag
        is_trending: True if hashtag appears in 10+ posts
        co_occurring_hashtags: List of hashtags that frequently appear with this one
        timestamp: When this insight was generated
    """
    hashtag: str
    post_count: int
    average_sentiment: float
    is_trending: bool
    co_occurring_hashtags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate topic insight data."""
        if not self.hashtag:
            raise ValueError("Hashtag cannot be empty")
        if self.post_count < 0:
            raise ValueError("Post count cannot be negative")
        if not -1.0 <= self.average_sentiment <= 1.0:
            raise ValueError(
                f"Invalid average_sentiment {self.average_sentiment}. Must be between -1.0 and 1.0"
            )


@dataclass
class EngagementInsight:
    """
    Engagement-sentiment correlation analysis.
    
    Analyzes the relationship between engagement scores and sentiment
    classifications across a batch of posts.
    
    Attributes:
        avg_engagement_positive: Mean engagement for positive posts
        avg_engagement_negative: Mean engagement for negative posts
        avg_engagement_neutral: Mean engagement for neutral posts
        high_engagement_negative_posts: Post IDs with high engagement + negative sentiment
        low_engagement_positive_posts: Post IDs with low engagement + positive sentiment
        correlation_coefficient: Statistical correlation between engagement and sentiment
        timestamp: When this insight was generated
    """
    avg_engagement_positive: float
    avg_engagement_negative: float
    avg_engagement_neutral: float
    high_engagement_negative_posts: List[str] = field(default_factory=list)
    low_engagement_positive_posts: List[str] = field(default_factory=list)
    correlation_coefficient: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate engagement insight data."""
        if self.avg_engagement_positive < 0:
            raise ValueError("Average engagement for positive posts cannot be negative")
        if self.avg_engagement_negative < 0:
            raise ValueError("Average engagement for negative posts cannot be negative")
        if self.avg_engagement_neutral < 0:
            raise ValueError("Average engagement for neutral posts cannot be negative")
        if not -1.0 <= self.correlation_coefficient <= 1.0:
            raise ValueError(
                f"Invalid correlation_coefficient {self.correlation_coefficient}. "
                "Must be between -1.0 and 1.0"
            )


@dataclass
class GeographicInsight:
    """
    Location-based sentiment patterns.
    
    Tracks sentiment metrics for posts from specific geographic regions.
    
    Attributes:
        city: City name (or "location-unknown" if not available)
        country: Country name (or "location-unknown" if not available)
        average_sentiment: Mean sentiment score for posts from this region
        post_count: Number of posts from this region
        dominant_sentiment: Most common sentiment classification in this region
        timestamp: When this insight was generated
    """
    city: str
    country: str
    average_sentiment: float
    post_count: int
    dominant_sentiment: str  # "positive", "negative", "neutral"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate geographic insight data."""
        if not self.city:
            raise ValueError("City cannot be empty")
        if not self.country:
            raise ValueError("Country cannot be empty")
        if not -1.0 <= self.average_sentiment <= 1.0:
            raise ValueError(
                f"Invalid average_sentiment {self.average_sentiment}. Must be between -1.0 and 1.0"
            )
        if self.post_count < 0:
            raise ValueError("Post count cannot be negative")
        valid_sentiments = {"positive", "negative", "neutral"}
        if self.dominant_sentiment not in valid_sentiments:
            raise ValueError(
                f"Invalid dominant_sentiment '{self.dominant_sentiment}'. "
                f"Must be one of: {valid_sentiments}"
            )


@dataclass
class ViralEventInsight:
    """
    Viral event detection and sentiment shift analysis.
    
    Identifies periods of high-volume posting and tracks sentiment changes
    during these events.
    
    Attributes:
        event_id: Unique identifier for this viral event
        post_count: Number of posts during the event window
        average_sentiment: Mean sentiment during the event
        baseline_sentiment: Mean sentiment before the event (for comparison)
        sentiment_shift: Change in sentiment (average_sentiment - baseline_sentiment)
        dominant_sentiment: Most common sentiment during the event
        top_products: Products most mentioned during the event
        top_hashtags: Hashtags most used during the event
        timestamp: When this event was detected
    """
    event_id: str
    post_count: int
    average_sentiment: float
    baseline_sentiment: float
    sentiment_shift: float
    dominant_sentiment: str  # "positive", "negative", "neutral"
    top_products: List[str] = field(default_factory=list)
    top_hashtags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate viral event insight data."""
        if not self.event_id:
            raise ValueError("Event ID cannot be empty")
        if self.post_count < 0:
            raise ValueError("Post count cannot be negative")
        if not -1.0 <= self.average_sentiment <= 1.0:
            raise ValueError(
                f"Invalid average_sentiment {self.average_sentiment}. Must be between -1.0 and 1.0"
            )
        if not -1.0 <= self.baseline_sentiment <= 1.0:
            raise ValueError(
                f"Invalid baseline_sentiment {self.baseline_sentiment}. Must be between -1.0 and 1.0"
            )
        if not -2.0 <= self.sentiment_shift <= 2.0:
            raise ValueError(
                f"Invalid sentiment_shift {self.sentiment_shift}. Must be between -2.0 and 2.0"
            )
        valid_sentiments = {"positive", "negative", "neutral"}
        if self.dominant_sentiment not in valid_sentiments:
            raise ValueError(
                f"Invalid dominant_sentiment '{self.dominant_sentiment}'. "
                f"Must be one of: {valid_sentiments}"
            )


@dataclass
class BatchProcessingMetrics:
    """
    Metrics for Lambda execution and batch processing.
    
    Tracks performance and cost metrics for a single Lambda invocation.
    
    Attributes:
        batch_id: Unique identifier for this processing batch
        total_records: Total number of records in the batch
        successful_records: Number of successfully processed records
        failed_records: Number of records that failed processing
        bedrock_api_calls: Number of Bedrock API calls made
        bedrock_total_latency_ms: Total time spent in Bedrock API calls
        total_processing_time_ms: Total time for entire batch processing
        timestamp: When this batch was processed
    """
    batch_id: str
    total_records: int
    successful_records: int
    failed_records: int
    bedrock_api_calls: int
    bedrock_total_latency_ms: float
    total_processing_time_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate batch processing metrics."""
        if not self.batch_id:
            raise ValueError("Batch ID cannot be empty")
        if self.total_records < 0:
            raise ValueError("Total records cannot be negative")
        if self.successful_records < 0:
            raise ValueError("Successful records cannot be negative")
        if self.failed_records < 0:
            raise ValueError("Failed records cannot be negative")
        if self.bedrock_api_calls < 0:
            raise ValueError("Bedrock API calls cannot be negative")
        if self.bedrock_total_latency_ms < 0:
            raise ValueError("Bedrock total latency cannot be negative")
        if self.total_processing_time_ms < 0:
            raise ValueError("Total processing time cannot be negative")
        # Validate that successful + failed = total
        if self.successful_records + self.failed_records != self.total_records:
            raise ValueError(
                "Sum of successful and failed records must equal total_records"
            )
