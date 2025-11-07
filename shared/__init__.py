"""
Shared utilities and data models for the Kinesis On-Demand Demo.
"""

from .models import SocialMediaPost, KinesisRecord, DemoMetrics, GeoLocation, PostType
from .serialization import serialize_to_json, deserialize_from_json
from .config import DemoConfig

__all__ = [
    'SocialMediaPost',
    'KinesisRecord', 
    'DemoMetrics',
    'GeoLocation',
    'PostType',
    'serialize_to_json',
    'deserialize_from_json',
    'DemoConfig'
]