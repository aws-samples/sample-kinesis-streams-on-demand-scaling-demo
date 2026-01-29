"""
Trending Topics Extractor.

This module extracts trending topic insights from analyzed social media posts.
It identifies hashtags, counts their frequency, calculates sentiment per hashtag,
and identifies co-occurring hashtags to understand topic relationships.
"""

import logging
from typing import List, Dict, Set
from collections import defaultdict, Counter

import sys
import os

# Import from parent package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import TopicInsight, SentimentResult

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TrendingTopicsExtractor:
    """
    Extracts trending topic insights from social media posts.
    
    This extractor identifies hashtags in posts, counts their frequency,
    calculates average sentiment per hashtag, and identifies co-occurring
    hashtags to understand topic relationships.
    
    A hashtag is considered "trending" if it appears in 10 or more posts
    within the batch.
    
    Attributes:
        trending_threshold: Minimum number of posts for a hashtag to be trending
    """
    
    def __init__(self, trending_threshold: int = 10):
        """
        Initialize the trending topics extractor.
        
        Args:
            trending_threshold: Minimum posts for trending classification (default: 10)
        """
        self.trending_threshold = trending_threshold
        logger.info(f"Initialized TrendingTopicsExtractor with threshold={trending_threshold}")
    
    def extract_insights(
        self,
        posts: List[any],  # List of SocialMediaPost objects
        sentiments: List[SentimentResult]
    ) -> List[TopicInsight]:
        """
        Extract trending topic insights from analyzed posts.
        
        This method:
        1. Counts hashtag frequencies across the batch
        2. Identifies trending hashtags (10+ posts threshold)
        3. Calculates average sentiment per hashtag
        4. Identifies co-occurring hashtags
        
        Args:
            posts: List of SocialMediaPost objects
            sentiments: List of SentimentResult objects (must match posts by ID)
            
        Returns:
            List of TopicInsight objects, one per identified hashtag
            
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
            return []
        
        # Create a mapping from post_id to sentiment result
        sentiment_map = {s.post_id: s for s in sentiments}
        
        # Track hashtag data: hashtag -> {sentiment_scores, post_ids}
        hashtag_data: Dict[str, Dict] = defaultdict(lambda: {
            'sentiment_scores': [],
            'post_ids': set(),
        })
        
        # Track co-occurring hashtags: hashtag -> Counter of other hashtags
        co_occurrence_map: Dict[str, Counter] = defaultdict(Counter)
        
        # Process each post
        for post in posts:
            # Get sentiment for this post
            sentiment = sentiment_map.get(post.id)
            if not sentiment:
                logger.warning(f"No sentiment found for post {post.id}")
                continue
            
            # Get hashtags from this post (clean them)
            post_hashtags = self._clean_hashtags(post.hashtags)
            
            if not post_hashtags:
                continue
            
            # Update data for each hashtag in this post
            for hashtag in post_hashtags:
                data = hashtag_data[hashtag]
                data['sentiment_scores'].append(sentiment.sentiment_score)
                data['post_ids'].add(post.id)
            
            # Track co-occurring hashtags
            # For each hashtag, count all other hashtags in the same post
            for hashtag in post_hashtags:
                other_hashtags = post_hashtags - {hashtag}
                co_occurrence_map[hashtag].update(other_hashtags)
        
        # Generate TopicInsight objects
        insights = []
        for hashtag, data in hashtag_data.items():
            post_count = len(data['post_ids'])
            
            # Calculate average sentiment
            avg_sentiment = (
                sum(data['sentiment_scores']) / len(data['sentiment_scores'])
                if data['sentiment_scores'] else 0.0
            )
            
            # Determine if trending (10+ posts)
            is_trending = post_count >= self.trending_threshold
            
            # Get top co-occurring hashtags (top 5 by frequency)
            co_occurring = []
            if hashtag in co_occurrence_map:
                # Get top 5 most common co-occurring hashtags
                top_co_occurring = co_occurrence_map[hashtag].most_common(5)
                co_occurring = [tag for tag, count in top_co_occurring]
            
            # Create insight
            insight = TopicInsight(
                hashtag=hashtag,
                post_count=post_count,
                average_sentiment=avg_sentiment,
                is_trending=is_trending,
                co_occurring_hashtags=co_occurring
            )
            insights.append(insight)
        
        logger.info(
            f"Extracted insights for {len(insights)} hashtags "
            f"({sum(1 for i in insights if i.is_trending)} trending)"
        )
        return insights
    
    def _clean_hashtags(self, hashtags: List[str]) -> Set[str]:
        """
        Clean and normalize hashtags from a post.
        
        Removes # symbol if present and converts to lowercase for consistency.
        
        Args:
            hashtags: List of hashtags from a post
            
        Returns:
            Set of cleaned hashtag strings (without # symbol, lowercase)
        """
        if not hashtags:
            return set()
        
        cleaned = set()
        for hashtag in hashtags:
            # Remove # symbol if present and convert to lowercase
            clean_tag = hashtag.lstrip('#').lower()
            
            # Only include non-empty hashtags
            if clean_tag:
                cleaned.add(clean_tag)
        
        return cleaned
