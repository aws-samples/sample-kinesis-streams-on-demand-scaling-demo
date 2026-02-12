"""
Geographic Sentiment Analyzer.

This module analyzes sentiment patterns by geographic location, grouping posts
by city and country, calculating average sentiment per region, and identifying
dominant sentiment classifications.
"""

import logging
from typing import List, Dict
from collections import defaultdict

import sys
import os

# Import from parent package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import GeographicInsight, SentimentResult

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GeographicSentimentAnalyzer:
    """
    Analyzes sentiment patterns by geographic location.
    
    This analyzer groups posts by city and country, calculates average sentiment
    per region, identifies the dominant sentiment classification, and handles
    posts with missing location data by categorizing them as "location-unknown".
    
    The analyzer processes posts and their corresponding sentiment results to
    generate GeographicInsight objects for each unique geographic region.
    """
    
    # Constants for location-unknown categorization
    LOCATION_UNKNOWN = "location-unknown"
    
    def __init__(self):
        """Initialize the geographic sentiment analyzer."""
        logger.info("Initialized GeographicSentimentAnalyzer")
    
    def extract_insights(
        self,
        posts: List[any],  # List of SocialMediaPost objects
        sentiments: List[SentimentResult]
    ) -> List[GeographicInsight]:
        """
        Extract geographic sentiment insights from analyzed posts.
        
        This method:
        1. Groups posts by city and country (or "location-unknown" if missing)
        2. Calculates average sentiment per geographic region
        3. Identifies dominant sentiment per region
        4. Returns GeographicInsight objects for each region
        
        Args:
            posts: List of SocialMediaPost objects
            sentiments: List of SentimentResult objects (must match posts by ID)
            
        Returns:
            List of GeographicInsight objects, one per geographic region
            
        Note:
            Handles mismatches gracefully by only processing posts with sentiment results
        """
        if len(posts) != len(sentiments):
            logger.warning(
                f"Posts and sentiments count mismatch: {len(posts)} posts, "
                f"{len(sentiments)} sentiments. Will process available data."
            )
        
        if not posts:
            logger.info("No posts to process")
            return []
        
        # Create a mapping from post_id to sentiment result
        sentiment_map = {s.post_id: s for s in sentiments}
        
        # Track geographic data: (city, country) -> {sentiment_scores, sentiment_counts}
        geographic_data: Dict[tuple, Dict] = defaultdict(lambda: {
            'sentiment_scores': [],
            'positive_count': 0,
            'negative_count': 0,
            'neutral_count': 0,
        })
        
        # Process each post
        for post in posts:
            # Get sentiment for this post
            sentiment = sentiment_map.get(post.id)
            if not sentiment:
                logger.warning(f"No sentiment found for post {post.id}")
                continue
            
            # Extract location data
            city, country = self._extract_location(post)
            
            # Create region key
            region_key = (city, country)
            
            # Update data for this region
            data = geographic_data[region_key]
            data['sentiment_scores'].append(sentiment.sentiment_score)
            
            # Count sentiment classifications
            if sentiment.sentiment == 'positive':
                data['positive_count'] += 1
            elif sentiment.sentiment == 'negative':
                data['negative_count'] += 1
            elif sentiment.sentiment == 'neutral':
                data['neutral_count'] += 1
        
        # Generate GeographicInsight objects
        insights = []
        for (city, country), data in geographic_data.items():
            # Calculate average sentiment
            avg_sentiment = (
                sum(data['sentiment_scores']) / len(data['sentiment_scores'])
                if data['sentiment_scores'] else 0.0
            )
            
            # Determine dominant sentiment
            dominant_sentiment = self._determine_dominant_sentiment(
                data['positive_count'],
                data['negative_count'],
                data['neutral_count']
            )
            
            # Create insight
            insight = GeographicInsight(
                city=city,
                country=country,
                average_sentiment=avg_sentiment,
                post_count=len(data['sentiment_scores']),
                dominant_sentiment=dominant_sentiment
            )
            insights.append(insight)
        
        logger.info(f"Extracted insights for {len(insights)} geographic regions")
        return insights
    
    def _extract_location(self, post: any) -> tuple:
        """
        Extract city and country from a social media post.
        
        If the post has location data, returns the city and country.
        If location data is missing, returns ("location-unknown", "location-unknown").
        
        Args:
            post: SocialMediaPost object
            
        Returns:
            Tuple of (city, country) strings
        """
        if post.location is None:
            return (self.LOCATION_UNKNOWN, self.LOCATION_UNKNOWN)
        
        city = post.location.city if post.location.city else self.LOCATION_UNKNOWN
        country = post.location.country if post.location.country else self.LOCATION_UNKNOWN
        
        return (city, country)
    
    def _determine_dominant_sentiment(
        self,
        positive_count: int,
        negative_count: int,
        neutral_count: int
    ) -> str:
        """
        Determine the dominant sentiment classification for a region.
        
        The dominant sentiment is the classification with the highest count.
        In case of a tie, the order of precedence is: positive > neutral > negative.
        
        Args:
            positive_count: Number of positive posts
            negative_count: Number of negative posts
            neutral_count: Number of neutral posts
            
        Returns:
            String indicating dominant sentiment: "positive", "negative", or "neutral"
        """
        # Find the maximum count
        max_count = max(positive_count, negative_count, neutral_count)
        
        # Return the sentiment with the highest count
        # In case of tie, prefer positive > neutral > negative
        if positive_count == max_count:
            return 'positive'
        elif neutral_count == max_count:
            return 'neutral'
        else:
            return 'negative'
