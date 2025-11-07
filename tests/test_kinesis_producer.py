"""
Unit tests for KinesisProducer functionality and error scenarios.
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.kinesis_producer import (
    KinesisProducer, ProducerMetrics, BatchRequest, ExponentialBackoff,
    PartitionKeyDistributor
)
from shared.models import SocialMediaPost, PostType, GeoLocation
from shared.config import DemoConfig


class TestProducerMetrics:
    """Test ProducerMetrics functionality."""
    
    def test_initial_metrics(self):
        """Test initial metrics state."""
        metrics = ProducerMetrics()
        assert metrics.messages_sent == 0
        assert metrics.messages_failed == 0
        assert metrics.throttle_exceptions == 0
        assert metrics.message_size == 0
        assert metrics.get_average_latency_ms() == 0.0
        assert metrics.get_average_message_size() == 0.0
        assert metrics.get_success_rate() == 100.0
    
    def test_average_latency_calculation(self):
        """Test average latency calculation."""
        metrics = ProducerMetrics()
        metrics.messages_sent = 10
        metrics.total_latency_ms = 500.0
        
        assert metrics.get_average_latency_ms() == 50.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = ProducerMetrics()
        metrics.messages_sent = 80
        metrics.messages_failed = 20
        
        assert metrics.get_success_rate() == 80.0
    
    def test_success_rate_no_messages(self):
        """Test success rate with no messages."""
        metrics = ProducerMetrics()
        assert metrics.get_success_rate() == 100.0
    
    def test_average_message_size_calculation(self):
        """Test average message size calculation."""
        metrics = ProducerMetrics()
        metrics.messages_sent = 5
        metrics.message_size = 1000
        
        assert metrics.get_average_message_size() == 200.0
    
    def test_average_message_size_no_messages(self):
        """Test average message size with no messages."""
        metrics = ProducerMetrics()
        assert metrics.get_average_message_size() == 0.0


class TestBatchRequest:
    """Test BatchRequest functionality."""
    
    def test_empty_batch(self):
        """Test empty batch initialization."""
        batch = BatchRequest()
        assert batch.size() == 0
        assert not batch.is_full()
        assert batch.get_total_size_bytes() == 0
    
    def test_add_record(self):
        """Test adding records to batch."""
        from shared.models import KinesisRecord
        
        batch = BatchRequest()
        record = KinesisRecord(
            partition_key="test-key",
            data=b'{"test": "data"}'
        )
        
        batch.add_record(record)
        assert batch.size() == 1
        assert len(batch.records) == 1
        assert batch.records[0]['PartitionKey'] == "test-key"
        assert batch.records[0]['Data'] == b'{"test": "data"}'
    
    def test_batch_full_check(self):
        """Test batch full detection."""
        from shared.models import KinesisRecord
        
        batch = BatchRequest()
        
        # Add records up to max batch size
        for i in range(500):
            record = KinesisRecord(
                partition_key=f"key-{i}",
                data=b'{"test": "data"}'
            )
            batch.add_record(record)
        
        assert batch.is_full()
    
    def test_total_size_calculation(self):
        """Test total size calculation."""
        from shared.models import KinesisRecord
        
        batch = BatchRequest()
        record = KinesisRecord(
            partition_key="test-key",  # 8 bytes
            data=b'{"test": "data"}'   # 16 bytes
        )
        
        batch.add_record(record)
        expected_size = 8 + 16  # partition key + data
        assert batch.get_total_size_bytes() == expected_size


class TestExponentialBackoff:
    """Test ExponentialBackoff functionality."""
    
    def test_initial_state(self):
        """Test initial backoff state."""
        backoff = ExponentialBackoff()
        assert backoff.attempt == 0
        assert backoff.should_retry()
    
    def test_delay_calculation(self):
        """Test delay calculation with exponential growth."""
        backoff = ExponentialBackoff(base_delay=0.1, max_delay=5.0, jitter=False)
        
        # First attempt
        delay1 = backoff.get_delay()
        assert delay1 == 0.1
        
        # Second attempt
        delay2 = backoff.get_delay()
        assert delay2 == 0.2
        
        # Third attempt
        delay3 = backoff.get_delay()
        assert delay3 == 0.4
    
    def test_max_delay_limit(self):
        """Test maximum delay limit."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=2.0, jitter=False)
        
        # Exhaust attempts to reach max delay
        for _ in range(10):
            delay = backoff.get_delay()
            assert delay <= 2.0
    
    def test_max_retries(self):
        """Test maximum retry limit."""
        backoff = ExponentialBackoff(max_retries=3)
        
        # Should allow retries up to max_retries
        assert backoff.should_retry()  # attempt 0
        backoff.get_delay()  # attempt 1
        assert backoff.should_retry()
        backoff.get_delay()  # attempt 2
        assert backoff.should_retry()
        backoff.get_delay()  # attempt 3
        assert not backoff.should_retry()
    
    def test_reset(self):
        """Test backoff reset."""
        backoff = ExponentialBackoff()
        backoff.get_delay()  # Increment attempt
        backoff.reset()
        assert backoff.attempt == 0
        assert backoff.should_retry()
    
    @pytest.mark.asyncio
    async def test_wait(self):
        """Test async wait functionality."""
        backoff = ExponentialBackoff(base_delay=0.01, jitter=False)
        
        start_time = asyncio.get_event_loop().time()
        await backoff.wait()
        end_time = asyncio.get_event_loop().time()
        
        # Should wait approximately base_delay seconds
        assert 0.005 <= (end_time - start_time) <= 0.02


