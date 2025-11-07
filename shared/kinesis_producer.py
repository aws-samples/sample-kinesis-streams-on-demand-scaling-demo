"""
Kinesis producer with batch publishing, error handling, and metrics collection.
"""

import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError, BotoCoreError
import json

from .models import SocialMediaPost, KinesisRecord, DemoMetrics
from .serialization import post_to_bytes
from .config import DemoConfig
from .cloudwatch_metrics import CloudWatchMetricsPublisher


logger = logging.getLogger(__name__)


@dataclass
class ProducerMetrics:
    """Metrics collected by the Kinesis producer."""
    messages_sent: int = 0
    messages_failed: int = 0
    throttle_exceptions: int = 0
    total_latency_ms: float = 0.0
    batch_count: int = 0
    retry_count: int = 0
    message_size: int = 0
    last_send_time: Optional[datetime] = None
    
    def get_average_latency_ms(self) -> float:
        """Calculate average latency per message."""
        if self.messages_sent == 0:
            return 0.0
        return self.total_latency_ms / self.messages_sent
    
    def get_average_message_size(self) -> float:
        """Calculate average message size in bytes."""
        if self.messages_sent == 0:
            return 0.0
        return self.message_size / self.messages_sent
    
    def get_success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total_attempts = self.messages_sent + self.messages_failed
        if total_attempts == 0:
            return 100.0
        return (self.messages_sent / total_attempts) * 100.0
    
    def reset(self) -> None:
        """Reset all metrics to zero for windowed collection."""
        self.messages_sent = 0
        self.messages_failed = 0
        self.throttle_exceptions = 0
        self.total_latency_ms = 0.0
        self.batch_count = 0
        self.retry_count = 0
        self.message_size = 0
        self.last_send_time = None


@dataclass
class BatchRequest:
    """Represents a batch of records to be sent to Kinesis."""
    records: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_record(self, record: KinesisRecord) -> None:
        """Add a record to the batch."""
        record_dict = {
            'Data': record.data,
            'PartitionKey': record.partition_key
        }
        
        # Only include ExplicitHashKey if it's not None
        if record.explicit_hash_key is not None:
            record_dict['ExplicitHashKey'] = record.explicit_hash_key
            
        self.records.append(record_dict)
    
    def size(self) -> int:
        """Get the number of records in the batch."""
        return len(self.records)
    
    def is_full(self, max_batch_size: int = 500) -> bool:
        """Check if batch is full."""
        return self.size() >= max_batch_size
    
    def get_total_size_bytes(self) -> int:
        """Calculate total size of all records in bytes."""
        total_size = 0
        for record in self.records:
            total_size += len(record['Data'])
            total_size += len(record['PartitionKey'].encode('utf-8'))
            if record.get('ExplicitHashKey'):
                total_size += len(record['ExplicitHashKey'].encode('utf-8'))
        return total_size


