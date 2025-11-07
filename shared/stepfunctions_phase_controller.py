"""
Step Functions Phase Controller Client

This module allows containers to get their current phase and target TPS
from CloudWatch metrics published by the Step Functions controller,
making them stateless workers without needing Parameter Store.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StepFunctionsPhaseController:
    """
    Client for getting phase information from Step Functions controller via CloudWatch metrics.
    
    This replaces Parameter Store with CloudWatch metrics for simpler architecture
    and better integration with Step Functions workflow.
    """
    
    def __init__(self, service_name: str = None, cache_ttl_seconds: int = 10):
        """
        Initialize the Step Functions phase controller client.
        
        Args:
            service_name: ECS service name for metrics filtering
            cache_ttl_seconds: How long to cache metric values
        """
        import os
        self.service_name = service_name or os.getenv('SERVICE_NAME', 'kinesis-ondemand-demo-service')
        self.cache_ttl_seconds = cache_ttl_seconds
        
        # AWS client
        self.cloudwatch_client = boto3.client('cloudwatch')
        
        # Cache for metric values
        self._cache = {}
        self._cache_timestamps = {}
        
        logger.info(f"StepFunctionsPhaseController initialized for service: {self.service_name}")
    
    def get_current_phase_number(self) -> int:
        """Get the current demo phase number from CloudWatch metrics."""
        try:
            phase_metric = self._get_latest_metric('KinesisOnDemandDemo/PhaseInfo', 'CurrentPhase')
            if phase_metric:
                return int(phase_metric)
            else:
                logger.warning("No current phase metric found, defaulting to 1")
                return 1
        except (ValueError, TypeError):
            logger.warning("Invalid phase number from CloudWatch metrics, defaulting to 1")
            return 1
    
    def get_target_tps(self) -> int:
        """Get the target TPS for the current phase from CloudWatch metrics."""
        try:
            tps_metric = self._get_latest_metric('KinesisOnDemandDemo/PhaseInfo', 'TargetTPS')
            if tps_metric:
                return int(tps_metric)
            else:
                logger.warning("No target TPS metric found, defaulting to 100")
                return 100
        except (ValueError, TypeError):
            logger.warning("Invalid target TPS from CloudWatch metrics, defaulting to 100")
            return 100
    
    def get_current_phase_info(self) -> Dict:
        """Get complete current phase information from CloudWatch metrics."""
        phase_number = self.get_current_phase_number()
        target_tps = self.get_target_tps()
        
        return {
            'phase_number': phase_number,
            'target_tps': target_tps,
            'duration_seconds': 120,  # Fixed duration for all phases
            'source': 'step_functions_cloudwatch'
        }
    
    def is_demo_running(self) -> bool:
        """Check if the demo is currently running by looking for recent metrics."""
        try:
            # Check if we have recent phase metrics (within last 5 minutes)
            phase_metric = self._get_latest_metric('KinesisOnDemandDemo/PhaseInfo', 'CurrentPhase', max_age_minutes=5)
            return phase_metric is not None
        except Exception as e:
            logger.error(f"Error checking if demo is running: {e}")
            return False
    
    def get_demo_progress(self) -> float:
        """Get demo progress (estimated based on current phase)."""
        phase_number = self.get_current_phase_number()
        
        # Estimate progress based on phase (each phase is 25% of demo)
        progress_map = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}
        return progress_map.get(phase_number, 0.0)
    
    def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
        """Calculate number of messages to generate in the given time window."""
        target_tps = self.get_target_tps()
        return int(target_tps * time_window_seconds)
    
    def get_post_type_distribution(self) -> Tuple[float, float, float]:
        """Get distribution of post types for current phase (original, share, reply)."""
        phase_number = self.get_current_phase_number()
        
        if phase_number <= 2:
            # Early phases: mostly original content
            return (0.7, 0.2, 0.1)
        else:
            # Viral phases: more shares and replies
            return (0.4, 0.4, 0.2)
    
    def wait_for_demo_start(self, timeout_seconds: int = 300, 
                           check_interval_seconds: int = 10) -> bool:
        """
        Wait for the demo to start (blocking).
        
        Args:
            timeout_seconds: Maximum time to wait
            check_interval_seconds: How often to check
            
        Returns:
            True if demo started, False if timeout
        """
        start_time = time.time()
        
        logger.info("Waiting for Step Functions demo to start...")
        
        while time.time() - start_time < timeout_seconds:
            if self.is_demo_running():
                logger.info("Step Functions demo has started!")
                return True
            
            logger.info(f"Demo not started yet, checking again in {check_interval_seconds}s...")
            time.sleep(check_interval_seconds)
        
        logger.warning(f"Timeout waiting for demo to start after {timeout_seconds}s")
        return False
    
    def _get_latest_metric(self, namespace: str, metric_name: str, max_age_minutes: int = 10) -> Optional[float]:
        """
        Get the latest value for a CloudWatch metric.
        
        Args:
            namespace: CloudWatch namespace
            metric_name: Metric name
            max_age_minutes: Maximum age of metric data to consider
            
        Returns:
            Latest metric value or None if not found
        """
        cache_key = f"{namespace}:{metric_name}"
        
        # Check cache first
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=max_age_minutes)
            
            response = self.cloudwatch_client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[
                    {
                        'Name': 'ServiceName',
                        'Value': self.service_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,  # 1 minute periods
                Statistics=['Maximum']  # Use Maximum to get the latest value
            )
            
            datapoints = response.get('Datapoints', [])
            if datapoints:
                # Sort by timestamp and get the latest value
                latest_datapoint = sorted(datapoints, key=lambda x: x['Timestamp'])[-1]
                value = latest_datapoint['Maximum']
                
                # Update cache
                self._cache[cache_key] = value
                self._cache_timestamps[cache_key] = time.time()
                
                logger.debug(f"Retrieved metric {metric_name}: {value}")
                return value
            else:
                logger.debug(f"No datapoints found for metric {metric_name}")
                return None
                
        except ClientError as e:
            logger.error(f"Error getting CloudWatch metric {metric_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting metric {metric_name}: {e}")
            return None
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached metric value is still valid."""
        if cache_key not in self._cache:
            return False
        
        if cache_key not in self._cache_timestamps:
            return False
        
        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.cache_ttl_seconds
    
    def clear_cache(self) -> None:
        """Clear the metric cache."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.debug("Metric cache cleared")


# Compatibility interface to match the original TrafficPatternController
class StepFunctionsTrafficPatternController:
    """
    Compatibility wrapper that provides the same interface as TrafficPatternController
    but gets data from Step Functions controller via CloudWatch metrics.
    """
    
    def __init__(self, config, service_name: str = None):
        """Initialize with config for compatibility."""
        self.config = config
        self.stepfunctions_controller = StepFunctionsPhaseController(service_name)
        self.demo_start_time: Optional[datetime] = None
        
        logger.info("StepFunctionsTrafficPatternController initialized (Step Functions mode)")
    
    def start_demo(self) -> None:
        """
        Wait for Step Functions to start the demo.
        This is a compatibility method - the actual demo start is controlled by Step Functions.
        """
        logger.info("Waiting for Step Functions to start demo...")
        
        if self.stepfunctions_controller.wait_for_demo_start():
            self.demo_start_time = datetime.utcnow()
            logger.info("Demo started by Step Functions")
        else:
            logger.error("Timeout waiting for Step Functions to start demo")
            raise RuntimeError("Demo start timeout")
    
    def get_current_phase(self):
        """Get current phase information from Step Functions controller."""
        phase_info = self.stepfunctions_controller.get_current_phase_info()
        
        # Create a simple phase object for compatibility
        class Phase:
            def __init__(self, info):
                self.phase_number = info.get('phase_number', 1)
                self.target_tps = info.get('target_tps', 100)
                self.duration_seconds = info.get('duration_seconds', 120)
        
        return Phase(phase_info)
    
    def get_target_tps(self) -> int:
        """Get target TPS from Step Functions controller."""
        return self.stepfunctions_controller.get_target_tps()
    
    def get_demo_progress(self) -> float:
        """Get demo progress from Step Functions controller."""
        return self.stepfunctions_controller.get_demo_progress()
    
    def get_phase_progress(self) -> float:
        """Get phase progress (estimated based on current phase)."""
        return 0.5  # Step Functions doesn't track phase progress, return midpoint
    
    def is_demo_complete(self) -> bool:
        """Check if demo is complete based on current phase."""
        phase_number = self.stepfunctions_controller.get_current_phase_number()
        # Demo is complete if we're past phase 4 or no recent metrics
        return phase_number > 4 or not self.stepfunctions_controller.is_demo_running()
    
    def get_remaining_time(self) -> int:
        """Get remaining time (estimated based on current phase)."""
        return 60  # Step Functions doesn't track remaining time, return estimate
    
    def calculate_messages_to_generate(self, time_window_seconds: float = 1.0) -> int:
        """Calculate messages to generate from Step Functions controller."""
        return self.stepfunctions_controller.calculate_messages_to_generate(time_window_seconds)
    
    def get_post_type_distribution(self) -> Tuple[float, float, float]:
        """Get post type distribution from Step Functions controller."""
        return self.stepfunctions_controller.get_post_type_distribution()