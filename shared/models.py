"""
Core data models for the Kinesis On-Demand Demo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid


class PostType(Enum):
    """Types of social media posts."""
    ORIGINAL = "original"
    SHARE = "share"
    REPLY = "reply"


@dataclass
class GeoLocation:
    """Geographic location data for social media posts."""
    latitude: float
    longitude: float
    city: str
    country: str

    def __post_init__(self):
        """Validate geographic coordinates."""
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude: {self.longitude}")


@dataclass
class SocialMediaPost:
    """Social media post data model."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    user_id: str = ""
    username: str = ""
    content: str = ""
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    location: Optional[GeoLocation] = None
    engagement_score: float = 0.0
    post_type: PostType = PostType.ORIGINAL

    def __post_init__(self):
        """Validate post data."""
        if not self.user_id:
            self.user_id = f"user_{uuid.uuid4().hex[:8]}"
        if not self.username:
            self.username = f"@{self.user_id}"
        if self.engagement_score < 0:
            raise ValueError("Engagement score cannot be negative")


@dataclass
class KinesisRecord:
    """Kinesis record wrapper for social media posts."""
    partition_key: str
    data: bytes
    explicit_hash_key: Optional[str] = None

    @classmethod
    def from_post(cls, post: SocialMediaPost, data_bytes: bytes) -> 'KinesisRecord':
        """Create a Kinesis record from a social media post."""
        # Use user_id as partition key for even distribution
        partition_key = post.user_id
        return cls(
            partition_key=partition_key,
            data=data_bytes,
            explicit_hash_key=None
        )


@dataclass
class DemoMetrics:
    """Demo metrics data model."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    messages_per_second: int = 0
    current_shard_count: int = 0
    throttle_count: int = 0
    processing_latency_ms: float = 0.0
    current_cost_usd: float = 0.0
    demo_phase: int = 1
    ecs_task_count: int = 1

    def __post_init__(self):
        """Validate metrics data."""
        if self.messages_per_second < 0:
            raise ValueError("Messages per second cannot be negative")
        if self.current_shard_count < 0:
            raise ValueError("Shard count cannot be negative")
        if self.throttle_count < 0:
            raise ValueError("Throttle count cannot be negative")
        if self.processing_latency_ms < 0:
            raise ValueError("Processing latency cannot be negative")
        if self.current_cost_usd < 0:
            raise ValueError("Cost cannot be negative")
        if not 1 <= self.demo_phase <= 4:
            raise ValueError("Demo phase must be between 1 and 4")
        if self.ecs_task_count < 0:
            raise ValueError("ECS task count cannot be negative")