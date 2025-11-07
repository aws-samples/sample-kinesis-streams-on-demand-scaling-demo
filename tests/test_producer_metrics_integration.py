"""
Integration tests for producer metrics functionality.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.kinesis_producer import KinesisProducer
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


class TestProducerMetricsIntegration:
    """Test producer metrics integration."""
    
    @patch('boto3.client')
    @patch('shared.kinesis_producer.CloudWatchMetricsPublisher')
    def test_producer_with_metrics_enabled(self, mock_publisher_class, mock_boto3_client, demo_config):
        """Test producer initialization with metrics enabled."""
        mock_publisher = Mock()
        mock_publisher_class.return_value = mock_publisher
        mock_boto3_client.return_value = Mock()
        
        producer = KinesisProducer(
            config=demo_config,
            enable_cloudwatch_publishing=True,
            metrics_publish_interval=5
        )
        
        assert producer.enable_cloudwatch_publishing
        assert producer.cloudwatch_publisher == mock_publisher
        assert producer.current_demo_phase == 1
        
        # Verify CloudWatch publisher was created
        mock_publisher_class.assert_called_once_with(
            config=demo_config,
            publish_interval_seconds=5
        )
    
    @patch('boto3.client')
    def test_producer_with_metrics_disabled(self, mock_boto3_client, demo_config):
        """Test producer initialization with metrics disabled."""
        mock_boto3_client.return_value = Mock()
        
        producer = KinesisProducer(
            config=demo_config,
            enable_cloudwatch_publishing=False
        )
        
        assert not producer.enable_cloudwatch_publishing
        assert producer.cloudwatch_publisher is None
    
    @patch('boto3.client')
    @patch('shared.kinesis_producer.CloudWatchMetricsPublisher')
    def test_demo_phase_management(self, mock_publisher_class, mock_boto3_client, demo_config):
        """Test demo phase management."""
        mock_publisher_class.return_value = Mock()
        mock_boto3_client.return_value = Mock()
        
        producer = KinesisProducer(config=demo_config)
        
        # Test setting valid phases
        for phase in range(1, 5):
            producer.set_demo_phase(phase)
            assert producer.current_demo_phase == phase
        
        # Test invalid phases
        with pytest.raises(ValueError):
            producer.set_demo_phase(0)
        
        with pytest.raises(ValueError):
            producer.set_demo_phase(5)
    
    @patch('boto3.client')
    @patch('shared.kinesis_producer.CloudWatchMetricsPublisher')
    @pytest.mark.asyncio
    async def test_metrics_publishing_lifecycle(self, mock_publisher_class, mock_boto3_client, demo_config):
        """Test metrics publishing lifecycle."""
        from unittest.mock import AsyncMock
        
        mock_publisher = Mock()
        mock_publisher.start_publishing = AsyncMock()
        mock_publisher.stop_publishing = AsyncMock()
        mock_publisher.publish_producer_metrics = AsyncMock()
        mock_publisher_class.return_value = mock_publisher
        mock_boto3_client.return_value = Mock()
        
        producer = KinesisProducer(config=demo_config, enable_cloudwatch_publishing=True)
        
        # Start metrics publishing
        await producer.start_metrics_publishing()
        mock_publisher.start_publishing.assert_called_once()
        
        # Publish current metrics
        await producer.publish_current_metrics()
        mock_publisher.publish_producer_metrics.assert_called_once_with(
            producer.metrics, producer.current_demo_phase
        )
        
        # Stop metrics publishing
        await producer.stop_metrics_publishing()
        mock_publisher.stop_publishing.assert_called_once()


    @patch('boto3.client')
    @patch('shared.kinesis_producer.CloudWatchMetricsPublisher')
    @pytest.mark.asyncio
    async def test_metrics_reset_after_publishing(self, mock_publisher_class, mock_boto3_client, demo_config):
        """Test that metrics are reset after publishing (windowed approach)."""
        from unittest.mock import AsyncMock
        
        mock_publisher = Mock()
        mock_publisher.start_publishing = AsyncMock()
        mock_publisher.stop_publishing = AsyncMock()
        mock_publisher.publish_producer_metrics = AsyncMock()
        mock_publisher.set_metrics_callback = Mock()
        mock_publisher_class.return_value = mock_publisher
        mock_boto3_client.return_value = Mock()
        
        producer = KinesisProducer(config=demo_config, enable_cloudwatch_publishing=True)
        
        # Simulate some activity to generate metrics
        producer.metrics.messages_sent = 100
        producer.metrics.throttle_exceptions = 5
        producer.metrics.total_latency_ms = 5000.0
        producer.metrics.batch_count = 10
        producer.metrics.message_size = 25000
        
        # Verify metrics have values before publishing
        assert producer.metrics.messages_sent == 100
        assert producer.metrics.throttle_exceptions == 5
        assert producer.metrics.total_latency_ms == 5000.0
        assert producer.metrics.batch_count == 10
        assert producer.metrics.message_size == 25000
        
        # Publish metrics
        await producer.publish_current_metrics()
        
        # Verify metrics were published
        mock_publisher.publish_producer_metrics.assert_called_once()
        
        # Verify metrics were reset after publishing (windowed approach)
        assert producer.metrics.messages_sent == 0
        assert producer.metrics.throttle_exceptions == 0
        assert producer.metrics.total_latency_ms == 0.0
        assert producer.metrics.batch_count == 0
        assert producer.metrics.retry_count == 0
        assert producer.metrics.message_size == 0
        assert producer.metrics.last_send_time is None


if __name__ == "__main__":
    pytest.main([__file__])