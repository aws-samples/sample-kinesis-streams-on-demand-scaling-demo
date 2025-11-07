"""
Unit tests for CloudWatch metrics publisher.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.cloudwatch_metrics import (
    CloudWatchMetricsPublisher, MetricDatum, ProducerMetricsSnapshot
)
from shared.kinesis_producer import ProducerMetrics
from shared.config import DemoConfig


@pytest.fixture
def demo_config():
    """Create a test demo configuration."""
    return DemoConfig(
        baseline_tps=100,
        spike_tps=10000,
        peak_tps=50000,
        stream_name="test-stream",
        aws_region="us-east-1"
    )


@pytest.fixture
def producer_metrics():
    """Create test producer metrics."""
    metrics = ProducerMetrics()
    metrics.messages_sent = 1000
    metrics.messages_failed = 10
    metrics.throttle_exceptions = 5
    metrics.total_latency_ms = 5000.0
    metrics.batch_count = 50
    metrics.retry_count = 15
    metrics.message_size = 50000
    metrics.last_send_time = datetime.now(timezone.utc)
    return metrics


@pytest.fixture
def mock_cloudwatch_client():
    """Create a mock CloudWatch client."""
    mock_client = Mock()
    mock_client.put_metric_data = Mock()
    return mock_client


class TestMetricDatum:
    """Test MetricDatum class."""
    
    def test_metric_datum_creation(self):
        """Test creating a MetricDatum."""
        timestamp = datetime.now(timezone.utc)
        metric = MetricDatum(
            metric_name="TestMetric",
            value=42.0,
            unit="Count",
            timestamp=timestamp,
            dimensions={"TestDim": "TestValue"}
        )
        
        assert metric.metric_name == "TestMetric"
        assert metric.value == 42.0
        assert metric.unit == "Count"
        assert metric.timestamp == timestamp
        assert metric.dimensions == {"TestDim": "TestValue"}
    
    def test_metric_datum_default_timestamp(self):
        """Test MetricDatum with default timestamp."""
        metric = MetricDatum(
            metric_name="TestMetric",
            value=42.0
        )
        
        assert metric.timestamp is not None
        assert isinstance(metric.timestamp, datetime)
        assert metric.timestamp.tzinfo == timezone.utc


class TestProducerMetricsSnapshot:
    """Test ProducerMetricsSnapshot class."""
    
    def test_snapshot_creation(self):
        """Test creating a ProducerMetricsSnapshot."""
        timestamp = datetime.now(timezone.utc)
        snapshot = ProducerMetricsSnapshot(
            timestamp=timestamp,
            messages_per_second=1000.0,
            throttle_exceptions_per_second=5.0,
            average_latency_ms=50.0,
            success_rate_percent=99.0,
            batch_count_per_second=20.0,
            retry_count_per_second=3.0,
            average_message_size_bytes=512.0,
            partition_distribution_entropy=0.8,
            container_id="test-container",
            demo_phase=2
        )
        
        assert snapshot.timestamp == timestamp
        assert snapshot.messages_per_second == 1000.0
        assert snapshot.throttle_exceptions_per_second == 5.0
        assert snapshot.average_latency_ms == 50.0
        assert snapshot.success_rate_percent == 99.0
        assert snapshot.batch_count_per_second == 20.0
        assert snapshot.retry_count_per_second == 3.0
        assert snapshot.partition_distribution_entropy == 0.8
        assert snapshot.container_id == "test-container"
        assert snapshot.demo_phase == 2


class TestCloudWatchMetricsPublisher:
    """Test CloudWatchMetricsPublisher class."""
    
    @patch('boto3.client')
    def test_publisher_initialization(self, mock_boto3_client, demo_config):
        """Test CloudWatch metrics publisher initialization."""
        mock_client = Mock()
        mock_boto3_client.return_value = mock_client
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        assert publisher.config == demo_config
        assert publisher.namespace == "KinesisOnDemandDemo"
        assert publisher.publish_interval_seconds == 10
        assert publisher.max_batch_size == 20
        assert publisher.cloudwatch == mock_client
        assert publisher.container_id is not None
        assert len(publisher.container_id) <= 16
        assert not publisher.is_running
        
        mock_boto3_client.assert_called_once_with('cloudwatch', region_name='us-east-1')
    
    @patch('boto3.client')
    def test_container_id_generation(self, mock_boto3_client, demo_config):
        """Test container ID generation."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Container ID should be non-empty and limited length
        assert publisher.container_id
        assert len(publisher.container_id) <= 16
        assert isinstance(publisher.container_id, str)
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_start_stop_publishing(self, mock_boto3_client, demo_config):
        """Test starting and stopping metrics publishing."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Start publishing
        await publisher.start_publishing()
        assert publisher.is_running
        assert publisher.publishing_task is not None
        assert not publisher.publishing_task.done()
        
        # Stop publishing
        await publisher.stop_publishing()
        assert not publisher.is_running
        assert publisher.publishing_task.done()
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_publish_producer_metrics(self, mock_boto3_client, demo_config, producer_metrics):
        """Test publishing producer metrics."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Publish metrics
        await publisher.publish_producer_metrics(producer_metrics, demo_phase=2)
        
        # Check that metrics were buffered
        assert len(publisher.metrics_buffer) > 0
        
        # Verify metric names
        metric_names = {metric.metric_name for metric in publisher.metrics_buffer}
        expected_metrics = {
            'MessagesPerSecond', 'BatchesPerSecond', 'ThrottleExceptionsPerSecond',
            'RetriesPerSecond', 'AverageLatency', 'SuccessRate'
        }
        assert expected_metrics.issubset(metric_names)
        
        # Verify dimensions include base dimensions plus demo phase
        for metric in publisher.metrics_buffer:
            assert 'ServiceName' in metric.dimensions
            assert 'ContainerID' in metric.dimensions
            assert 'ClusterName' in metric.dimensions
            assert 'DemoPhase' in metric.dimensions
            assert metric.dimensions['DemoPhase'] == '2'
            assert metric.dimensions['ServiceName'] == 'kinesis-data-generator'
            assert metric.dimensions['ClusterName'] == 'kinesis-demo-cluster'
    

    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_publish_custom_metric(self, mock_boto3_client, demo_config):
        """Test publishing custom metrics."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        await publisher.publish_custom_metric(
            metric_name="CustomTestMetric",
            value=123.45,
            unit="Bytes",
            dimensions={"CustomDim": "CustomValue"}
        )
        
        # Check that custom metric was buffered
        assert len(publisher.metrics_buffer) == 1
        
        metric = publisher.metrics_buffer[0]
        assert metric.metric_name == "CustomTestMetric"
        assert metric.value == 123.45
        assert metric.unit == "Bytes"
        assert metric.dimensions["CustomDim"] == "CustomValue"
        # Should also include base dimensions
        assert metric.dimensions["ServiceName"] == "kinesis-data-generator"
        assert metric.dimensions["ContainerID"] == publisher.container_id
        assert metric.dimensions["ClusterName"] == "kinesis-demo-cluster"
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_flush_metrics_success(self, mock_boto3_client, demo_config):
        """Test successful metrics flushing to CloudWatch."""
        mock_client = Mock()
        mock_client.put_metric_data = Mock()
        mock_boto3_client.return_value = mock_client
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Add test metrics to buffer
        await publisher.publish_custom_metric("TestMetric1", 100.0)
        await publisher.publish_custom_metric("TestMetric2", 200.0)
        
        # Flush metrics
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor = mock_executor
            
            await publisher.flush_metrics()
            
            # Verify CloudWatch API was called
            mock_executor.assert_called_once()
        
        # Buffer should be empty after flush
        assert len(publisher.metrics_buffer) == 0
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_flush_metrics_with_throttling(self, mock_boto3_client, demo_config):
        """Test metrics flushing with CloudWatch throttling."""
        mock_client = Mock()
        
        # Mock throttling error on first call, success on second
        throttling_error = ClientError(
            error_response={'Error': {'Code': 'Throttling'}},
            operation_name='PutMetricData'
        )
        
        mock_client.put_metric_data.side_effect = [throttling_error, None]
        mock_boto3_client.return_value = mock_client
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Add test metric
        await publisher.publish_custom_metric("TestMetric", 100.0)
        
        # Flush with retry logic
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = AsyncMock()
            mock_executor.side_effect = [throttling_error, None]
            mock_loop.return_value.run_in_executor = mock_executor
            
            with patch('asyncio.sleep') as mock_sleep:
                await publisher.flush_metrics()
                
                # Should have retried after throttling
                assert mock_executor.call_count == 2
                mock_sleep.assert_called_once()
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_batch_size_limit(self, mock_boto3_client, demo_config):
        """Test that metrics are batched according to CloudWatch limits."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config, max_batch_size=3)
        
        # Add more metrics than batch size
        for i in range(7):
            await publisher.publish_custom_metric(f"TestMetric{i}", float(i))
        
        # Mock the publishing to track batch calls
        with patch.object(publisher, '_publish_single_batch') as mock_publish:
            await publisher.flush_metrics()
            
            # Should have been called multiple times due to batch size limit
            assert mock_publish.call_count >= 2
            
            # Verify batch sizes
            call_args_list = mock_publish.call_args_list
            total_metrics = sum(len(call[0][0]) for call in call_args_list)
            assert total_metrics == 7
    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_boto3_client, demo_config):
        """Test CloudWatch publisher as async context manager."""
        mock_boto3_client.return_value = Mock()
        
        async with CloudWatchMetricsPublisher(demo_config) as publisher:
            assert publisher.is_running
            
            # Add and publish a metric
            await publisher.publish_custom_metric("TestMetric", 42.0)
        
        # Should be stopped after context exit
        assert not publisher.is_running
    
    @patch('boto3.client')
    def test_metrics_snapshot_creation(self, mock_boto3_client, demo_config, producer_metrics):
        """Test creating metrics snapshot from producer metrics."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        timestamp = datetime.now(timezone.utc)
        
        snapshot = publisher._create_metrics_snapshot(producer_metrics, 3, timestamp)
        
        assert snapshot.timestamp == timestamp
        assert snapshot.demo_phase == 3
        assert snapshot.container_id == publisher.container_id
        assert snapshot.average_latency_ms == producer_metrics.get_average_latency_ms()
        assert snapshot.success_rate_percent == producer_metrics.get_success_rate()
        
        # Rate calculations should be non-negative
        assert snapshot.messages_per_second >= 0
        assert snapshot.throttle_exceptions_per_second >= 0
        assert snapshot.batch_count_per_second >= 0
        assert snapshot.retry_count_per_second >= 0
    

    
    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_metric_data_formatting(self, mock_boto3_client, demo_config):
        """Test proper formatting of metric data for CloudWatch API."""
        mock_client = Mock()
        mock_boto3_client.return_value = mock_client
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Create test metric with dimensions
        metric = MetricDatum(
            metric_name="TestMetric",
            value=42.5,
            unit="Milliseconds",
            dimensions={"Dim1": "Value1", "Dim2": "Value2"}
        )
        
        # Test the formatting
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor = mock_executor
            
            await publisher._publish_single_batch([metric])
            
            # Verify the call was made
            mock_executor.assert_called_once()
            
            # Verify the call structure - should have None as first arg and a callable as second
            call_args = mock_executor.call_args[0]
            assert call_args[0] is None  # executor
            assert callable(call_args[1])  # lambda function


    @patch('boto3.client')
    @pytest.mark.asyncio
    async def test_windowed_metrics_with_reset(self, mock_boto3_client, demo_config, producer_metrics):
        """Test windowed metrics approach with reset after publishing."""
        mock_boto3_client.return_value = Mock()
        
        publisher = CloudWatchMetricsPublisher(demo_config)
        
        # Set up producer metrics with some values
        producer_metrics.messages_sent = 100
        producer_metrics.throttle_exceptions = 5
        producer_metrics.total_latency_ms = 5000.0
        producer_metrics.batch_count = 10
        
        # Publish metrics (should create snapshot from current values)
        await publisher.publish_producer_metrics(producer_metrics, demo_phase=2)
        
        # Verify metrics were buffered
        assert len(publisher.metrics_buffer) > 0
        
        # Check that the snapshot used the raw values for rate calculation
        messages_metric = next(
            m for m in publisher.metrics_buffer 
            if m.metric_name == 'MessagesPerSecond'
        )
        # Should be > 0 since we have messages and time delta
        assert messages_metric.value > 0
        
        # Verify dimensions are correct
        assert messages_metric.dimensions['ServiceName'] == 'kinesis-data-generator'
        assert messages_metric.dimensions['DemoPhase'] == '2'


if __name__ == "__main__":
    pytest.main([__file__])