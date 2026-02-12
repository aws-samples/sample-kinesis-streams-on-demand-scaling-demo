"""
Product Sentiment Extractor.

This module extracts product-specific sentiment insights from analyzed social media posts.
It identifies product mentions in content and hashtags, aggregates sentiment scores,
and calculates engagement metrics per product.
"""

import re
import logging
from typing import List, Dict, Set
from collections import defaultdict

import sys
import os

# Import from parent package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ProductInsight, SentimentResult

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProductSentimentExtractor:
    """
    Extracts product-specific sentiment insights from social media posts.
    
    This extractor identifies product mentions in post content and hashtags,
    aggregates sentiment scores per product, and calculates engagement metrics.
    
    Product names are extracted using regex patterns that match:
    - Capitalized words (e.g., "TechProduct", "iPhone")
    - Hashtags containing product names (e.g., "#TechProduct")
    - Common product naming patterns
    
    Attributes:
        product_patterns: List of regex patterns for product name extraction
    """
    
    # Common product name patterns
    # Matches capitalized words that could be product names
    PRODUCT_PATTERNS = [
        r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b',  # CamelCase: TechProduct, Apple
        r'\b([a-z]+[A-Z][a-zA-Z]*)\b',  # lowercase start CamelCase: iPhone, eBay
        r'\b([A-Z]{2,})\b',  # All caps: AWS, IBM, API
        r'\b([A-Z][a-z]+\d+)\b',  # Product with numbers: Galaxy23
        r'\b([a-z]+[A-Z][a-z]*\d+)\b',  # lowercase CamelCase with numbers: iPhone15
    ]
    
    # Common words to exclude (not product names)
    EXCLUDE_WORDS = {
        'I', 'A', 'The', 'This', 'That', 'These', 'Those',
        'My', 'Your', 'His', 'Her', 'Its', 'Our', 'Their',
        'Am', 'Is', 'Are', 'Was', 'Were', 'Be', 'Been', 'Being',
        'Have', 'Has', 'Had', 'Do', 'Does', 'Did',
        'Will', 'Would', 'Should', 'Could', 'May', 'Might', 'Must',
        'Can', 'Cannot', 'Could', 'Should', 'Would',
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
        'Today', 'Tomorrow', 'Yesterday', 'Week', 'Month', 'Year',
        'New', 'Old', 'Good', 'Bad', 'Great', 'Best', 'Worst',
        'First', 'Last', 'Next', 'Previous',
        'All', 'Some', 'Many', 'Few', 'Most', 'More', 'Less',
        'Very', 'Really', 'Quite', 'Too', 'So', 'Such',
        'Just', 'Only', 'Even', 'Also', 'Still', 'Yet',
        'Now', 'Then', 'Here', 'There', 'Where', 'When', 'Why', 'How',
        'What', 'Which', 'Who', 'Whom', 'Whose',
        'And', 'Or', 'But', 'If', 'Because', 'While', 'Although',
        'For', 'To', 'From', 'With', 'Without', 'About', 'Through',
        'Over', 'Under', 'Between', 'Among', 'During', 'Before', 'After',
        'It', 'Excited', 'Amazing', 'Terrible', 'Disappointed', 'Love', 'Got',
        'Try', 'Get', 'Make', 'Take', 'Give', 'Come', 'Go', 'See', 'Know',
    }
    
    def __init__(self):
        """Initialize the product sentiment extractor."""
        self.product_patterns = [re.compile(pattern) for pattern in self.PRODUCT_PATTERNS]
        logger.info("Initialized ProductSentimentExtractor")
    
    def extract_insights(
        self,
        posts: List[any],  # List of SocialMediaPost objects
        sentiments: List[SentimentResult]
    ) -> List[ProductInsight]:
        """
        Extract product-specific sentiment insights from analyzed posts.
        
        This method:
        1. Extracts product names from post content and hashtags
        2. Aggregates sentiment scores per product
        3. Calculates engagement metrics per product
        4. Returns ProductInsight objects for each identified product
        
        Args:
            posts: List of SocialMediaPost objects
            sentiments: List of SentimentResult objects (must match posts by ID)
            
        Returns:
            List of ProductInsight objects, one per identified product
            
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
        
        # Track product data: product_name -> {sentiments, engagements, sentiment_counts}
        product_data: Dict[str, Dict] = defaultdict(lambda: {
            'sentiment_scores': [],
            'engagement_scores': [],
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
            
            # Extract product names from this post
            product_names = self._extract_product_names(post)
            
            if not product_names:
                continue
            
            # Update data for each product mentioned in this post
            for product_name in product_names:
                data = product_data[product_name]
                data['sentiment_scores'].append(sentiment.sentiment_score)
                data['engagement_scores'].append(post.engagement_score)
                
                # Count sentiment classifications
                if sentiment.sentiment == 'positive':
                    data['positive_count'] += 1
                elif sentiment.sentiment == 'negative':
                    data['negative_count'] += 1
                elif sentiment.sentiment == 'neutral':
                    data['neutral_count'] += 1
        
        # Generate ProductInsight objects
        insights = []
        for product_name, data in product_data.items():
            # Calculate averages
            avg_sentiment = (
                sum(data['sentiment_scores']) / len(data['sentiment_scores'])
                if data['sentiment_scores'] else 0.0
            )
            avg_engagement = (
                sum(data['engagement_scores']) / len(data['engagement_scores'])
                if data['engagement_scores'] else 0.0
            )
            
            # Create insight
            insight = ProductInsight(
                product_name=product_name,
                average_sentiment=avg_sentiment,
                post_count=len(data['sentiment_scores']),
                positive_count=data['positive_count'],
                negative_count=data['negative_count'],
                neutral_count=data['neutral_count'],
                average_engagement=avg_engagement
            )
            insights.append(insight)
        
        logger.info(f"Extracted insights for {len(insights)} products")
        return insights
    
    def _extract_product_names(self, post: any) -> Set[str]:
        """
        Extract product names from a social media post.
        
        Searches for product names in:
        1. Post content (using regex patterns)
        2. Hashtags (cleaned of # symbol)
        
        Args:
            post: SocialMediaPost object
            
        Returns:
            Set of unique product names found in the post
        """
        product_names = set()
        
        # Extract from content using regex patterns
        if post.content:
            for pattern in self.product_patterns:
                matches = pattern.findall(post.content)
                for match in matches:
                    # Filter out common words and single letters
                    if match not in self.EXCLUDE_WORDS and len(match) > 1:
                        product_names.add(match)
        
        # Extract from hashtags
        if post.hashtags:
            for hashtag in post.hashtags:
                # Remove # symbol if present
                clean_hashtag = hashtag.lstrip('#')
                
                # Add hashtag if it matches product patterns and isn't a common word
                if len(clean_hashtag) > 1 and clean_hashtag not in self.EXCLUDE_WORDS:
                    # Check if hashtag matches any product pattern
                    matches_pattern = False
                    for pattern in self.product_patterns:
                        if pattern.match(clean_hashtag):
                            matches_pattern = True
                            break
                    
                    if matches_pattern:
                        product_names.add(clean_hashtag)
        
        return product_names
