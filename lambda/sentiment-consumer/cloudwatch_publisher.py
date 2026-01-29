"""
CloudWatch Publisher for sentiment analysis insights.

This module handles publishing structured JSON logs to multiple CloudWatch log streams,
with buffering, batch writing, and retry logic for resilient log delivery.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import asdict

try:
    from .models import (
        ProductInsight,
        TopicInsight,
        EngagementInsight,
        GeographicInsight,
        ViralEventInsight,
    )
    from .serialization import SentimentJSONEncoder
except ImportError:
    from models import (
        ProductInsight,
        TopicInsight,
        EngagementInsight,
        GeographicInsight,
        ViralEventInsight,
    )
    from serialization import SentimentJSONEncoder


class CloudWatchPublisher:
    """
    Publishes sentiment insights to CloudWatch Logs with buffering and retry logic.
    
    This class manages multiple log streams for different insight types, handles
    sequence token management, implements batch writing with buffering, and provides
    retry logic for transient CloudWatch API failures.
    """
    
    # Log stream names for different insight types
    PRODUCT_SENTIMENT_STREAM = "product-sentiment"
    TRENDING_TOPICS_STREAM = "trending-topics"
    ENGAGEMENT_SENTIMENT_STREAM = "engagement-sentiment"
    GEOGRAPHIC_SENTIMENT_STREAM = "geographic-sentiment"
    VIRAL_EVENTS_STREAM = "viral-events"
    
    # Buffer configuration
    MAX_BUFFER_SIZE = 100  # Maximum entries per buffer before flush
    MAX_BATCH_SIZE = 100   # Maximum entries per PutLogEvents call
    
    # Retry configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY_MS = 100
    MAX_RETRY_DELAY_MS = 1000
    
    def __init__(
        self,
        logs_client,
        log_group_name: str,
        demo_phase: Optional[int] = None,
        batch_id: Optional[str] = None,
    ):
        """
        Initialize CloudWatch publisher.
        
        Args:
            logs_client: boto3 CloudWatch Logs client
            log_group_name: Name of the CloudWatch log group
            demo_phase: Current demo phase number (for metadata)
            batch_id: Unique identifier for this processing batch
        """
        self.logs_client = logs_client
        self.log_group_name = log_group_name
        self.demo_phase = demo_phase or 0
        self.batch_id = batch_id or str(uuid.uuid4())
        
        # Buffers for each log stream
        self._buffers: Dict[str, List[Dict[str, Any]]] = {
            self.PRODUCT_SENTIMENT_STREAM: [],
            self.TRENDING_TOPICS_STREAM: [],
            self.ENGAGEMENT_SENTIMENT_STREAM: [],
            self.GEOGRAPHIC_SENTIMENT_STREAM: [],
            self.VIRAL_EVENTS_STREAM: [],
        }
        
        # Sequence tokens for each log stream
        self._sequence_tokens: Dict[str, Optional[str]] = {
            self.PRODUCT_SENTIMENT_STREAM: None,
            self.TRENDING_TOPICS_STREAM: None,
            self.ENGAGEMENT_SENTIMENT_STREAM: None,
            self.GEOGRAPHIC_SENTIMENT_STREAM: None,
            self.VIRAL_EVENTS_STREAM: None,
        }
    
    def publish_product_sentiment(
        self,
        insights: List[ProductInsight],
        processing_time_ms: Optional[float] = None,
    ) -> None:
        """
        Publish product sentiment insights to CloudWatch.
        
        Args:
            insights: List of product sentiment insights
            processing_time_ms: Time taken to process this batch
        """
        for insight in insights:
            log_entry = self._create_log_entry(
                insight_type="product_sentiment",
                data=asdict(insight),
                processing_time_ms=processing_time_ms,
            )
            self._add_to_buffer(self.PRODUCT_SENTIMENT_STREAM, log_entry)
    
    def publish_trending_topics(
        self,
        insights: List[TopicInsight],
        processing_time_ms: Optional[float] = None,
    ) -> None:
        """
        Publish trending topics insights to CloudWatch.
        
        Args:
            insights: List of trending topic insights
            processing_time_ms: Time taken to process this batch
        """
        for insight in insights:
            log_entry = self._create_log_entry(
                insight_type="trending_topics",
                data=asdict(insight),
                processing_time_ms=processing_time_ms,
            )
            self._add_to_buffer(self.TRENDING_TOPICS_STREAM, log_entry)
    
    def publish_engagement_sentiment(
        self,
        insight: EngagementInsight,
        processing_time_ms: Optional[float] = None,
    ) -> None:
        """
        Publish engagement-sentiment correlation insight to CloudWatch.
        
        Args:
            insight: Engagement sentiment insight
            processing_time_ms: Time taken to process this batch
        """
        log_entry = self._create_log_entry(
            insight_type="engagement_sentiment",
            data=asdict(insight),
            processing_time_ms=processing_time_ms,
        )
        self._add_to_buffer(self.ENGAGEMENT_SENTIMENT_STREAM, log_entry)
    
    def publish_geographic_sentiment(
        self,
        insights: List[GeographicInsight],
        processing_time_ms: Optional[float] = None,
    ) -> None:
        """
        Publish geographic sentiment insights to CloudWatch.
        
        Args:
            insights: List of geographic sentiment insights
            processing_time_ms: Time taken to process this batch
        """
        for insight in insights:
            log_entry = self._create_log_entry(
                insight_type="geographic_sentiment",
                data=asdict(insight),
                processing_time_ms=processing_time_ms,
            )
            self._add_to_buffer(self.GEOGRAPHIC_SENTIMENT_STREAM, log_entry)
    
    def publish_viral_events(
        self,
        insights: List[ViralEventInsight],
        processing_time_ms: Optional[float] = None,
    ) -> None:
        """
        Publish viral event insights to CloudWatch.
        
        Args:
            insights: List of viral event insights
            processing_time_ms: Time taken to process this batch
        """
        for insight in insights:
            log_entry = self._create_log_entry(
                insight_type="viral_events",
                data=asdict(insight),
                processing_time_ms=processing_time_ms,
            )
            self._add_to_buffer(self.VIRAL_EVENTS_STREAM, log_entry)
    
    def flush_all(self) -> None:
        """
        Flush all buffered log entries to CloudWatch.
        
        This should be called before Lambda timeout or at the end of processing
        to ensure all logs are written.
        """
        for stream_name in self._buffers.keys():
            self._flush_buffer(stream_name)
    
    def _create_log_entry(
        self,
        insight_type: str,
        data: Dict[str, Any],
        processing_time_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create a structured log entry with metadata.
        
        Args:
            insight_type: Type of insight (e.g., "product_sentiment")
            data: Insight data dictionary
            processing_time_ms: Processing time in milliseconds
            
        Returns:
            Structured log entry dictionary
        """
        # Convert datetime objects to ISO 8601 strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "insight_type": insight_type,
            "demo_phase": self.demo_phase,
            "batch_id": self.batch_id,
            "processing_time_ms": processing_time_ms,
            "data": data,
        }
    
    def _add_to_buffer(self, stream_name: str, log_entry: Dict[str, Any]) -> None:
        """
        Add log entry to buffer and flush if buffer is full.
        
        Args:
            stream_name: Name of the log stream
            log_entry: Log entry to add
        """
        self._buffers[stream_name].append(log_entry)
        
        # Flush if buffer is full
        if len(self._buffers[stream_name]) >= self.MAX_BUFFER_SIZE:
            self._flush_buffer(stream_name)
    
    def _flush_buffer(self, stream_name: str) -> None:
        """
        Flush buffered log entries to CloudWatch with retry logic.
        
        Args:
            stream_name: Name of the log stream to flush
        """
        buffer = self._buffers[stream_name]
        if not buffer:
            return
        
        # Process buffer in batches (CloudWatch limit is 10,000 events per call,
        # but we use smaller batches for better error handling)
        while buffer:
            batch = buffer[:self.MAX_BATCH_SIZE]
            
            # Convert log entries to CloudWatch format
            log_events = [
                {
                    "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    "message": json.dumps(entry, cls=SentimentJSONEncoder, ensure_ascii=False),
                }
                for entry in batch
            ]
            
            # Sort by timestamp (required by CloudWatch)
            log_events.sort(key=lambda x: x["timestamp"])
            
            # Write to CloudWatch with retry logic
            success = self._write_log_events_with_retry(stream_name, log_events)
            
            if success:
                # Remove successfully written entries from buffer
                del buffer[:self.MAX_BATCH_SIZE]
            else:
                # Keep failed entries in buffer for next attempt
                # Log warning but don't fail the entire batch
                print(f"Warning: Failed to write {len(batch)} log entries to {stream_name}")
                break
    
    def _write_log_events_with_retry(
        self,
        stream_name: str,
        log_events: List[Dict[str, Any]],
    ) -> bool:
        """
        Write log events to CloudWatch with exponential backoff retry.
        
        Args:
            stream_name: Name of the log stream
            log_events: List of log events to write
            
        Returns:
            True if write succeeded, False otherwise
        """
        retry_delay_ms = self.INITIAL_RETRY_DELAY_MS
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Prepare request parameters
                params = {
                    "logGroupName": self.log_group_name,
                    "logStreamName": stream_name,
                    "logEvents": log_events,
                }
                
                # Include sequence token if we have one
                if self._sequence_tokens[stream_name] is not None:
                    params["sequenceToken"] = self._sequence_tokens[stream_name]
                
                # Write to CloudWatch
                response = self.logs_client.put_log_events(**params)
                
                # Update sequence token for next write
                self._sequence_tokens[stream_name] = response.get("nextSequenceToken")
                
                return True
                
            except self.logs_client.exceptions.ResourceNotFoundException:
                # Log stream doesn't exist, create it
                if self._create_log_stream(stream_name):
                    # Retry write after creating stream
                    continue
                else:
                    return False
                    
            except self.logs_client.exceptions.InvalidSequenceTokenException as e:
                # Sequence token is invalid, extract correct token from error
                error_message = str(e)
                if "expectedSequenceToken" in error_message:
                    # Extract token from error message
                    import re
                    match = re.search(r'expectedSequenceToken: (\S+)', error_message)
                    if match:
                        self._sequence_tokens[stream_name] = match.group(1)
                        # Retry with correct token
                        continue
                return False
                
            except self.logs_client.exceptions.DataAlreadyAcceptedException as e:
                # Data was already accepted (duplicate), treat as success
                error_message = str(e)
                if "expectedSequenceToken" in error_message:
                    import re
                    match = re.search(r'expectedSequenceToken: (\S+)', error_message)
                    if match:
                        self._sequence_tokens[stream_name] = match.group(1)
                return True
                
            except self.logs_client.exceptions.ThrottlingException:
                # Rate limited, retry with exponential backoff
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(retry_delay_ms / 1000.0)
                    retry_delay_ms = min(retry_delay_ms * 2, self.MAX_RETRY_DELAY_MS)
                    continue
                return False
                
            except Exception as e:
                # Unexpected error, log and fail
                print(f"Error writing to CloudWatch stream {stream_name}: {e}")
                return False
        
        return False
    
    def _create_log_stream(self, stream_name: str) -> bool:
        """
        Create a log stream if it doesn't exist.
        
        Args:
            stream_name: Name of the log stream to create
            
        Returns:
            True if stream was created or already exists, False on error
        """
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group_name,
                logStreamName=stream_name,
            )
            # Reset sequence token for new stream
            self._sequence_tokens[stream_name] = None
            return True
            
        except self.logs_client.exceptions.ResourceAlreadyExistsException:
            # Stream already exists, that's fine
            self._sequence_tokens[stream_name] = None
            return True
            
        except Exception as e:
            print(f"Error creating log stream {stream_name}: {e}")
            return False
