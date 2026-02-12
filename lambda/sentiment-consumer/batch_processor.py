"""
Batch processor for grouping social media posts for optimal Bedrock API usage.

This module provides functionality to group posts into batches that balance
cost efficiency (fewer API calls) with latency (smaller batches process faster).
"""

from typing import List
import sys
import os

# Add parent directory to path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models import SocialMediaPost


class BatchProcessor:
    """
    Groups social media posts into optimal batches for Bedrock processing.
    
    The batch processor ensures that posts are grouped efficiently to minimize
    Bedrock API calls while maintaining acceptable latency. Posts are kept in
    chronological order within each batch.
    
    Attributes:
        max_batch_size: Maximum number of posts per batch (default: 25)
    """
    
    def __init__(self, max_batch_size: int = 25):
        """
        Initialize the batch processor.
        
        Args:
            max_batch_size: Maximum number of posts per Bedrock API call.
                          Defaults to 25 for optimal cost/latency balance.
        
        Raises:
            ValueError: If max_batch_size is less than 1
        """
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")
        
        self.max_batch_size = max_batch_size
    
    def create_batches(self, posts: List[SocialMediaPost]) -> List[List[SocialMediaPost]]:
        """
        Group posts into optimal batches for Bedrock processing.
        
        This method divides a list of posts into smaller batches, each containing
        at most max_batch_size posts. Posts maintain their chronological order
        within each batch.
        
        Args:
            posts: List of deserialized social media posts to batch
        
        Returns:
            List of post batches, where each batch is a list containing
            up to max_batch_size posts in chronological order
        
        Examples:
            >>> processor = BatchProcessor(max_batch_size=25)
            >>> posts = [post1, post2, post3, ..., post60]  # 60 posts
            >>> batches = processor.create_batches(posts)
            >>> len(batches)  # Returns 3 (25 + 25 + 10)
            3
            >>> len(batches[0])  # First batch has 25 posts
            25
            >>> len(batches[2])  # Last batch has remaining 10 posts
            10
        
        Notes:
            - Empty input list returns empty list of batches
            - Posts are not reordered; chronological order is preserved
            - Last batch may contain fewer than max_batch_size posts
        """
        if not posts:
            return []
        
        batches = []
        
        # Create batches by slicing the posts list
        for i in range(0, len(posts), self.max_batch_size):
            batch = posts[i:i + self.max_batch_size]
            batches.append(batch)
        
        return batches