class ExponentialBackoff:
    """Exponential backoff with jitter for retry logic."""
    
    def __init__(self, base_delay: float = 0.1, max_delay: float = 5.0, 
                 max_retries: int = 5, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter = jitter
        self.attempt = 0
    
    def reset(self) -> None:
        """Reset the backoff state."""
        self.attempt = 0
    
    def should_retry(self) -> bool:
        """Check if we should retry based on attempt count."""
        return self.attempt < self.max_retries
    
    def get_delay(self) -> float:
        """Calculate delay for current attempt."""
        if self.attempt >= self.max_retries:
            return 0.0
        
        delay = min(self.base_delay * (2 ** self.attempt), self.max_delay)
        
        if self.jitter:
            # Add jitter to prevent thundering herd
            delay *= (0.5 + random.random() * 0.5)
        
        self.attempt += 1
        return delay
    
    async def wait(self) -> None:
        """Wait for the calculated delay."""
        delay = self.get_delay()
        if delay > 0:
            await asyncio.sleep(delay)


class PartitionKeyDistributor:
    """Manages partition key distribution for optimal shard utilization."""
    
    def __init__(self, num_partitions: int = 1000):
        self.num_partitions = num_partitions
        self.partition_counts: Dict[str, int] = {}
    
    def get_partition_key(self, post: SocialMediaPost) -> str:
        """Generate optimal partition key for a post."""
        # Use user_id as base but add distribution logic
        base_key = post.user_id
        
        # Create hash to distribute evenly across partitions
        hash_value = hashlib.md5(base_key.encode('utf-8')).hexdigest()
        partition_index = int(hash_value[:8], 16) % self.num_partitions
        
        # Create partition key that ensures even distribution
        partition_key = f"{base_key}#{partition_index:04d}"
        
        # Track partition usage for monitoring
        self.partition_counts[partition_key] = self.partition_counts.get(partition_key, 0) + 1
        
        return partition_key
    
    def get_partition_stats(self) -> Dict[str, int]:
        """Get statistics about partition key distribution."""
        return dict(self.partition_counts)
    
    def reset_stats(self) -> None:
        """Reset partition statistics."""
        self.partition_counts.clear()


class KinesisProducer:
    """
    High-performance Kinesis producer with batch publishing, error handling,
    and comprehensive metrics collection.
    """
    
    def __init__(self, config: DemoConfig, max_batch_size: int = 500,
                 max_batch_wait_ms: int = 100, enable_metrics: bool = True,
                 enable_cloudwatch_publishing: bool = True, 
                 metrics_publish_interval: int = 10):
        self.config = config
        self.max_batch_size = max_batch_size
        self.max_batch_wait_ms = max_batch_wait_ms
        self.enable_metrics = enable_metrics
        self.enable_cloudwatch_publishing = enable_cloudwatch_publishing
        
        # Initialize AWS client
        self.kinesis_client = boto3.client('kinesis', region_name=config.aws_region)
        
        # Initialize components
        self.metrics = ProducerMetrics()
        self.backoff = ExponentialBackoff(base_delay=0.01, max_delay=1.0)  # Even faster retries for high throughput
        self.partition_distributor = PartitionKeyDistributor()
        
        # Initialize CloudWatch metrics publisher
        self.cloudwatch_publisher: Optional[CloudWatchMetricsPublisher] = None
        if self.enable_cloudwatch_publishing:
            logger.info(f"Initializing CloudWatch metrics publisher (interval: {metrics_publish_interval}s)")
            self.cloudwatch_publisher = CloudWatchMetricsPublisher(
                config=config,
                publish_interval_seconds=metrics_publish_interval
            )
            # Set up callback for periodic publishing with reset
            self.cloudwatch_publisher.set_metrics_callback(self.publish_current_metrics)
            logger.info("CloudWatch metrics publisher initialized successfully")
        else:
            logger.info("CloudWatch metrics publishing disabled")
        
        # Batch management
        self.current_batch = BatchRequest()
        self.batch_lock = asyncio.Lock()
        self.batch_timer_task: Optional[asyncio.Task] = None
        
        # Circuit breaker state
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = None
        self.circuit_breaker_threshold = 3
        self.circuit_breaker_timeout = 30.0
        
        # Demo phase tracking for metrics
        self.current_demo_phase = 1
        
        logger.info(f"KinesisProducer initialized for stream: {config.stream_name}")
    
    async def send_post(self, post: SocialMediaPost) -> bool:
        """
        Send a single social media post to Kinesis.
        Returns True if successful, False otherwise.
        """
        try:
            # Serialize post to bytes
            data_bytes = post_to_bytes(post)
            
            # Create Kinesis record with optimized partition key
            partition_key = self.partition_distributor.get_partition_key(post)
            record = KinesisRecord(
                partition_key=partition_key,
                data=data_bytes
            )
            
            # Track message size for metrics
            if self.enable_metrics:
                message_size = len(data_bytes) + len(partition_key.encode('utf-8'))
                self.metrics.message_size += message_size
            
            # Add to batch
            await self._add_to_batch(record)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send post {post.id}: {e}")
            if self.enable_metrics:
                self.metrics.messages_failed += 1
            return False
    
    async def send_posts_batch(self, posts: List[SocialMediaPost]) -> Tuple[int, int]:
        """
        Send multiple posts in optimized batches.
        Returns tuple of (successful_count, failed_count).
        """
        successful = 0
        failed = 0
        
        for post in posts:
            if await self.send_post(post):
                successful += 1
            else:
                failed += 1
        
        # Flush any remaining records
        await self.flush()
        
        return successful, failed
    
    async def _add_to_batch(self, record: KinesisRecord) -> None:
        """Add record to current batch and send if batch is full."""
        async with self.batch_lock:
            self.current_batch.add_record(record)
            
            # Send batch when we have enough records or hit size/timeout limits
            if (self.current_batch.is_full(self.max_batch_size) or 
                self.current_batch.get_total_size_bytes() > 4 * 1024 * 1024):  # 4MB limit - let is_full() handle max_batch_size
                await self._send_current_batch()
            else:
                # Start timer for batch timeout if not already running
                if self.batch_timer_task is None or self.batch_timer_task.done():
                    self.batch_timer_task = asyncio.create_task(self._batch_timeout())
    
    async def _batch_timeout(self) -> None:
        """Handle batch timeout to ensure timely delivery."""
        await asyncio.sleep(self.max_batch_wait_ms / 1000.0)
        
        async with self.batch_lock:
            if self.current_batch.size() > 0:
                await self._send_current_batch()
    
    async def _send_current_batch(self) -> None:
        """Send the current batch to Kinesis with retry logic."""
        if self.current_batch.size() == 0:
            return
        
        # Check circuit breaker
        if self._is_circuit_breaker_open():
            logger.warning("Circuit breaker is open, dropping batch")
            if self.enable_metrics:
                self.metrics.messages_failed += self.current_batch.size()
            self.current_batch = BatchRequest()
            return
        
        batch_to_send = self.current_batch
        self.current_batch = BatchRequest()
        
        start_time = time.time()
        
        try:
            await self._send_batch_with_retry(batch_to_send)
            
            # Update metrics on success
            if self.enable_metrics:
                latency_ms = (time.time() - start_time) * 1000
                self.metrics.messages_sent += batch_to_send.size()
                self.metrics.total_latency_ms += latency_ms
                self.metrics.batch_count += 1
                self.metrics.last_send_time = datetime.utcnow()
            
            # Reset circuit breaker on success
            self.circuit_breaker_failures = 0
            
        except Exception as e:
            logger.error(f"Failed to send batch after retries: {e}")
            
            # Update circuit breaker
            self.circuit_breaker_failures += 1
            self.circuit_breaker_last_failure = time.time()
            
            # Update metrics on failure
            if self.enable_metrics:
                self.metrics.messages_failed += batch_to_send.size()
    
    async def _send_batch_with_retry(self, batch: BatchRequest) -> None:
        """Send batch with exponential backoff retry logic."""
        self.backoff.reset()
        
        while self.backoff.should_retry():
            try:
                response = await self._put_records(batch.records)
                
                # Check for partial failures and throttling
                failed_records = response.get('FailedRecordCount', 0)
                
                if failed_records == 0:
                    # Complete success
                    return
                
                # Handle partial failures
                await self._handle_partial_failure(response, batch)
                return
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code == 'ProvisionedThroughputExceededException':
                    # Throttling - increment counter and retry with backoff
                    if self.enable_metrics:
                        self.metrics.throttle_exceptions += 1
                        self.metrics.retry_count += 1
                    
                    logger.warning(f"Throttled, retrying in {self.backoff.get_delay():.2f}s")
                    await self.backoff.wait()
                    continue
                
                elif error_code in ['InternalFailure', 'ServiceUnavailable']:
                    # Retryable service errors
                    if self.enable_metrics:
                        self.metrics.retry_count += 1
                    
                    logger.warning(f"Service error {error_code}, retrying")
                    await self.backoff.wait()
                    continue
                
                else:
                    # Non-retryable error
                    logger.error(f"Non-retryable error: {error_code}")
                    raise
            
            except (BotoCoreError, Exception) as e:
                # Network or other errors - retry with backoff
                if self.enable_metrics:
                    self.metrics.retry_count += 1
                
                logger.warning(f"Network/service error, retrying: {e}")
                await self.backoff.wait()
                continue
        
        # Exhausted retries
        raise Exception(f"Failed to send batch after {self.backoff.max_retries} retries")
    
    async def _put_records(self, records: List[Dict]) -> Dict:
        """Send records to Kinesis using put_records API."""
        loop = asyncio.get_event_loop()
        
        # Run the synchronous boto3 call in a thread pool
        response = await loop.run_in_executor(
            None,
            lambda: self.kinesis_client.put_records(
                Records=records,
                StreamName=self.config.stream_name
            )
        )
        
        return response
    
    async def _handle_partial_failure(self, response: Dict, original_batch: BatchRequest) -> None:
        """Handle partial failures by retrying failed records."""
        failed_records = []
        
        for i, record_result in enumerate(response.get('Records', [])):
            if 'ErrorCode' in record_result:
                error_code = record_result['ErrorCode']
                
                if error_code == 'ProvisionedThroughputExceededException':
                    # Throttled record - retry
                    failed_records.append(original_batch.records[i])
                    if self.enable_metrics:
                        self.metrics.throttle_exceptions += 1
                else:
                    # Other error - log and skip
                    logger.error(f"Record failed with error: {error_code}")
                    if self.enable_metrics:
                        self.metrics.messages_failed += 1
        
        # Retry failed records if any
        if failed_records:
            retry_batch = BatchRequest()
            retry_batch.records = failed_records
            
            logger.info(f"Retrying {len(failed_records)} failed records")
            await asyncio.sleep(0.005)  # Further reduced delay to 5ms for maximum throughput
            await self._send_batch_with_retry(retry_batch)
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.circuit_breaker_failures < self.circuit_breaker_threshold:
            return False
        
        if self.circuit_breaker_last_failure is None:
            return False
        
        time_since_failure = time.time() - self.circuit_breaker_last_failure
        return time_since_failure < self.circuit_breaker_timeout
    
    async def flush(self) -> None:
        """Flush any pending records in the current batch."""
        async with self.batch_lock:
            if self.current_batch.size() > 0:
                await self._send_current_batch()
    
    def get_metrics(self) -> ProducerMetrics:
        """Get current producer metrics."""
        return self.metrics
    
    def reset_metrics(self) -> None:
        """Reset producer metrics."""
        self.metrics = ProducerMetrics()
        self.partition_distributor.reset_stats()
    
    def get_partition_stats(self) -> Dict[str, int]:
        """Get partition key distribution statistics."""
        return self.partition_distributor.get_partition_stats()
    
    async def start_metrics_publishing(self) -> None:
        """Start CloudWatch metrics publishing."""
        if self.cloudwatch_publisher:
            await self.cloudwatch_publisher.start_publishing()
            logger.info("Started CloudWatch metrics publishing")
    
    async def stop_metrics_publishing(self) -> None:
        """Stop CloudWatch metrics publishing."""
        if self.cloudwatch_publisher:
            await self.cloudwatch_publisher.stop_publishing()
            logger.info("Stopped CloudWatch metrics publishing")
    
    def set_demo_phase(self, phase: int) -> None:
        """Update the current demo phase for metrics tracking."""
        if not 1 <= phase <= 4:
            raise ValueError("Demo phase must be between 1 and 4")
        self.current_demo_phase = phase
        logger.info(f"Updated demo phase to {phase}")
    
    async def publish_current_metrics(self) -> None:
        """Publish current producer metrics to CloudWatch and reset for next window."""
        if self.cloudwatch_publisher and self.enable_metrics:
            logger.info(f"Publishing producer metrics - Messages sent: {self.metrics.messages_sent}, "
                       f"Failed: {self.metrics.messages_failed}, Phase: {self.current_demo_phase}")
            await self.cloudwatch_publisher.publish_producer_metrics(
                self.metrics, 
                self.current_demo_phase
            )
            # Reset metrics for next window (windowed approach)
            self.metrics.reset()
        else:
            if not self.cloudwatch_publisher:
                logger.warning("CloudWatch publisher not initialized - metrics not published")
            if not self.enable_metrics:
                logger.debug("Metrics publishing disabled")
    
    async def close(self) -> None:
        """Close the producer and flush any pending records."""
        # Stop metrics publishing first
        if self.cloudwatch_publisher:
            await self.stop_metrics_publishing()
        
        # Cancel batch timer if running
        if self.batch_timer_task and not self.batch_timer_task.done():
            self.batch_timer_task.cancel()
            try:
                await self.batch_timer_task
            except asyncio.CancelledError:
                pass
        
        # Flush any remaining records
        await self.flush()
        
        logger.info("KinesisProducer closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self.cloudwatch_publisher:
            await self.start_metrics_publishing()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()