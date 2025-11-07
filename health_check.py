#!/usr/bin/env python3
"""
Health check endpoint for the containerized data generator.

This script provides health status information for container orchestration
platforms like ECS, Kubernetes, or Docker Compose.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any

# Configure minimal logging for health checks
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class HealthChecker:
    """Provides health check functionality for the data generator container."""
    
    def __init__(self):
        """Initialize the health checker."""
        self.start_time = datetime.utcnow()
    
    def check_python_environment(self) -> Dict[str, Any]:
        """Check Python environment health."""
        try:
            import sys
            import asyncio
            import boto3
            
            return {
                'status': 'healthy',
                'python_version': sys.version,
                'asyncio_available': True,
                'boto3_available': True
            }
        except ImportError as e:
            return {
                'status': 'unhealthy',
                'error': f'Missing required dependency: {e}'
            }
    
    def check_aws_credentials(self) -> Dict[str, Any]:
        """Check AWS credentials availability (without making API calls)."""
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError, PartialCredentialsError
            
            # Try to create a session to check credentials
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials is None:
                return {
                    'status': 'warning',
                    'message': 'No AWS credentials found'
                }
            
            # Check if credentials are frozen (temporary credentials)
            if credentials.token:
                return {
                    'status': 'healthy',
                    'credential_type': 'temporary',
                    'access_key_id': credentials.access_key[:8] + '...' if credentials.access_key else None
                }
            else:
                return {
                    'status': 'healthy',
                    'credential_type': 'permanent',
                    'access_key_id': credentials.access_key[:8] + '...' if credentials.access_key else None
                }
                
        except (NoCredentialsError, PartialCredentialsError):
            return {
                'status': 'warning',
                'message': 'Invalid or incomplete AWS credentials'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_environment_variables(self) -> Dict[str, Any]:
        """Check required environment variables."""
        import os
        
        required_vars = [
            'AWS_REGION',
            'STREAM_NAME'
        ]
        
        optional_vars = [
            'PER_TASK_CAPACITY'
        ]
        
        # Container-specific metrics variables
        metrics_vars = [
            'CLOUDWATCH_NAMESPACE',
            'SERVICE_NAME',
            'CLUSTER_NAME',
            'ENVIRONMENT',
            'DEPLOYMENT_ID',
            'CONTAINER_ID',
            'METRICS_PUBLISH_INTERVAL',
            'ENABLE_CLOUDWATCH_METRICS'
        ]
        
        missing_required = []
        present_optional = []
        present_metrics = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_required.append(var)
        
        for var in optional_vars:
            if os.getenv(var):
                present_optional.append(var)
        
        for var in metrics_vars:
            if os.getenv(var):
                present_metrics.append(var)
        
        if missing_required:
            return {
                'status': 'unhealthy',
                'missing_required': missing_required,
                'present_optional': present_optional,
                'present_metrics': present_metrics
            }
        
        return {
            'status': 'healthy',
            'present_optional': present_optional,
            'present_metrics': present_metrics,
            'aws_region': os.getenv('AWS_REGION'),
            'stream_name': os.getenv('STREAM_NAME'),
            'container_metrics_config': {
                'namespace': os.getenv('CLOUDWATCH_NAMESPACE'),
                'service_name': os.getenv('SERVICE_NAME'),
                'cluster_name': os.getenv('CLUSTER_NAME'),
                'environment': os.getenv('ENVIRONMENT'),
                'deployment_id': os.getenv('DEPLOYMENT_ID'),
                'container_id': os.getenv('CONTAINER_ID'),
                'metrics_enabled': os.getenv('ENABLE_CLOUDWATCH_METRICS', 'true').lower() == 'true'
            }
        }
    
    def check_shared_modules(self) -> Dict[str, Any]:
        """Check if shared modules can be imported."""
        try:
            from shared.config import DemoConfig
            from shared.post_generator import SocialMediaPostGenerator, TrafficPatternController
            from shared.kinesis_producer import KinesisProducer
            from shared.models import SocialMediaPost, PostType
            
            # Try to create a basic config to test module functionality
            config = DemoConfig()
            
            return {
                'status': 'healthy',
                'modules_loaded': [
                    'shared.config',
                    'shared.post_generator',
                    'shared.kinesis_producer',
                    'shared.models'
                ],
                'config_test': 'passed'
            }
        except ImportError as e:
            return {
                'status': 'unhealthy',
                'error': f'Failed to import shared modules: {e}'
            }
        except Exception as e:
            return {
                'status': 'warning',
                'error': f'Shared modules imported but configuration failed: {e}'
            }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        import os
        import platform
        import psutil
        
        try:
            return {
                'hostname': platform.node(),
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu_count': os.cpu_count(),
                'memory_total_mb': round(psutil.virtual_memory().total / 1024 / 1024),
                'memory_available_mb': round(psutil.virtual_memory().available / 1024 / 1024),
                'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds()
            }
        except ImportError:
            # psutil not available, provide basic info
            return {
                'hostname': platform.node(),
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu_count': os.cpu_count(),
                'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds()
            }
    
    def perform_full_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_status = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }
        
        # Run all health checks
        checks = {
            'python_environment': self.check_python_environment,
            'aws_credentials': self.check_aws_credentials,
            'environment_variables': self.check_environment_variables,
            'shared_modules': self.check_shared_modules
        }
        
        unhealthy_count = 0
        warning_count = 0
        
        for check_name, check_func in checks.items():
            try:
                result = check_func()
                health_status['checks'][check_name] = result
                
                if result['status'] == 'unhealthy':
                    unhealthy_count += 1
                elif result['status'] in ['warning', 'error']:
                    warning_count += 1
                    
            except Exception as e:
                health_status['checks'][check_name] = {
                    'status': 'error',
                    'error': str(e)
                }
                unhealthy_count += 1
        
        # Add system info
        try:
            health_status['system_info'] = self.get_system_info()
        except Exception as e:
            health_status['system_info'] = {'error': str(e)}
        
        # Determine overall status
        if unhealthy_count > 0:
            health_status['overall_status'] = 'unhealthy'
        elif warning_count > 0:
            health_status['overall_status'] = 'warning'
        
        return health_status


def main():
    """Main entry point for health check script."""
    checker = HealthChecker()
    
    try:
        health_result = checker.perform_full_health_check()
        
        # Output JSON for container orchestration
        print(json.dumps(health_result, indent=2))
        
        # Exit with appropriate code
        if health_result['overall_status'] == 'unhealthy':
            sys.exit(1)
        elif health_result['overall_status'] == 'warning':
            sys.exit(0)  # Warnings are still considered healthy for containers
        else:
            sys.exit(0)
            
    except Exception as e:
        error_result = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'error',
            'error': str(e)
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()