class TestPartitionKeyDistributor:
    """Test PartitionKeyDistributor functionality."""
    
    def test_partition_key_generation(self):
        """Test partition key generation."""
        distributor = PartitionKeyDistributor(num_partitions=100)
        post = SocialMediaPost(user_id="test_user_123")
        
        key = distributor.get_partition_key(post)
        
        # Should contain user_id and partition index
        assert "test_user_123#" in key
        assert len(key.split('#')) == 2
    
    def test_consistent_partition_keys(self):
        """Test that same user gets same partition key."""
        distributor = PartitionKeyDistributor()
        post1 = SocialMediaPost(user_id="test_user")
        post2 = SocialMediaPost(user_id="test_user")
        
        key1 = distributor.get_partition_key(post1)
        key2 = distributor.get_partition_key(post2)
        
        assert key1 == key2
    
    def test_different_users_different_partitions(self):
        """Test that different users get different partition keys."""
        distributor = PartitionKeyDistributor()
        post1 = SocialMediaPost(user_id="user1")
        post2 = SocialMediaPost(user_id="user2")
        
        key1 = distributor.get_partition_key(post1)
        key2 = distributor.get_partition_key(post2)
        
        # Keys should be different (high probability)
        assert key1 != key2
    
    def test_partition_stats(self):
        """Test partition statistics tracking."""
        distributor = PartitionKeyDistributor()
        post = SocialMediaPost(user_id="test_user")
        
        # Generate multiple keys for same user
        key1 = distributor.get_partition_key(post)
        key2 = distributor.get_partition_key(post)
        
        stats = distributor.get_partition_stats()
        assert key1 in stats
        assert stats[key1] == 2
    
    def test_reset_stats(self):
        """Test partition statistics reset."""
        distributor = PartitionKeyDistributor()
        post = SocialMediaPost(user_id="test_user")
        
        distributor.get_partition_key(post)
        assert len(distributor.get_partition_stats()) > 0
        
        distributor.reset_stats()
        assert len(distributor.get_partition_stats()) == 0


