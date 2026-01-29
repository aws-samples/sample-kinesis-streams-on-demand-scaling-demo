"""
Engagement-Sentiment Correlator.

This module analyzes the relationship between engagement scores and sentiment
classifications across social media posts. It identifies controversial content
(high engagement + negative sentiment) and underperforming content (low engagement
+ positive sentiment), and calculates correlation coefficients.
"""

import logging
from typing import List, Tuple
from statistics import mean, stdev
import math

import sys
import os

# Import from parent package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import EngagementInsight, SentimentResult

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EngagementSentimentCorrelator:
    """
    Analyzes engagement-sentiment correlation in social media posts.
    
    This correlator examines the relationship between how much engagement
    a post receives and its sentiment classification. It identifies:
    - Controversial content: High engagement with negative sentiment
    - Underperforming content: Low engagement with positive sentiment
    - Overall correlation between engagement and sentiment
    
    Attributes:
        high_engagement_threshold: Percentile threshold for high engagement (default: 75th)
        low_engagement_threshold: Percentile threshold for low engagement (default: 25th)
    """
    
    def __init__(
        self,
        high_engagement_threshold: float = 0.75,
        low_engagement_threshold: float = 0.25
    ):
        """
        Initialize the engagement-sentiment correlator.
        
        Args:
            high_engagement_threshold: Percentile for high engagement (0.0-1.0, default: 0.75)
            low_engagement_threshold: Percentile for low engagement (0.0-1.0, default: 0.25)
        """
        if not 0.0 <= high_engagement_threshold <= 1.0:
            raise ValueError("high_engagement_threshold must be between 0.0 and 1.0")
        if not 0.0 <= low_engagement_threshold <= 1.0:
            raise ValueError("low_engagement_threshold must be between 0.0 and 1.0")
        if low_engagement_threshold >= high_engagement_threshold:
            raise ValueError("low_engagement_threshold must be less than high_engagement_threshold")
        
        self.high_engagement_threshold = high_engagement_threshold
        self.low_engagement_threshold = low_engagement_threshold
        logger.info(
            f"Initialized EngagementSentimentCorrelator with "
            f"high_threshold={high_engagement_threshold}, low_threshold={low_engagement_threshold}"
        )
    
    def extract_insights(
        self,
        posts: List[any],  # List of SocialMediaPost objects
        sentiments: List[SentimentResult]
    ) -> EngagementInsight:
        """
        Extract engagement-sentiment correlation insights from analyzed posts.
        
        This method:
        1. Calculates average engagement per sentiment category
        2. Identifies posts with high engagement but negative sentiment (controversy)
        3. Identifies posts with low engagement but positive sentiment (underperforming)
        4. Calculates correlation coefficient between engagement and sentiment
        
        Args:
            posts: List of SocialMediaPost objects
            sentiments: List of SentimentResult objects (must match posts by ID)
            
        Returns:
            EngagementInsight object with correlation analysis
            
        Raises:
            ValueError: If posts and sentiments lists don't match
        """
        if len(posts) != len(sentiments):
            raise ValueError(
                f"Posts and sentiments count mismatch: {len(posts)} posts, "
                f"{len(sentiments)} sentiments"
            )
        
        if not posts:
            logger.info("No posts to process")
            # Return empty insight with zeros
            return EngagementInsight(
                avg_engagement_positive=0.0,
                avg_engagement_negative=0.0,
                avg_engagement_neutral=0.0,
                high_engagement_negative_posts=[],
                low_engagement_positive_posts=[],
                correlation_coefficient=0.0
            )
        
        # Create a mapping from post_id to sentiment result
        sentiment_map = {s.post_id: s for s in sentiments}
        
        # Collect engagement scores by sentiment category
        positive_engagements = []
        negative_engagements = []
        neutral_engagements = []
        
        # Collect all engagement scores and sentiment scores for correlation
        all_engagements = []
        all_sentiment_scores = []
        
        # Track post IDs with their engagement and sentiment
        post_data = []  # List of (post_id, engagement, sentiment, sentiment_score)
        
        # Process each post
        for post in posts:
            # Get sentiment for this post
            sentiment = sentiment_map.get(post.id)
            if not sentiment:
                logger.warning(f"No sentiment found for post {post.id}")
                continue
            
            engagement = post.engagement_score
            
            # Categorize by sentiment
            if sentiment.sentiment == 'positive':
                positive_engagements.append(engagement)
            elif sentiment.sentiment == 'negative':
                negative_engagements.append(engagement)
            elif sentiment.sentiment == 'neutral':
                neutral_engagements.append(engagement)
            
            # Collect for correlation calculation
            all_engagements.append(engagement)
            all_sentiment_scores.append(sentiment.sentiment_score)
            
            # Store post data for controversy/underperforming detection
            post_data.append((post.id, engagement, sentiment.sentiment, sentiment.sentiment_score))
        
        # Calculate average engagement per sentiment category
        avg_engagement_positive = mean(positive_engagements) if positive_engagements else 0.0
        avg_engagement_negative = mean(negative_engagements) if negative_engagements else 0.0
        avg_engagement_neutral = mean(neutral_engagements) if neutral_engagements else 0.0
        
        # Calculate engagement thresholds for controversy/underperforming detection
        high_engagement_cutoff, low_engagement_cutoff = self._calculate_thresholds(all_engagements)
        
        # Identify controversial posts (high engagement + negative sentiment)
        high_engagement_negative_posts = [
            post_id for post_id, engagement, sentiment, _ in post_data
            if engagement >= high_engagement_cutoff and sentiment == 'negative'
        ]
        
        # Identify underperforming posts (low engagement + positive sentiment)
        low_engagement_positive_posts = [
            post_id for post_id, engagement, sentiment, _ in post_data
            if engagement <= low_engagement_cutoff and sentiment == 'positive'
        ]
        
        # Calculate correlation coefficient
        correlation = self._calculate_correlation(all_engagements, all_sentiment_scores)
        
        # Create insight
        insight = EngagementInsight(
            avg_engagement_positive=avg_engagement_positive,
            avg_engagement_negative=avg_engagement_negative,
            avg_engagement_neutral=avg_engagement_neutral,
            high_engagement_negative_posts=high_engagement_negative_posts,
            low_engagement_positive_posts=low_engagement_positive_posts,
            correlation_coefficient=correlation
        )
        
        logger.info(
            f"Extracted engagement-sentiment insight: "
            f"correlation={correlation:.3f}, "
            f"controversial={len(high_engagement_negative_posts)}, "
            f"underperforming={len(low_engagement_positive_posts)}"
        )
        
        return insight
    
    def _calculate_thresholds(self, engagements: List[float]) -> Tuple[float, float]:
        """
        Calculate engagement thresholds based on percentiles.
        
        Args:
            engagements: List of engagement scores
            
        Returns:
            Tuple of (high_threshold, low_threshold)
        """
        if not engagements:
            return (0.0, 0.0)
        
        # Sort engagements to calculate percentiles
        sorted_engagements = sorted(engagements)
        n = len(sorted_engagements)
        
        # Calculate percentile indices
        high_idx = int(n * self.high_engagement_threshold)
        low_idx = int(n * self.low_engagement_threshold)
        
        # Ensure indices are within bounds
        high_idx = min(high_idx, n - 1)
        low_idx = max(low_idx, 0)
        
        high_threshold = sorted_engagements[high_idx]
        low_threshold = sorted_engagements[low_idx]
        
        return (high_threshold, low_threshold)
    
    def _calculate_correlation(
        self,
        engagements: List[float],
        sentiment_scores: List[float]
    ) -> float:
        """
        Calculate Pearson correlation coefficient between engagement and sentiment.
        
        The correlation coefficient measures the linear relationship between
        engagement scores and sentiment scores:
        - 1.0: Perfect positive correlation (higher engagement = more positive)
        - 0.0: No correlation
        - -1.0: Perfect negative correlation (higher engagement = more negative)
        
        Args:
            engagements: List of engagement scores
            sentiment_scores: List of sentiment scores (-1.0 to 1.0)
            
        Returns:
            Correlation coefficient between -1.0 and 1.0
        """
        if not engagements or not sentiment_scores:
            return 0.0
        
        if len(engagements) != len(sentiment_scores):
            logger.warning(
                f"Engagement and sentiment score count mismatch: "
                f"{len(engagements)} vs {len(sentiment_scores)}"
            )
            return 0.0
        
        # Need at least 2 data points for correlation
        if len(engagements) < 2:
            return 0.0
        
        # Calculate means
        mean_engagement = mean(engagements)
        mean_sentiment = mean(sentiment_scores)
        
        # Calculate standard deviations
        try:
            std_engagement = stdev(engagements)
            std_sentiment = stdev(sentiment_scores)
        except Exception as e:
            logger.warning(f"Failed to calculate standard deviation: {e}")
            return 0.0
        
        # If either standard deviation is zero, correlation is undefined
        if std_engagement == 0 or std_sentiment == 0:
            return 0.0
        
        # Calculate covariance
        covariance = sum(
            (e - mean_engagement) * (s - mean_sentiment)
            for e, s in zip(engagements, sentiment_scores)
        ) / len(engagements)
        
        # Calculate correlation coefficient
        correlation = covariance / (std_engagement * std_sentiment)
        
        # Clamp to valid range (handle floating point errors)
        correlation = max(-1.0, min(1.0, correlation))
        
        return correlation
