"""
Unit tests for data models.
"""

import pytest
import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import (
    SocialMediaPost, KinesisRecord, DemoMetrics, 
    GeoLocation, PostType
)


class TestGeoLocation:
    """Test GeoLocation model."""
    
    def test_valid_coordinates(self):
        """Test valid geographic coordinates."""
        location = GeoLocation(
            latitude=40.7128,
            longitude=-74.0060,
            city="New York",
            country="USA"
        )
        assert location.latitude == 40.7128
        assert location.longitude == -74.0060
        assert location.city == "New York"
        assert location.country == "USA"
    
    def test_invalid_latitude(self):
        """Test invalid latitude raises ValueError."""
        with pytest.raises(ValueError, match="Invalid latitude"):
            GeoLocation(latitude=91.0, longitude=0.0, city="Test", country="Test")
    
    def test_invalid_longitude(self):
        """Test invalid longitude raises ValueError."""
        with pytest.raises(ValueError, match="Invalid longitude"):
            GeoLocation(latitude=0.0, longitude=181.0, city="Test", country="Test")


class TestSocialMediaPost:
    """Test SocialMediaPost model."""
    
    def test_default_values(self):
        """Test post creation with default values."""
        post = SocialMediaPost(content="Test post")
        
        assert post.content == "Test post"
        assert post.id  # Should have generated ID
        assert post.timestamp  # Should have timestamp
        assert post.user_id.startswith("user_")
        assert post.username.startswith("@user_")
        assert post.hashtags == []
        assert post.mentions == []
        assert post.location is None
        assert post.engagement_score == 0.0
        assert post.post_type == PostType.ORIGINAL
    
    def test_custom_values(self):
        """Test post creation with custom values."""
        location = GeoLocation(40.7128, -74.0060, "New York", "USA")
        post = SocialMediaPost(
            user_id="test_user",
            username="@testuser",
            content="Hello world! #test @friend",
            hashtags=["test"],
            mentions=["friend"],
            location=location,
            engagement_score=5.5,
            post_type=PostType.SHARE
        )
        
        assert post.user_id == "test_user"
        assert post.username == "@testuser"
        assert post.content == "Hello world! #test @friend"
        assert post.hashtags == ["test"]
        assert post.mentions == ["friend"]
        assert post.location == location
        assert post.engagement_score == 5.5
        assert post.post_type == PostType.SHARE
    
    def test_negative_engagement_score(self):
        """Test negative engagement score raises ValueError."""
        with pytest.raises(ValueError, match="Engagement score cannot be negative"):
            SocialMediaPost(content="Test", engagement_score=-1.0)


class TestKinesisRecord:
    """Test KinesisRecord model."""
    
    def test_from_post(self):
        """Test creating Kinesis record from social media post."""
        post = SocialMediaPost(
            user_id="test_user",
            content="Test post"
        )
        data_bytes = b'{"test": "data"}'
        
        record = KinesisRecord.from_post(post, data_bytes)
        
        assert record.partition_key == "test_user"
        assert record.data == data_bytes
        assert record.explicit_hash_key is None


class TestDemoMetrics:
    """Test DemoMetrics model."""
    
    def test_default_values(self):
        """Test metrics creation with default values."""
        metrics = DemoMetrics()
        
        assert metrics.timestamp
        assert metrics.messages_per_second == 0
        assert metrics.current_shard_count == 0
        assert metrics.throttle_count == 0
        assert metrics.processing_latency_ms == 0.0
        assert metrics.current_cost_usd == 0.0
        assert metrics.demo_phase == 1
        assert metrics.ecs_task_count == 1
    
    def test_custom_values(self):
        """Test metrics creation with custom values."""
        timestamp = datetime.utcnow()
        metrics = DemoMetrics(
            timestamp=timestamp,
            messages_per_second=1000,
            current_shard_count=5,
            throttle_count=2,
            processing_latency_ms=50.5,
            current_cost_usd=1.25,
            demo_phase=3,
            ecs_task_count=10
        )
        
        assert metrics.timestamp == timestamp
        assert metrics.messages_per_second == 1000
        assert metrics.current_shard_count == 5
        assert metrics.throttle_count == 2
        assert metrics.processing_latency_ms == 50.5
        assert metrics.current_cost_usd == 1.25
        assert metrics.demo_phase == 3
        assert metrics.ecs_task_count == 10
    
    def test_validation_errors(self):
        """Test validation errors for invalid values."""
        with pytest.raises(ValueError, match="Messages per second cannot be negative"):
            DemoMetrics(messages_per_second=-1)
        
        with pytest.raises(ValueError, match="Demo phase must be between 1 and 4"):
            DemoMetrics(demo_phase=5)
        
        with pytest.raises(ValueError, match="Cost cannot be negative"):
            DemoMetrics(current_cost_usd=-1.0)