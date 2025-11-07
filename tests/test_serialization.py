"""
Unit tests for serialization utilities.
"""

import pytest
import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import (
    SocialMediaPost, DemoMetrics, GeoLocation, PostType
)
from shared.serialization import (
    serialize_to_json, deserialize_from_json,
    serialize_to_bytes, deserialize_from_bytes,
    post_to_json, post_from_json,
    post_to_bytes, post_from_bytes,
    metrics_to_json, metrics_from_json
)


class TestSerialization:
    """Test JSON serialization/deserialization."""
    
    def test_social_media_post_serialization(self):
        """Test SocialMediaPost serialization round-trip."""
        location = GeoLocation(40.7128, -74.0060, "New York", "USA")
        original_post = SocialMediaPost(
            user_id="test_user",
            username="@testuser",
            content="Hello world! #test @friend",
            hashtags=["test", "demo"],
            mentions=["friend"],
            location=location,
            engagement_score=5.5,
            post_type=PostType.SHARE
        )
        
        # Test JSON string serialization
        json_str = post_to_json(original_post)
        assert isinstance(json_str, str)
        assert "test_user" in json_str
        assert "share" in json_str
        
        # Test deserialization
        deserialized_post = post_from_json(json_str)
        assert deserialized_post.user_id == original_post.user_id
        assert deserialized_post.username == original_post.username
        assert deserialized_post.content == original_post.content
        assert deserialized_post.hashtags == original_post.hashtags
        assert deserialized_post.mentions == original_post.mentions
        assert deserialized_post.engagement_score == original_post.engagement_score
        assert deserialized_post.post_type == original_post.post_type
        assert deserialized_post.location.city == original_post.location.city
    
    def test_bytes_serialization(self):
        """Test bytes serialization round-trip."""
        post = SocialMediaPost(content="Test post")
        
        # Test bytes serialization
        json_bytes = post_to_bytes(post)
        assert isinstance(json_bytes, bytes)
        
        # Test deserialization from bytes
        deserialized_post = post_from_bytes(json_bytes)
        assert deserialized_post.content == post.content
    
    def test_demo_metrics_serialization(self):
        """Test DemoMetrics serialization round-trip."""
        original_metrics = DemoMetrics(
            messages_per_second=1000,
            current_shard_count=5,
            throttle_count=2,
            processing_latency_ms=50.5,
            current_cost_usd=1.25,
            demo_phase=3,
            ecs_task_count=10
        )
        
        # Test serialization
        json_str = metrics_to_json(original_metrics)
        assert isinstance(json_str, str)
        
        # Test deserialization
        deserialized_metrics = metrics_from_json(json_str)
        assert deserialized_metrics.messages_per_second == original_metrics.messages_per_second
        assert deserialized_metrics.current_shard_count == original_metrics.current_shard_count
        assert deserialized_metrics.demo_phase == original_metrics.demo_phase