class TestKinesisProducer:
    """Test KinesisProducer functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return DemoConfig(
            stream_name="test-stream",
            aws_region="us-east-1"
        )
    
    @pytest.fixture
    def mock_kinesis_client(self):
        """Create mock Kinesis client."""
        client = Mock()
        client.put_records = Mock()
        return client
    
    @pytest.fixture
    def producer(self, config, mock_kinesis_client):
        """Create KinesisProducer with mocked client."""
        with patch('boto3.client', return_value=mock_kinesis_client):
            producer = KinesisProducer(config, max_batch_size=5, max_batch_wait_ms=50)
            producer.kinesis_client = mock_kinesis_client
            return producer
    
    def test_producer_initialization(self, config):
        """Test producer initialization."""
        with patch('boto3.client') as mock_boto:
            producer = KinesisProducer(config)
            
            assert producer.config == config
            assert producer.max_batch_size == 500
            assert producer.enable_metrics is True
            assert isinstance(producer.metrics, ProducerMetrics)
            mock_boto.assert_called_once_with('kinesis', region_name='us-east-1')
    
    @pytest.mark.asyncio
    async def test_send_single_post_success(self, producer, mock_kinesis_client):
        """Test sending a single post successfully."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [{'SequenceNumber': '123', 'ShardId': 'shard-001'}]
        }
        
        post = SocialMediaPost(
            user_id="test_user",
            content="Test post content"
        )
        
        result = await producer.send_post(post)
        assert result is True
        
        # Flush to ensure batch is sent
        await producer.flush()
        
        # Verify metrics
        assert producer.metrics.messages_sent == 1
        assert producer.metrics.messages_failed == 0
        assert producer.metrics.batch_count == 1
    
    @pytest.mark.asyncio
    async def test_send_multiple_posts_batch(self, producer, mock_kinesis_client):
        """Test sending multiple posts in batch."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [
                {'SequenceNumber': '123', 'ShardId': 'shard-001'},
                {'SequenceNumber': '124', 'ShardId': 'shard-001'},
                {'SequenceNumber': '125', 'ShardId': 'shard-001'}
            ]
        }
        
        posts = [
            SocialMediaPost(user_id=f"user_{i}", content=f"Post {i}")
            for i in range(3)
        ]
        
        successful, failed = await producer.send_posts_batch(posts)
        
        assert successful == 3
        assert failed == 0
        assert producer.metrics.messages_sent == 3
        assert producer.metrics.messages_failed == 0
    
    @pytest.mark.asyncio
    async def test_batch_size_limit(self, producer, mock_kinesis_client):
        """Test that batches are sent when size limit is reached."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [{'SequenceNumber': f'{i}', 'ShardId': 'shard-001'} for i in range(5)]
        }
        
        # Send exactly max_batch_size posts (5 in test config)
        posts = [
            SocialMediaPost(user_id=f"user_{i}", content=f"Post {i}")
            for i in range(5)
        ]
        
        for post in posts:
            await producer.send_post(post)
        
        # Should have triggered automatic batch send
        mock_kinesis_client.put_records.assert_called_once()
        assert producer.metrics.batch_count == 1
    
    @pytest.mark.asyncio
    async def test_throttling_retry(self, producer, mock_kinesis_client):
        """Test retry logic for throttling exceptions."""
        # First call returns throttling error, second succeeds
        mock_kinesis_client.put_records.side_effect = [
            ClientError(
                error_response={'Error': {'Code': 'ProvisionedThroughputExceededException'}},
                operation_name='PutRecords'
            ),
            {
                'FailedRecordCount': 0,
                'Records': [{'SequenceNumber': '123', 'ShardId': 'shard-001'}]
            }
        ]
        
        post = SocialMediaPost(user_id="test_user", content="Test post")
        
        result = await producer.send_post(post)
        await producer.flush()
        
        assert result is True
        assert producer.metrics.throttle_exceptions == 1
        assert producer.metrics.retry_count == 1
        assert producer.metrics.messages_sent == 1
        assert mock_kinesis_client.put_records.call_count == 2
    
    @pytest.mark.asyncio
    async def test_partial_failure_handling(self, producer, mock_kinesis_client):
        """Test handling of partial batch failures."""
        # Mock partial failure response
        mock_kinesis_client.put_records.side_effect = [
            {
                'FailedRecordCount': 1,
                'Records': [
                    {'SequenceNumber': '123', 'ShardId': 'shard-001'},
                    {'ErrorCode': 'ProvisionedThroughputExceededException', 'ErrorMessage': 'Throttled'}
                ]
            },
            {
                'FailedRecordCount': 0,
                'Records': [{'SequenceNumber': '124', 'ShardId': 'shard-001'}]
            }
        ]
        
        posts = [
            SocialMediaPost(user_id="user1", content="Post 1"),
            SocialMediaPost(user_id="user2", content="Post 2")
        ]
        
        successful, failed = await producer.send_posts_batch(posts)
        
        assert successful == 2
        assert failed == 0
        assert producer.metrics.throttle_exceptions == 1
        assert mock_kinesis_client.put_records.call_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker(self, producer, mock_kinesis_client):
        """Test circuit breaker functionality."""
        # Mock repeated failures to trigger circuit breaker
        mock_kinesis_client.put_records.side_effect = ClientError(
            error_response={'Error': {'Code': 'InternalFailure'}},
            operation_name='PutRecords'
        )
        
        # Send enough posts to fill multiple batches and trigger circuit breaker
        posts = [
            SocialMediaPost(user_id=f"user_{i}", content=f"Post {i}")
            for i in range(15)  # 3 full batches (5 posts each)
        ]
        
        # Send posts to trigger circuit breaker
        for post in posts:
            await producer.send_post(post)
        
        await producer.flush()
        
        # Circuit breaker should be triggered after threshold failures
        # Each batch failure increments circuit_breaker_failures
        assert producer.circuit_breaker_failures >= producer.circuit_breaker_threshold
        assert producer.metrics.messages_failed > 0
    
    @pytest.mark.asyncio
    async def test_non_retryable_error(self, producer, mock_kinesis_client):
        """Test handling of non-retryable errors."""
        # Mock non-retryable error
        mock_kinesis_client.put_records.side_effect = ClientError(
            error_response={'Error': {'Code': 'InvalidArgumentException'}},
            operation_name='PutRecords'
        )
        
        post = SocialMediaPost(user_id="test_user", content="Test post")
        
        result = await producer.send_post(post)
        await producer.flush()
        
        assert result is True  # send_post returns True, but flush will fail
        assert producer.metrics.messages_failed == 1
        mock_kinesis_client.put_records.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_timeout(self, producer, mock_kinesis_client):
        """Test batch timeout functionality."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [{'SequenceNumber': '123', 'ShardId': 'shard-001'}]
        }
        
        post = SocialMediaPost(user_id="test_user", content="Test post")
        
        # Send single post (won't fill batch)
        await producer.send_post(post)
        
        # Wait for batch timeout
        await asyncio.sleep(0.1)  # Slightly longer than max_batch_wait_ms (50ms)
        
        # Should have sent the batch due to timeout
        mock_kinesis_client.put_records.assert_called_once()
        assert producer.metrics.messages_sent == 1
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, producer, mock_kinesis_client):
        """Test comprehensive metrics collection."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [{'SequenceNumber': '123', 'ShardId': 'shard-001'}]
        }
        
        post = SocialMediaPost(user_id="test_user", content="Test post")
        
        initial_time = datetime.utcnow()
        await producer.send_post(post)
        await producer.flush()
        
        metrics = producer.get_metrics()
        assert metrics.messages_sent == 1
        assert metrics.messages_failed == 0
        assert metrics.batch_count == 1
        assert metrics.get_success_rate() == 100.0
        assert metrics.get_average_latency_ms() > 0
        assert metrics.last_send_time >= initial_time
    
    @pytest.mark.asyncio
    async def test_partition_key_distribution(self, producer):
        """Test partition key distribution."""
        posts = [
            SocialMediaPost(user_id=f"user_{i}", content=f"Post {i}")
            for i in range(10)
        ]
        
        # Generate partition keys
        for post in posts:
            producer.partition_distributor.get_partition_key(post)
        
        stats = producer.get_partition_stats()
        
        # Should have generated partition keys for different users
        assert len(stats) == 10  # 10 unique users
        
        # Each user should have 1 post
        for count in stats.values():
            assert count == 1
    
    def test_metrics_reset(self, producer):
        """Test metrics reset functionality."""
        # Simulate some activity
        producer.metrics.messages_sent = 10
        producer.metrics.throttle_exceptions = 2
        producer.partition_distributor.partition_counts["test"] = 5
        
        producer.reset_metrics()
        
        assert producer.metrics.messages_sent == 0
        assert producer.metrics.throttle_exceptions == 0
        assert len(producer.get_partition_stats()) == 0
    
    @pytest.mark.asyncio
    async def test_context_manager(self, config, mock_kinesis_client):
        """Test async context manager functionality."""
        with patch('boto3.client', return_value=mock_kinesis_client):
            async with KinesisProducer(config) as producer:
                assert isinstance(producer, KinesisProducer)
            
            # Producer should be closed after context exit
            # (No direct way to test this, but close() should have been called)
    
    @pytest.mark.asyncio
    async def test_large_batch_size_limit(self, producer, mock_kinesis_client):
        """Test 4MB batch size limit."""
        # Mock successful response
        mock_kinesis_client.put_records.return_value = {
            'FailedRecordCount': 0,
            'Records': [{'SequenceNumber': '123', 'ShardId': 'shard-001'}]
        }
        
        # Create posts that would exceed 4MB when batched
        # Each post will be roughly 1MB + metadata when serialized
        large_content = "x" * (1024 * 1024)  # 1MB content
        posts = [
            SocialMediaPost(user_id=f"user_{i}", content=large_content)
            for i in range(6)  # 6MB total, should definitely trigger size limit
        ]
        
        for post in posts:
            await producer.send_post(post)
        
        # Flush any remaining records
        await producer.flush()
        
        # Should have sent multiple batches due to size limit
        # With 1MB+ posts, we should get multiple batches
        assert mock_kinesis_client.put_records.call_count >= 2


if __name__ == "__main__":
    pytest.main([__file__])