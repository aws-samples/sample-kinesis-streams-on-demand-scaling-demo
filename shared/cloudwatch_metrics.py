"""
CloudWatch metrics publisher for real-time producer monitoring.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError, BotoCoreError

from .models import DemoMetrics
from .config import DemoConfig


logger = logging.getLogger(__name__)


@dataclass
class MetricDatum:
    """Represents a single CloudWatch metric data point."""
    metric_name: str
    value: float
    unit: str = 'Count'
    timestamp: Optional[datetime] = None
    dimensions: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class ProducerMetricsSnapshot:
    """Snapshot of producer metrics at a point in time."""
    timestamp: datetime
    messages_per_second: float
    throttle_exceptions_per_second: float
    average_latency_ms: float
    success_rate_percent: float
    batch_count_per_second: float
    retry_count_per_second: float
    average_message_size_bytes: float
    partition_distribution_entropy: float
    container_id: str
    demo_phase: int


class CloudWatchMetricsPublisher:
    """
    Publishes producer metrics to CloudWatch with batching and error handling.
    Uses consistent dimensions for CloudWatch native aggregation across containers.
    Supports windowed metrics with automatic reset after publishing.
    """
    
    def __init__(self, config: DemoConfig, namespace: str = None,
                 publish_interval_seconds: int = 10, max_batch_size: int = 20,
                 service_name: str = None, 
                 cluster_name: str = None):
        self.config = config
        
        # Load container-specific configuration from environment variables
        import os
        self.namespace = namespace or os.getenv('CLOUDWATCH_NAMESPACE', 'KinesisOnDemandDemo')
        self.service_name = service_name or os.getenv('SERVICE_NAME', 'kinesis-data-generator')
        self.cluster_name = cluster_name or os.getenv('CLUSTER_NAME', 'kinesis-demo-cluster')
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.deployment_id = os.getenv('DEPLOYMENT_ID', 'default')
        
        # Extract ECS runtime information if available
        self.ecs_cluster_name = self._get_ecs_cluster_name()
        self.ecs_service_name = self._get_ecs_service_name()
        self.ecs_task_definition_family = self._get_ecs_task_definition_family()
        
        # Use ECS runtime values if available and not explicitly overridden
        if self.ecs_cluster_name and self.cluster_name == 'kinesis-demo-cluster':
            self.cluster_name = self.ecs_cluster_name
        if self.ecs_service_name and self.service_name == 'kinesis-data-generator':
            self.service_name = self.ecs_service_name
        
        self.publish_interval_seconds = publish_interval_seconds
        self.max_batch_size = max_batch_size
        
        # Initialize CloudWatch client
        self.cloudwatch = boto3.client('cloudwatch', region_name=config.aws_region)
        
        # Container identification for multi-container deployments
        self.container_id = self._get_container_id()
        
        # Base dimensions for consistent CloudWatch aggregation
        self.base_dimensions = {
            'ServiceName': self.service_name,
            'ContainerID': self.container_id,
            'ClusterName': self.cluster_name,
            'Environment': self.environment,
            'DeploymentID': self.deployment_id
        }
        
        # Add ECS-specific dimensions if available
        if self.ecs_task_definition_family:
            self.base_dimensions['TaskDefinitionFamily'] = self.ecs_task_definition_family
        
        # Metrics buffer and publishing state
        self.metrics_buffer: List[MetricDatum] = []
        self.buffer_lock = asyncio.Lock()
        self.publishing_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        # Windowed metrics tracking
        self.last_publish_time = time.time()
        
        # Callback for periodic metrics publishing (set by producer)
        self.metrics_callback: Optional[callable] = None
        
        logger.info(f"CloudWatchMetricsPublisher initialized:")
        logger.info(f"  - Container ID: {self.container_id}")
        logger.info(f"  - Service Name: {self.service_name}")
        logger.info(f"  - Cluster Name: {self.cluster_name}")
        logger.info(f"  - Environment: {self.environment}")
        logger.info(f"  - CloudWatch Namespace: {self.namespace}")
        logger.info(f"  - AWS Region: {config.aws_region}")
        logger.info(f"  - Publish Interval: {self.publish_interval_seconds}s")
        logger.info(f"  - Base Dimensions: {self.base_dimensions}")
    
    def _get_container_id(self) -> str:
        """Get unique container identifier for multi-container deployments with ECS runtime support."""
        import os
        import socket
        
        # Check for explicit container ID environment variable first
        container_id = os.getenv('CONTAINER_ID')
        if container_id:
            return container_id[:16]  # Limit length for CloudWatch dimensions
        
        # Try ECS Task Metadata Endpoint V4 (Fargate and EC2)
        metadata_uri_v4 = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
        if metadata_uri_v4:
            try:
                import urllib.request
                import json
                
                # Get task metadata
                task_response = urllib.request.urlopen(f"{metadata_uri_v4}/task", timeout=2)
                task_metadata = json.loads(task_response.read().decode())
                
                # Get container metadata
                container_response = urllib.request.urlopen(metadata_uri_v4, timeout=2)
                container_metadata = json.loads(container_response.read().decode())
                
                # Extract task ID and container name
                task_arn = task_metadata.get('TaskARN', '')
                task_id = task_arn.split('/')[-1][:8] if task_arn else ''
                container_name = container_metadata.get('Name', '')
                
                if task_id and container_name:
                    return f"{task_id}-{container_name}"[:16]
                elif task_id:
                    return f"ecs-{task_id}"[:16]
                    
            except Exception as e:
                logger.debug(f"Failed to get ECS metadata: {e}")
        
        # Try ECS Task Metadata Endpoint V3 (fallback for older ECS versions)
        metadata_uri_v3 = os.getenv('ECS_CONTAINER_METADATA_URI')
        if metadata_uri_v3:
            try:
                import urllib.request
                import json
                
                response = urllib.request.urlopen(metadata_uri_v3, timeout=2)
                metadata = json.loads(response.read().decode())
                
                # Use container name and short task ARN
                container_name = metadata.get('Name', '')
                task_arn = metadata.get('Labels', {}).get('com.amazonaws.ecs.task-arn', '')
                task_id = task_arn.split('/')[-1][:8] if task_arn else ''
                
                if task_id and container_name:
                    return f"{task_id}-{container_name}"[:16]
                elif container_name:
                    return container_name[:16]
                    
            except Exception as e:
                logger.debug(f"Failed to get ECS metadata v3: {e}")
        
        # Try Kubernetes pod name
        k8s_pod = os.getenv('HOSTNAME')  # Kubernetes sets this to pod name
        if k8s_pod and k8s_pod != socket.gethostname():
            return k8s_pod[:16]
        
        # Try Docker container ID
        docker_id = os.getenv('DOCKER_CONTAINER_ID')
        if docker_id:
            return docker_id[:16]
        
        # Fallback to hostname
        hostname = socket.gethostname()
        return hostname[:16]
    
    def _get_ecs_cluster_name(self) -> Optional[str]:
        """Extract ECS cluster name from runtime metadata."""
        import os
        
        # Try ECS Task Metadata Endpoint V4
        metadata_uri_v4 = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
        if metadata_uri_v4:
            try:
                import urllib.request
                import json
                
                response = urllib.request.urlopen(f"{metadata_uri_v4}/task", timeout=2)
                metadata = json.loads(response.read().decode())
                
                cluster_arn = metadata.get('ClusterArn', '')
                if cluster_arn:
                    # Extract cluster name from ARN: arn:aws:ecs:region:account:cluster/cluster-name
                    return cluster_arn.split('/')[-1]
                    
            except Exception as e:
                logger.debug(f"Failed to get ECS cluster name: {e}")
        
        return None
    
    def _get_ecs_service_name(self) -> Optional[str]:
        """Extract ECS service name from runtime metadata."""
        import os
        
        # Try ECS Task Metadata Endpoint V4
        metadata_uri_v4 = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
        if metadata_uri_v4:
            try:
                import urllib.request
                import json
                
                response = urllib.request.urlopen(f"{metadata_uri_v4}/task", timeout=2)
                metadata = json.loads(response.read().decode())
                
                # ECS service name is in the ServiceName field
                service_name = metadata.get('ServiceName')
                if service_name:
                    return service_name
                    
                # Fallback: try to extract from task definition ARN
                task_def_arn = metadata.get('TaskDefinitionArn', '')
                if task_def_arn:
                    # Extract family name from task definition ARN
                    family = task_def_arn.split('/')[-1].split(':')[0]
                    return family
                    
            except Exception as e:
                logger.debug(f"Failed to get ECS service name: {e}")
        
        return None
    
    def _get_ecs_task_definition_family(self) -> Optional[str]:
        """Extract ECS task definition family from runtime metadata."""
        import os
        
        # Try ECS Task Metadata Endpoint V4
        metadata_uri_v4 = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
        if metadata_uri_v4:
            try:
                import urllib.request
                import json
                
                response = urllib.request.urlopen(f"{metadata_uri_v4}/task", timeout=2)
                metadata = json.loads(response.read().decode())
                
                task_def_arn = metadata.get('TaskDefinitionArn', '')
                if task_def_arn:
                    # Extract family from ARN: arn:aws:ecs:region:account:task-definition/family:revision
                    return task_def_arn.split('/')[-1].split(':')[0]
                    
            except Exception as e:
                logger.debug(f"Failed to get ECS task definition family: {e}")
        
        return None
    
    async def start_publishing(self) -> None:
        """Start the periodic metrics publishing task."""
        if self.is_running:
            logger.warning("Metrics publishing is already running")
            return
        
        # Test CloudWatch permissions before starting
        await self._test_cloudwatch_permissions()
        
        self.is_running = True
        self.publishing_task = asyncio.create_task(self._publishing_loop())
        logger.info(f"Started metrics publishing every {self.publish_interval_seconds}s")
    
    async def stop_publishing(self) -> None:
        """Stop the periodic metrics publishing task."""
        self.is_running = False
        
        if self.publishing_task and not self.publishing_task.done():
            self.publishing_task.cancel()
            try:
                await self.publishing_task
            except asyncio.CancelledError:
                pass
        
        # Flush any remaining metrics
        await self.flush_metrics()
        logger.info("Stopped metrics publishing")
    
    async def publish_producer_metrics(self, producer_metrics, demo_phase: int = 1) -> None:
        """
        Publish producer metrics to CloudWatch using windowed approach.
        
        Args:
            producer_metrics: ProducerMetrics instance from KinesisProducer
            demo_phase: Current demo phase (1-4)
        """
        current_time = datetime.now(timezone.utc)
        
        # Create snapshot from current window metrics
        snapshot = self._create_metrics_snapshot(producer_metrics, demo_phase, current_time)
        
        # Create CloudWatch metric data points
        metrics = await self._create_producer_metric_data(snapshot)
        
        # Add to buffer for batch publishing
        async with self.buffer_lock:
            self.metrics_buffer.extend(metrics)
            buffer_size = len(self.metrics_buffer)
        
        logger.debug(f"Queued {len(metrics)} producer metrics for publishing (buffer now has {buffer_size} metrics)")
    
    def _create_metrics_snapshot(self, producer_metrics, demo_phase: int, 
                                timestamp: datetime) -> ProducerMetricsSnapshot:
        """Create a metrics snapshot using windowed approach (metrics represent current window only)."""
        current_time = time.time()
        time_delta = current_time - self.last_publish_time
        
        # For windowed metrics, we use the raw counts and calculate rates based on time window
        if time_delta > 0:
            # Calculate rates for this window
            messages_per_second = producer_metrics.messages_sent / time_delta
            throttle_per_second = producer_metrics.throttle_exceptions / time_delta
            batch_per_second = producer_metrics.batch_count / time_delta
            retry_per_second = producer_metrics.retry_count / time_delta
        else:
            # Edge case: very short time window
            messages_per_second = producer_metrics.messages_sent
            throttle_per_second = producer_metrics.throttle_exceptions
            batch_per_second = producer_metrics.batch_count
            retry_per_second = producer_metrics.retry_count
        
        self.last_publish_time = current_time
        
        return ProducerMetricsSnapshot(
            timestamp=timestamp,
            messages_per_second=messages_per_second,
            throttle_exceptions_per_second=throttle_per_second,
            average_latency_ms=producer_metrics.get_average_latency_ms(),
            success_rate_percent=producer_metrics.get_success_rate(),
            batch_count_per_second=batch_per_second,
            retry_count_per_second=retry_per_second,
            average_message_size_bytes=producer_metrics.get_average_message_size(),
            partition_distribution_entropy=0.0,  # Will be calculated if partition stats available
            container_id=self.container_id,
            demo_phase=demo_phase
        )
    
    async def _create_producer_metric_data(self, snapshot: ProducerMetricsSnapshot) -> List[MetricDatum]:
        """Create CloudWatch metric data points from producer metrics snapshot."""
        # Use base dimensions plus demo phase for consistent aggregation
        dimensions = {
            **self.base_dimensions,
            'DemoPhase': str(snapshot.demo_phase)
        }
        
        metrics = [
            # Throughput metrics
            MetricDatum(
                metric_name='MessagesPerSecond',
                value=snapshot.messages_per_second,
                unit='Count/Second',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            MetricDatum(
                metric_name='BatchesPerSecond',
                value=snapshot.batch_count_per_second,
                unit='Count/Second',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            
            # Error and throttling metrics
            MetricDatum(
                metric_name='ThrottleExceptionsPerSecond',
                value=snapshot.throttle_exceptions_per_second,
                unit='Count/Second',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            MetricDatum(
                metric_name='RetriesPerSecond',
                value=snapshot.retry_count_per_second,
                unit='Count/Second',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            
            # Latency metrics
            MetricDatum(
                metric_name='AverageLatency',
                value=snapshot.average_latency_ms,
                unit='Milliseconds',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            
            # Success rate metrics
            MetricDatum(
                metric_name='SuccessRate',
                value=snapshot.success_rate_percent,
                unit='Percent',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            ),
            
            # Message size metrics
            MetricDatum(
                metric_name='AverageMessageSize',
                value=snapshot.average_message_size_bytes,
                unit='Bytes',
                timestamp=snapshot.timestamp,
                dimensions=dimensions
            )
        ]
        
        return metrics
    

    
    async def publish_custom_metric(self, metric_name: str, value: float, unit: str = 'Count',
                                   dimensions: Optional[Dict[str, str]] = None) -> None:
        """
        Publish a custom metric to CloudWatch.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: CloudWatch unit (Count, Seconds, Bytes, etc.)
            dimensions: Optional dimensions for the metric (will be merged with base dimensions)
        """
        # Merge with base dimensions for consistent aggregation
        final_dimensions = {**self.base_dimensions}
        if dimensions:
            final_dimensions.update(dimensions)
        
        metric = MetricDatum(
            metric_name=metric_name,
            value=value,
            unit=unit,
            dimensions=final_dimensions
        )
        
        async with self.buffer_lock:
            self.metrics_buffer.append(metric)
        
        logger.debug(f"Queued custom metric {metric_name}={value} for publishing")
    
    async def flush_metrics(self) -> None:
        """Flush all buffered metrics to CloudWatch immediately."""
        async with self.buffer_lock:
            if not self.metrics_buffer:
                logger.debug("No metrics in buffer to flush")
                return
            
            metrics_to_publish = self.metrics_buffer.copy()
            self.metrics_buffer.clear()
            logger.debug(f"Flushing {len(metrics_to_publish)} metrics from buffer to CloudWatch")
        
        await self._publish_metrics_batch(metrics_to_publish)
    
    def set_metrics_callback(self, callback: callable) -> None:
        """Set callback function for periodic metrics publishing."""
        self.metrics_callback = callback
    
    async def _publishing_loop(self) -> None:
        """Main publishing loop that runs periodically."""
        while self.is_running:
            try:
                await asyncio.sleep(self.publish_interval_seconds)
                
                # If we have a metrics callback, use it for periodic publishing
                if self.metrics_callback:
                    await self.metrics_callback()
                    # Flush the buffer after callback to actually publish metrics
                    await self.flush_metrics()
                else:
                    # Otherwise just flush the buffer
                    await self.flush_metrics()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics publishing loop: {e}")
                # Continue running despite errors
                await asyncio.sleep(1)
    
    async def _publish_metrics_batch(self, metrics: List[MetricDatum]) -> None:
        """Publish a batch of metrics to CloudWatch with error handling."""
        if not metrics:
            return
        
        # Split into batches of max_batch_size (CloudWatch limit is 20)
        for i in range(0, len(metrics), self.max_batch_size):
            batch = metrics[i:i + self.max_batch_size]
            await self._publish_single_batch(batch)
    
    async def _publish_single_batch(self, batch: List[MetricDatum]) -> None:
        """Publish a single batch of metrics with retry logic."""
        metric_data = []
        
        for metric in batch:
            data_point = {
                'MetricName': metric.metric_name,
                'Value': metric.value,
                'Unit': metric.unit,
                'Timestamp': metric.timestamp
            }
            
            if metric.dimensions:
                data_point['Dimensions'] = [
                    {'Name': name, 'Value': value}
                    for name, value in metric.dimensions.items()
                ]
            
            metric_data.append(data_point)
        
        # Log the metrics being published for debugging
        logger.info(f"Publishing {len(batch)} metrics to CloudWatch namespace: {self.namespace}")
        logger.debug(f"Metric names: {[m.metric_name for m in batch]}")
        
        # Retry logic for CloudWatch API calls
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.cloudwatch.put_metric_data(
                        Namespace=self.namespace,
                        MetricData=metric_data
                    )
                )
                
                logger.info(f"Successfully published {len(batch)} metrics to CloudWatch namespace: {self.namespace}")
                return
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                
                if error_code == 'Throttling' and attempt < max_retries - 1:
                    # Exponential backoff for throttling
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"CloudWatch throttled (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {error_message}")
                    await asyncio.sleep(delay)
                    continue
                elif error_code == 'AccessDenied':
                    logger.error(f"CloudWatch access denied - check IAM permissions for namespace '{self.namespace}': {error_message}")
                    logger.error(f"Required permission: cloudwatch:PutMetricData with namespace condition")
                    break
                else:
                    logger.error(f"CloudWatch API error (attempt {attempt + 1}/{max_retries}): {error_code} - {error_message}")
                    if attempt == max_retries - 1:
                        break
                    
            except (BotoCoreError, Exception) as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"CloudWatch error (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Failed to publish metrics after {max_retries} attempts: {e}")
                    break
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_publishing()
        return self
    
    async def _test_cloudwatch_permissions(self) -> None:
        """Test CloudWatch permissions by publishing a test metric."""
        try:
            test_metric = MetricDatum(
                metric_name='PermissionTest',
                value=1.0,
                unit='Count',
                dimensions=self.base_dimensions
            )
            
            logger.info(f"Testing CloudWatch permissions for namespace: {self.namespace}")
            await self._publish_single_batch([test_metric])
            logger.info("CloudWatch permissions test successful")
            
        except Exception as e:
            logger.error(f"CloudWatch permissions test failed: {e}")
            logger.error("This may indicate IAM permission issues or incorrect namespace configuration")
            # Don't raise the exception - let the application continue but log the issue
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_publishing()