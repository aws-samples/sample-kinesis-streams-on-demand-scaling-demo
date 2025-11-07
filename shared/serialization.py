"""
JSON serialization/deserialization utilities for demo data models.
"""

import json
from datetime import datetime
from typing import Any, Dict, Type, TypeVar
from dataclasses import asdict, is_dataclass

from .models import SocialMediaPost, KinesisRecord, DemoMetrics, GeoLocation, PostType

T = TypeVar('T')


class DemoJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for demo data types."""
    
    def default(self, obj: Any) -> Any:
        """Convert demo objects to JSON-serializable format."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, PostType):
            return obj.value
        elif is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def serialize_to_json(obj: Any) -> str:
    """Serialize an object to JSON string."""
    try:
        return json.dumps(obj, cls=DemoJSONEncoder, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to serialize object to JSON: {e}")


def serialize_to_bytes(obj: Any) -> bytes:
    """Serialize an object to JSON bytes."""
    json_str = serialize_to_json(obj)
    return json_str.encode('utf-8')


def deserialize_from_json(json_str: str, target_class: Type[T]) -> T:
    """Deserialize JSON string to target class instance."""
    try:
        data = json.loads(json_str)
        return _dict_to_dataclass(data, target_class)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise ValueError(f"Failed to deserialize JSON to {target_class.__name__}: {e}")


def deserialize_from_bytes(json_bytes: bytes, target_class: Type[T]) -> T:
    """Deserialize JSON bytes to target class instance."""
    try:
        json_str = json_bytes.decode('utf-8')
        return deserialize_from_json(json_str, target_class)
    except UnicodeDecodeError as e:
        raise ValueError(f"Failed to decode bytes to UTF-8: {e}")


def _dict_to_dataclass(data: Dict[str, Any], target_class: Type[T]) -> T:
    """Convert dictionary to dataclass instance with type conversion."""
    if not is_dataclass(target_class):
        raise ValueError(f"{target_class.__name__} is not a dataclass")
    
    # Handle special type conversions
    converted_data = {}
    
    for field_name, field_value in data.items():
        if field_name == 'timestamp' and isinstance(field_value, str):
            # Convert ISO format string back to datetime
            converted_data[field_name] = datetime.fromisoformat(field_value)
        elif field_name == 'post_type' and isinstance(field_value, str):
            # Convert string back to PostType enum
            converted_data[field_name] = PostType(field_value)
        elif field_name == 'location' and isinstance(field_value, dict) and field_value:
            # Convert dict back to GeoLocation
            converted_data[field_name] = GeoLocation(**field_value)
        else:
            converted_data[field_name] = field_value
    
    try:
        return target_class(**converted_data)
    except TypeError as e:
        raise ValueError(f"Failed to create {target_class.__name__} instance: {e}")


# Convenience functions for common serialization tasks
def post_to_json(post: SocialMediaPost) -> str:
    """Serialize SocialMediaPost to JSON string."""
    return serialize_to_json(post)


def post_to_bytes(post: SocialMediaPost) -> bytes:
    """Serialize SocialMediaPost to JSON bytes."""
    return serialize_to_bytes(post)


def post_from_json(json_str: str) -> SocialMediaPost:
    """Deserialize JSON string to SocialMediaPost."""
    return deserialize_from_json(json_str, SocialMediaPost)


def post_from_bytes(json_bytes: bytes) -> SocialMediaPost:
    """Deserialize JSON bytes to SocialMediaPost."""
    return deserialize_from_bytes(json_bytes, SocialMediaPost)


def metrics_to_json(metrics: DemoMetrics) -> str:
    """Serialize DemoMetrics to JSON string."""
    return serialize_to_json(metrics)


def metrics_from_json(json_str: str) -> DemoMetrics:
    """Deserialize JSON string to DemoMetrics."""
    return deserialize_from_json(json_str, DemoMetrics)