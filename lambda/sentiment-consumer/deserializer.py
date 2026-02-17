"""
Record deserializer for Kinesis stream records.

This module provides utilities for deserializing Kinesis records containing
social media posts into SocialMediaPost objects, with graceful error handling
for invalid or malformed records.
"""

import base64
import json
import logging
from typing import Any, Dict, Optional

# Import from shared module (available in Lambda environment)
import sys
import os

# Add parent directory to path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from shared.serialization import post_from_bytes
from shared.models import SocialMediaPost

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RecordDeserializer:
    """
    Deserializes Kinesis records into SocialMediaPost objects.
    
    This class handles the conversion of Kinesis record data (base64-encoded JSON)
    into SocialMediaPost objects, with robust error handling for malformed records.
    
    Attributes:
        None
        
    Example:
        >>> deserializer = RecordDeserializer()
        >>> kinesis_record = {
        ...     'kinesis': {
        ...         'data': 'eyJpZCI6ICIxMjMiLCAidXNlcl9pZCI6ICJ1c2VyMSJ9',
        ...         'sequenceNumber': '12345'
        ...     }
        ... }
        >>> post = deserializer.deserialize_record(kinesis_record)
    """
    
    def __init__(self):
        """Initialize the RecordDeserializer."""
        pass
    
    def deserialize_record(self, kinesis_record: Dict[str, Any]) -> Optional[SocialMediaPost]:
        """
        Deserialize a Kinesis record to SocialMediaPost.
        
        This method extracts the base64-encoded data from a Kinesis record,
        decodes it, and deserializes it into a SocialMediaPost object using
        the shared serialization utilities.
        
        Args:
            kinesis_record: Raw Kinesis record with 'kinesis' field containing
                          'data' (base64-encoded) and 'sequenceNumber' fields
                          
        Returns:
            SocialMediaPost object if deserialization succeeds, None otherwise
            
        Error Handling:
            - Logs errors with record sequence number for debugging
            - Returns None for failed records to allow batch processing to continue
            - Handles missing fields, invalid base64, malformed JSON, and validation errors
            
        Example:
            >>> deserializer = RecordDeserializer()
            >>> record = {
            ...     'kinesis': {
            ...         'data': base64.b64encode(b'{"id": "123"}').decode('utf-8'),
            ...         'sequenceNumber': '12345'
            ...     }
            ... }
            >>> post = deserializer.deserialize_record(record)
        """
        sequence_number = None
        
        try:
            # Extract Kinesis-specific fields
            kinesis_data = kinesis_record.get('kinesis', {})
            sequence_number = kinesis_data.get('sequenceNumber', 'unknown')
            
            # Get base64-encoded data
            encoded_data = kinesis_data.get('data')
            if not encoded_data:
                logger.error(
                    f"Missing 'data' field in Kinesis record. "
                    f"Sequence number: {sequence_number}"
                )
                return None
            
            # Decode base64 to bytes
            try:
                decoded_bytes = base64.b64decode(encoded_data)
            except Exception as e:
                logger.error(
                    f"Failed to decode base64 data. "
                    f"Sequence number: {sequence_number}, Error: {e}"
                )
                return None
            
            # Deserialize bytes to SocialMediaPost using shared utilities
            try:
                post = post_from_bytes(decoded_bytes)
                logger.debug(
                    f"Successfully deserialized record. "
                    f"Sequence number: {sequence_number}, Post ID: {post.id}"
                )
                return post
                
            except ValueError as e:
                # This catches JSON parsing errors and validation errors
                logger.error(
                    f"Failed to deserialize post from bytes. "
                    f"Sequence number: {sequence_number}, Error: {e}"
                )
                return None
                
        except Exception as e:
            # Catch any unexpected errors
            logger.error(
                f"Unexpected error during deserialization. "
                f"Sequence number: {sequence_number}, Error: {e}",
                exc_info=True
            )
            return None
