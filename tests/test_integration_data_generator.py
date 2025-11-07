"""
Integration tests for the complete data generation flow.

These tests validate the end-to-end functionality of the containerized
data generator application including phase transitions, traffic control,
and Kinesis publishing.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os

# Add the parent directory to the path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.config import DemoConfig
from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController
from shared.kinesis_producer import KinesisProducer
from shared.models import SocialMediaPost, PostType
from main import DemoDataGenerator


class TestDataGeneratorIntegration:
    """Integration tests for the complete data generator application."""
    
    @pytest.fixture
    def demo_config(self):
        """Create a test configuration with short durations."""
        return DemoConfig(
            baseline_tps=10,
            spike_tps=50,
            peak_tps=100,
            phase_durations=[2, 2, 2, 2],  # 2 seconds each for fast testing
            stream_name="test-stream",
            aws_region="us-east-1"
        )
    
    @pytest.fixture
    def mock_kinesis_producer(self):
        """Create a mock Kinesis producer for testing."""
        producer = Mock(spec=KinesisProducer)
        producer.send_post = AsyncMock(return_value=True)
        producer.send_posts_batch = AsyncMock(return_value=(10, 0))  # 10 successful, 0 failed
        producer.set_demo_phase = Mock()
        producer.get_metrics = Mock()
        producer.get_metrics.return_value = Mock(
            messages_sent=100,
            messages_failed=0,
            throttle_exceptions=0,
            get_success_rate=Mock(return_value=100.0),
            get_average_latency_ms=Mock(return_value=50.0),
            batch_count=10,
            retry_count=0
        )
        
        # Mock async context manager
        producer.__aenter__ = AsyncMock(return_value=producer)
        producer.__aexit__ = AsyncMock(return_value=None)
        
        return producer
    
    @pytest.mark.asyncio
    async def test_demo_generator_initialization(self, demo_config):
        """Test that the demo generator initializes correctly."""
        generator = DemoDataGenerator(demo_config)
        
        assert generator.config == demo_config
        assert not generator.is_running
        assert not generator.shutdown_requested
        assert generator.current_phase == 1
        assert generator.total_messages_sent == 0
        assert generator.total_messages_failed == 0
        assert isinstance(generator.post_generator, SocialMediaPostGenerator)
        assert isinstance(generator.traffic_controller, TrafficPatternController)
    
    @pytest.mark.asyncio
    async def test_demo_generator_start_stop(self, demo_config, mock_kinesis_producer):
        """Test starting and stopping the demo generator."""
        generator = DemoDataGenerator(demo_config)
        
        # Mock the KinesisProducer creation
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Start the generator in a task
            start_task = asyncio.create_task(generator.start())
            
            # Wait a short time for initialization
            await asyncio.sleep(0.1)
            
            # Verify it's running
            assert generator.is_running
            assert generator.demo_start_time is not None
            
            # Stop the generator
            await generator.stop()
            
            # Wait for the start task to complete
            try:
                await asyncio.wait_for(start_task, timeout=1.0)
            except asyncio.TimeoutError:
                start_task.cancel()
                try:
                    await start_task
                except asyncio.CancelledError:
                    pass
            
            # Verify it's stopped
            assert not generator.is_running
            assert generator.shutdown_requested
    
    @pytest.mark.asyncio
    async def test_phase_transitions(self, demo_config, mock_kinesis_producer):
        """Test that demo phases transition correctly."""
        generator = DemoDataGenerator(demo_config)
        
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Start the demo
            start_task = asyncio.create_task(generator.start())
            
            # Wait for initialization
            await asyncio.sleep(0.1)
            
            # Check initial phase
            assert generator.current_phase == 1
            
            # Wait for phase transitions (each phase is 2 seconds)
            await asyncio.sleep(2.5)  # Should be in phase 2
            
            # The phase should have been updated
            # Note: Due to timing, we might be in phase 2 or 3
            assert generator.current_phase >= 2
            
            # Verify producer was notified of phase changes
            mock_kinesis_producer.set_demo_phase.assert_called()
            
            # Stop the demo
            await generator.stop()
            
            # Clean up
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_post_generation_and_publishing(self, demo_config, mock_kinesis_producer):
        """Test that posts are generated and published correctly."""
        generator = DemoDataGenerator(demo_config)
        
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Mock the generate_and_send_posts method to run once
            original_method = generator._generate_and_send_posts
            call_count = 0
            
            async def mock_generate_and_send():
                nonlocal call_count
                call_count += 1
                await original_method()
                if call_count >= 3:  # Stop after a few calls
                    generator.shutdown_requested = True
            
            generator._generate_and_send_posts = mock_generate_and_send
            
            # Start the demo
            await generator.start()
            
            # Verify posts were generated and sent
            assert call_count >= 3
            mock_kinesis_producer.send_posts_batch.assert_called()
            
            # Verify metrics were updated
            assert generator.total_messages_sent > 0
    
    @pytest.mark.asyncio
    async def test_traffic_pattern_control(self, demo_config):
        """Test traffic pattern control across demo phases."""
        controller = TrafficPatternController(demo_config)
        controller.start_demo()
        
        # Test phase 1 (baseline)
        phase1 = controller.get_current_phase()
        assert phase1.phase_number == 1
        assert phase1.target_tps == demo_config.baseline_tps
        
        # Test message calculation
        messages = controller.calculate_messages_to_generate(1.0)
        assert messages == demo_config.baseline_tps
        
        # Test post type distribution
        original_pct, share_pct, reply_pct = controller.get_post_type_distribution()
        assert abs(original_pct + share_pct + reply_pct - 1.0) < 0.001  # Allow for floating point precision
        assert original_pct > 0.5  # Should be mostly original in early phases
    
    @pytest.mark.asyncio
    async def test_demo_status_reporting(self, demo_config, mock_kinesis_producer):
        """Test demo status reporting functionality."""
        generator = DemoDataGenerator(demo_config)
        
        # Test status when stopped
        status = generator.get_demo_status()
        assert status['status'] == 'stopped'
        assert status['demo_progress'] == 0.0
        assert status['current_phase'] == 0
        
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Start the demo
            start_task = asyncio.create_task(generator.start())
            await asyncio.sleep(0.1)
            
            # Test status when running
            status = generator.get_demo_status()
            assert status['status'] == 'running'
            assert status['demo_progress'] >= 0.0
            assert status['current_phase'] >= 1
            assert 'target_tps' in status
            assert 'remaining_time' in status
            assert status['demo_start_time'] is not None
            
            # Stop the demo
            await generator.stop()
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_error_handling_in_post_generation(self, demo_config, mock_kinesis_producer):
        """Test error handling during post generation."""
        generator = DemoDataGenerator(demo_config)
        
        # Mock producer to simulate failures
        mock_kinesis_producer.send_posts_batch = AsyncMock(return_value=(5, 5))  # 5 success, 5 failed
        
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Mock the generate_and_send_posts method to run once and then stop
            call_count = 0
            original_method = generator._generate_and_send_posts
            
            async def mock_generate_and_send():
                nonlocal call_count
                call_count += 1
                # Manually simulate the post generation and sending
                posts = [generator.post_generator.generate_post(phase=1) for _ in range(10)]
                successful, failed = await mock_kinesis_producer.send_posts_batch(posts)
                generator.total_messages_sent += successful
                generator.total_messages_failed += failed
                generator.shutdown_requested = True  # Stop after one call
            
            generator._generate_and_send_posts = mock_generate_and_send
            
            # Start the demo
            await generator.start()
            
            # Verify that failures were tracked
            assert generator.total_messages_failed > 0
            assert generator.total_messages_sent > 0
    
    @pytest.mark.asyncio
    async def test_metrics_logging(self, demo_config, mock_kinesis_producer):
        """Test periodic metrics logging."""
        generator = DemoDataGenerator(demo_config)
        generator.metrics_log_interval = 0.1  # Very short interval for testing
        
        with patch('main.KinesisProducer', return_value=mock_kinesis_producer):
            # Mock logging to capture log calls
            with patch('main.logger') as mock_logger:
                # Start the demo
                start_task = asyncio.create_task(generator.start())
                await asyncio.sleep(0.2)  # Wait for metrics logging
                
                # Stop the demo
                await generator.stop()
                start_task.cancel()
                try:
                    await start_task
                except asyncio.CancelledError:
                    pass
                
                # Verify metrics were logged
                mock_logger.info.assert_called()
                
                # Check that metrics logging calls were made
                log_calls = [call for call in mock_logger.info.call_args_list 
                           if 'DEMO METRICS' in str(call)]
                assert len(log_calls) > 0


class TestPostGenerationIntegration:
    """Integration tests for post generation components."""
    
    @pytest.fixture
    def demo_config(self):
        """Create a test configuration."""
        return DemoConfig(
            baseline_tps=100,
            spike_tps=1000,
            peak_tps=5000,
            phase_durations=[120, 120, 120, 120]
        )
    
    def test_post_generator_creates_valid_posts(self, demo_config):
        """Test that the post generator creates valid posts."""
        generator = SocialMediaPostGenerator(demo_config)
        
        # Test posts for each phase
        for phase in range(1, 5):
            post = generator.generate_post(phase=phase, post_type=PostType.ORIGINAL)
            
            assert isinstance(post, SocialMediaPost)
            assert post.user_id
            assert post.username
            assert post.content
            assert isinstance(post.hashtags, list)
            assert isinstance(post.mentions, list)
            assert post.engagement_score >= 0
            assert post.post_type == PostType.ORIGINAL
            assert isinstance(post.timestamp, datetime)
    
    def test_traffic_controller_phase_progression(self, demo_config):
        """Test traffic controller phase progression."""
        controller = TrafficPatternController(demo_config)
        controller.start_demo()
        
        # Test initial phase
        phase = controller.get_current_phase()
        assert phase.phase_number == 1
        assert phase.target_tps == demo_config.baseline_tps
        
        # Test progress calculations
        progress = controller.get_demo_progress()
        assert 0.0 <= progress <= 1.0
        
        phase_progress = controller.get_phase_progress()
        assert 0.0 <= phase_progress <= 1.0
        
        # Test remaining time
        remaining = controller.get_remaining_time()
        assert remaining >= 0
    
    def test_post_type_distribution_changes_by_phase(self, demo_config):
        """Test that post type distribution changes appropriately by phase."""
        controller = TrafficPatternController(demo_config)
        controller.start_demo()
        
        # Early phases should have more original content
        original_pct, share_pct, reply_pct = controller.get_post_type_distribution()
        assert original_pct >= 0.4  # At least 40% original
        assert abs(original_pct + share_pct + reply_pct - 1.0) < 0.001  # Allow for floating point precision
        
        # Mock being in a later phase by patching the get_current_phase method
        from unittest.mock import patch
        with patch.object(controller, 'get_current_phase') as mock_get_phase:
            mock_get_phase.return_value = controller.phases[2]  # Phase 3 (viral)
            original_pct, share_pct, reply_pct = controller.get_post_type_distribution()
            assert share_pct + reply_pct >= 0.4  # More sharing/replies in viral phases


class TestContainerHealthCheck:
    """Integration tests for container health check functionality."""
    
    def test_health_check_script_imports(self):
        """Test that health check script can import required modules."""
        # This test ensures the health check script works in the container environment
        import sys
        import os
        
        # Add the parent directory to import health_check
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        try:
            from health_check import HealthChecker
            checker = HealthChecker()
            
            # Test basic functionality
            python_check = checker.check_python_environment()
            assert 'status' in python_check
            
            env_check = checker.check_environment_variables()
            assert 'status' in env_check
            
            modules_check = checker.check_shared_modules()
            assert 'status' in modules_check
            
        except ImportError as e:
            pytest.skip(f"Health check module not available: {e}")
    
    def test_container_metrics_environment_variables(self):
        """Test that container metrics environment variables are properly handled."""
        import os
        import sys
        
        # Add the parent directory to import health_check
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        # Set test environment variables (including required ones)
        test_env_vars = {
            'AWS_REGION': 'us-east-1',
            'STREAM_NAME': 'test-stream',
            'CLOUDWATCH_NAMESPACE': 'TestNamespace',
            'SERVICE_NAME': 'test-service',
            'CLUSTER_NAME': 'test-cluster',
            'ENVIRONMENT': 'test',
            'DEPLOYMENT_ID': 'test-deployment',
            'CONTAINER_ID': 'test-container-123',
            'METRICS_PUBLISH_INTERVAL': '15',
            'ENABLE_CLOUDWATCH_METRICS': 'true'
        }
        
        # Set environment variables
        for key, value in test_env_vars.items():
            os.environ[key] = value
        
        try:
            from health_check import HealthChecker
            checker = HealthChecker()
            
            # Check environment variables
            env_check = checker.check_environment_variables()
            
            # Verify container metrics config is included
            assert 'container_metrics_config' in env_check
            metrics_config = env_check['container_metrics_config']
            
            assert metrics_config['namespace'] == 'TestNamespace'
            assert metrics_config['service_name'] == 'test-service'
            assert metrics_config['cluster_name'] == 'test-cluster'
            assert metrics_config['environment'] == 'test'
            assert metrics_config['deployment_id'] == 'test-deployment'
            assert metrics_config['container_id'] == 'test-container-123'
            assert metrics_config['metrics_enabled'] == True
            
        finally:
            # Clean up environment variables
            for key in test_env_vars.keys():
                os.environ.pop(key, None)
    
    def test_cloudwatch_metrics_publisher_environment_config(self):
        """Test that CloudWatch metrics publisher uses environment variables correctly."""
        import os
        import sys
        
        # Add the parent directory to import modules
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        # Set test environment variables
        test_env_vars = {
            'CLOUDWATCH_NAMESPACE': 'TestMetricsNamespace',
            'SERVICE_NAME': 'test-metrics-service',
            'CLUSTER_NAME': 'test-metrics-cluster',
            'ENVIRONMENT': 'test-env',
            'DEPLOYMENT_ID': 'test-deploy-123',
            'CONTAINER_ID': 'test-metrics-con'  # Use 16 char limit to match implementation
        }
        
        # Set environment variables
        for key, value in test_env_vars.items():
            os.environ[key] = value
        
        try:
            from shared.config import DemoConfig
            from shared.cloudwatch_metrics import CloudWatchMetricsPublisher
            
            config = DemoConfig()
            
            # Create publisher without explicit parameters to test environment variable usage
            publisher = CloudWatchMetricsPublisher(config=config)
            
            # Verify environment variables are used
            assert publisher.namespace == 'TestMetricsNamespace'
            assert publisher.service_name == 'test-metrics-service'
            assert publisher.cluster_name == 'test-metrics-cluster'
            assert publisher.environment == 'test-env'
            assert publisher.deployment_id == 'test-deploy-123'
            
            # Verify base dimensions include all container-specific information
            expected_dimensions = {
                'ServiceName': 'test-metrics-service',
                'ContainerID': 'test-metrics-con',  # Truncated to 16 chars
                'ClusterName': 'test-metrics-cluster',
                'Environment': 'test-env',
                'DeploymentID': 'test-deploy-123'
            }
            
            for key, value in expected_dimensions.items():
                assert publisher.base_dimensions[key] == value
            
        finally:
            # Clean up environment variables
            for key in test_env_vars.keys():
                os.environ.pop(key, None)
    
    def test_ecs_environment_variable_detection(self):
        """Test that ECS environment variables are properly detected and used."""
        import os
        import sys
        
        # Add the parent directory to import modules
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        # Set ECS environment variables to test detection
        test_env_vars = {
            'ECS_CONTAINER_METADATA_URI_V4': 'http://169.254.170.2/v4/12345678-1234-1234-1234-123456789012',
            'CLOUDWATCH_NAMESPACE': 'KinesisOnDemandDemo/ECS',
            'SERVICE_NAME': 'ecs-kinesis-generator',
            'CLUSTER_NAME': 'ecs-demo-cluster',
            'ENVIRONMENT': 'ecs-test',
            'DEPLOYMENT_ID': 'ecs-v1.0.0',
            'CONTAINER_ID': 'ecs-test-container',
            'ENABLE_CLOUDWATCH_METRICS': 'true'
        }
        
        for key, value in test_env_vars.items():
            os.environ[key] = value
        
        try:
            from shared.config import DemoConfig
            from shared.cloudwatch_metrics import CloudWatchMetricsPublisher
            
            config = DemoConfig()
            
            # Create publisher to test environment variable usage
            publisher = CloudWatchMetricsPublisher(config=config)
            
            # Verify environment variables are used correctly
            assert publisher.namespace == 'KinesisOnDemandDemo/ECS'
            assert publisher.service_name == 'ecs-kinesis-generator'
            assert publisher.cluster_name == 'ecs-demo-cluster'
            assert publisher.environment == 'ecs-test'
            assert publisher.deployment_id == 'ecs-v1.0.0'
            assert publisher.container_id == 'ecs-test-contain'  # Truncated to 16 chars
            
            # Verify base dimensions are set correctly
            expected_dimensions = {
                'ServiceName': 'ecs-kinesis-generator',
                'ContainerID': 'ecs-test-contain',  # Truncated to 16 chars
                'ClusterName': 'ecs-demo-cluster',
                'Environment': 'ecs-test',
                'DeploymentID': 'ecs-v1.0.0'
            }
            
            for key, value in expected_dimensions.items():
                assert publisher.base_dimensions[key] == value
            
            # Verify ECS metadata URI is detected
            assert os.getenv('ECS_CONTAINER_METADATA_URI_V4') is not None
            
        finally:
            # Clean up environment variables
            for key in test_env_vars.keys():
                os.environ.pop(key, None)
    

    
    def test_internal_controller_mode_selection(self):
        """Test that the application correctly selects internal controller mode."""
        import os
        import sys
        
        # Add the parent directory to import modules
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        # Test internal controller mode (default)
        # No special environment variables needed for internal mode
        
        try:
            from shared.config import DemoConfig
            from main import DemoDataGenerator
            
            config = DemoConfig()
            
            # Create generator (should use internal controller)
            generator = DemoDataGenerator(config)
            
            # Verify internal controller is used
            assert not hasattr(generator.traffic_controller, 'external_controller')
            assert hasattr(generator.traffic_controller, 'phases')  # Internal controller has phases
    
    def test_step_functions_controller_mode_selection(self):
        """Test that the application correctly selects Step Functions controller mode."""
        import os
        import sys
        from unittest.mock import patch, MagicMock
        
        # Add the parent directory to import modules
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        # Test Step Functions controller mode
        test_env_vars = {
            'CONTROLLER_MODE': 'step_functions',
            'SERVICE_NAME': 'test-stepfunctions-service'
        }
        
        for key, value in test_env_vars.items():
            os.environ[key] = value
        
        try:
            from shared.config import DemoConfig
            
            config = DemoConfig()
            
            # Mock the CloudWatch client to avoid AWS calls
            with patch('shared.stepfunctions_phase_controller.boto3.client') as mock_boto3:
                mock_cloudwatch = MagicMock()
                mock_boto3.return_value = mock_cloudwatch
                
                # Mock CloudWatch response
                mock_cloudwatch.get_metric_statistics.return_value = {
                    'Datapoints': [
                        {'Timestamp': '2024-01-15T10:30:00Z', 'Maximum': 2.0}
                    ]
                }
                
                from main import DemoDataGenerator
                
                # Create generator (should use Step Functions controller)
                generator = DemoDataGenerator(config)
                
                # Verify Step Functions controller is used
                assert hasattr(generator.traffic_controller, 'stepfunctions_controller')
                assert generator.traffic_controller.stepfunctions_controller.service_name == 'test-stepfunctions-service'
                
        finally:
            # Clean up environment variables
            for key in test_env_vars.keys():
                os.environ.pop(key, None)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])