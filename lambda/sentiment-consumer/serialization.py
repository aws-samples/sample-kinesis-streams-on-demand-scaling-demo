"""
JSON serialization/deserialization utilities for sentiment analysis models.

This module provides utilities for converting sentiment analysis data models
to and from JSON format, following the same patterns as the shared serialization module.
"""

import json
from datetime import datetime
from typing import Any, Dict, Type, TypeVar
from dataclasses import asdict, is_dataclass

try:
    from .models import (
        SentimentResult,
        ProductInsight,
        TopicInsight,
        EngagementInsight,
        GeographicInsight,
        ViralEventInsight,
        BatchProcessingMetrics,
    )
except ImportError:
    from models import (
        SentimentResult,
        ProductInsight,
        TopicInsight,
        EngagementInsight,
        GeographicInsight,
        ViralEventInsight,
        BatchProcessingMetrics,
    )

T = TypeVar('T')


class SentimentJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for sentiment analysis data types."""
    
    def default(self, obj: Any) -> Any:
        """Convert sentiment objects to JSON-serializable format."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def serialize_to_json(obj: Any) -> str:
    """
    Serialize an object to JSON string.
    
    Args:
        obj: Object to serialize (typically a dataclass instance)
        
    Returns:
        JSON string representation
        
    Raises:
        ValueError: If serialization fails
    """
    try:
        return json.dumps(obj, cls=SentimentJSONEncoder, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to serialize object to JSON: {e}")


def serialize_to_bytes(obj: Any) -> bytes:
    """
    Serialize an object to JSON bytes.
    
    Args:
        obj: Object to serialize
        
    Returns:
        UTF-8 encoded JSON bytes
        
    Raises:
        ValueError: If serialization fails
    """
    json_str = serialize_to_json(obj)
    return json_str.encode('utf-8')


def deserialize_from_json(json_str: str, target_class: Type[T]) -> T:
    """
    Deserialize JSON string to target class instance.
    
    Args:
        json_str: JSON string to deserialize
        target_class: Target dataclass type
        
    Returns:
        Instance of target_class
        
    Raises:
        ValueError: If deserialization fails
    """
    try:
        data = json.loads(json_str)
        return _dict_to_dataclass(data, target_class)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise ValueError(f"Failed to deserialize JSON to {target_class.__name__}: {e}")


def deserialize_from_bytes(json_bytes: bytes, target_class: Type[T]) -> T:
    """
    Deserialize JSON bytes to target class instance.
    
    Args:
        json_bytes: UTF-8 encoded JSON bytes
        target_class: Target dataclass type
        
    Returns:
        Instance of target_class
        
    Raises:
        ValueError: If deserialization fails
    """
    try:
        json_str = json_bytes.decode('utf-8')
        return deserialize_from_json(json_str, target_class)
    except UnicodeDecodeError as e:
        raise ValueError(f"Failed to decode bytes to UTF-8: {e}")


def _dict_to_dataclass(data: Dict[str, Any], target_class: Type[T]) -> T:
    """
    Convert dictionary to dataclass instance with type conversion.
    
    Args:
        data: Dictionary with field values
        target_class: Target dataclass type
        
    Returns:
        Instance of target_class
        
    Raises:
        ValueError: If conversion fails
    """
    if not is_dataclass(target_class):
        raise ValueError(f"{target_class.__name__} is not a dataclass")
    
    # Handle special type conversions
    converted_data = {}
    
    for field_name, field_value in data.items():
        if field_name == 'timestamp' and isinstance(field_value, str):
            # Convert ISO format string back to datetime
            converted_data[field_name] = datetime.fromisoformat(field_value)
        else:
            converted_data[field_name] = field_value
    
    try:
        return target_class(**converted_data)
    except TypeError as e:
        raise ValueError(f"Failed to create {target_class.__name__} instance: {e}")


# Convenience functions for SentimentResult
def sentiment_result_to_json(result: SentimentResult) -> str:
    """Serialize SentimentResult to JSON string."""
    return serialize_to_json(result)


def sentiment_result_to_bytes(result: SentimentResult) -> bytes:
    """Serialize SentimentResult to JSON bytes."""
    return serialize_to_bytes(result)


def sentiment_result_from_json(json_str: str) -> SentimentResult:
    """Deserialize JSON string to SentimentResult."""
    return deserialize_from_json(json_str, SentimentResult)


def sentiment_result_from_bytes(json_bytes: bytes) -> SentimentResult:
    """Deserialize JSON bytes to SentimentResult."""
    return deserialize_from_bytes(json_bytes, SentimentResult)


# Convenience functions for ProductInsight
def product_insight_to_json(insight: ProductInsight) -> str:
    """Serialize ProductInsight to JSON string."""
    return serialize_to_json(insight)


def product_insight_from_json(json_str: str) -> ProductInsight:
    """Deserialize JSON string to ProductInsight."""
    return deserialize_from_json(json_str, ProductInsight)


# Convenience functions for TopicInsight
def topic_insight_to_json(insight: TopicInsight) -> str:
    """Serialize TopicInsight to JSON string."""
    return serialize_to_json(insight)


def topic_insight_from_json(json_str: str) -> TopicInsight:
    """Deserialize JSON string to TopicInsight."""
    return deserialize_from_json(json_str, TopicInsight)


# Convenience functions for EngagementInsight
def engagement_insight_to_json(insight: EngagementInsight) -> str:
    """Serialize EngagementInsight to JSON string."""
    return serialize_to_json(insight)


def engagement_insight_from_json(json_str: str) -> EngagementInsight:
    """Deserialize JSON string to EngagementInsight."""
    return deserialize_from_json(json_str, EngagementInsight)


# Convenience functions for GeographicInsight
def geographic_insight_to_json(insight: GeographicInsight) -> str:
    """Serialize GeographicInsight to JSON string."""
    return serialize_to_json(insight)


def geographic_insight_from_json(json_str: str) -> GeographicInsight:
    """Deserialize JSON string to GeographicInsight."""
    return deserialize_from_json(json_str, GeographicInsight)


# Convenience functions for ViralEventInsight
def viral_event_insight_to_json(insight: ViralEventInsight) -> str:
    """Serialize ViralEventInsight to JSON string."""
    return serialize_to_json(insight)


def viral_event_insight_from_json(json_str: str) -> ViralEventInsight:
    """Deserialize JSON string to ViralEventInsight."""
    return deserialize_from_json(json_str, ViralEventInsight)


# Convenience functions for BatchProcessingMetrics
def batch_metrics_to_json(metrics: BatchProcessingMetrics) -> str:
    """Serialize BatchProcessingMetrics to JSON string."""
    return serialize_to_json(metrics)


def batch_metrics_from_json(json_str: str) -> BatchProcessingMetrics:
    """Deserialize JSON string to BatchProcessingMetrics."""
    return deserialize_from_json(json_str, BatchProcessingMetrics)
