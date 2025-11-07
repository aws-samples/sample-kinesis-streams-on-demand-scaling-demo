#!/usr/bin/env python3
"""
Step Functions Demo Controller

This Lambda function is designed to work with AWS Step Functions for the
Kinesis On-Demand Demo. It handles individual operations called by the
Step Functions state machine, with state managed by Step Functions itself.

Key Benefits over previous approaches:
- No Parameter Store needed (Step Functions manages state)
- No CloudWatch Events scheduling needed (Step Functions has Wait states)
- Built-in retry and error handling
- Visual workflow tracking
- Simpler Lambda functions (single responsibility)

IMPORTANT: Phase configuration comes from Step Functions state machine JSON,
NOT from hardcoded values in this Python file. Step Functions is the single
source of truth for phase TPS, duration, and timing.
"""

import json
import logging
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
ecs_client = boto3.client('ecs')
cloudwatch_client = boto3.client('cloudwatch')


class StepFunctionsDemoController:
    """Demo controller designed to work with Step Functions state machine."""
    
    def __init__(self, cluster_name: str, service_name: str):
        self.cluster_name = cluster_name
        self.service_name = service_name
        
        # Per-task capacity limit (safety mechanism)
        import os
        self.per_task_capacity = int(os.getenv('PER_TASK_CAPACITY', '3500'))
        
    def initialize_demo(self, demo_config: Dict) -> Dict:
        """Initialize the demo and return initial state."""
        import os
        logger.info("Initializing Kinesis On-Demand Demo")
        
        demo_start_time = datetime.utcnow()
        
        # Create demo state that will be passed through Step Functions
        phases = demo_config.get("phases", [])
        demo_state = {
            "demo_id": f"demo-{int(time.time())}",
            "start_time": demo_start_time.isoformat(),
            "cluster_name": self.cluster_name,
            "service_name": self.service_name,
            "phases": phases,
            "current_phase": 0,
            "per_task_capacity": self.per_task_capacity
        }
        
        # Log the phase configuration from Step Functions
        logger.info("Phase configuration from Step Functions:")
        for phase in phases:
            phase_num = phase.get("phase_number")
            target_tps = phase.get("target_tps")
            duration = phase.get("duration_seconds")
            task_count = max(1, math.ceil(target_tps / self.per_task_capacity))
            logger.info(f"  Phase {phase_num}: {target_tps:,} TPS, {duration}s, {task_count} tasks")
        
        # Publish initial metrics
        self._publish_demo_metrics("DemoInitialized", 1, demo_state)
        
        logger.info(f"Demo initialized with ID: {demo_state['demo_id']}")
        logger.info(f"Total phases: {len(demo_state['phases'])}")
        
        return {
            "status": "initialized",
            "demo_state": demo_state,
            "timestamp": demo_start_time.isoformat()
        }
    
    def start_phase(self, phase_number: int, demo_state: Dict) -> Dict:
        """Start a specific demo phase by redeploying workers with phase environment variable."""
        logger.info(f"Starting Phase {phase_number}")
        
        # Get phase configuration from Step Functions state (single source of truth)
        phases = demo_state.get("phases", [])
        phase_config = None
        
        for phase in phases:
            if phase.get("phase_number") == phase_number:
                phase_config = phase
                break
        
        if not phase_config:
            raise ValueError(f"Phase {phase_number} not found in demo configuration")
        
        # Extract configuration from Step Functions
        total_target_tps = phase_config["target_tps"]
        duration_seconds = phase_config["duration_seconds"]
        
        # Calculate required task count based on per-task capacity
        task_count = max(1, math.ceil(total_target_tps / self.per_task_capacity))
        
        logger.info(f"Phase {phase_number} - Target TPS: {total_target_tps}, "
                   f"Duration: {duration_seconds}s, Task Count: {task_count}, "
                   f"Per-task TPS: {total_target_tps // task_count}")
        
        # Redeploy ECS service with new phase environment variable
        deployment_result = self._redeploy_ecs_service_with_phase(phase_number, task_count, total_target_tps)
        
        # Update demo state
        demo_state["current_phase"] = phase_number
        demo_state["current_target_tps"] = total_target_tps
        demo_state["current_task_count"] = task_count
        demo_state["current_duration"] = duration_seconds
        demo_state[f"phase_{phase_number}_start_time"] = datetime.utcnow().isoformat()
        
        # Publish phase transition metrics
        self._publish_demo_metrics("PhaseTransition", phase_number, demo_state)
        self._publish_demo_metrics("TargetTPS", total_target_tps, demo_state)
        self._publish_demo_metrics("TaskCount", task_count, demo_state)
        
        result = {
            "status": "phase_started",
            "phase_number": phase_number,
            "target_tps": total_target_tps,
            "duration_seconds": duration_seconds,
            "task_count": task_count,
            "per_task_tps": total_target_tps // task_count,
            "deployment_result": deployment_result,
            "demo_state": demo_state,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Phase {phase_number} started successfully")
        return result
    
    def cleanup_demo(self, demo_state: Dict) -> Dict:
        """Clean up demo resources."""
        logger.info("Cleaning up Kinesis On-Demand Demo")
        
        # Scale ECS service to 0 tasks
        cleanup_result = self._cleanup_ecs_service()
        
        # Update demo state
        demo_state["end_time"] = datetime.utcnow().isoformat()
        demo_state["status"] = "completed"
        
        # Publish completion metrics
        self._publish_demo_metrics("DemoCompleted", 1, demo_state)
        
        # Calculate total demo duration
        start_time = datetime.fromisoformat(demo_state["start_time"])
        end_time = datetime.utcnow()
        duration_seconds = (end_time - start_time).total_seconds()
        
        self._publish_demo_metrics("DemoDurationSeconds", duration_seconds, demo_state)
        
        result = {
            "status": "cleanup_completed",
            "cleanup_result": cleanup_result,
            "demo_duration_seconds": duration_seconds,
            "demo_state": demo_state,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Demo cleanup completed. Duration: {duration_seconds:.1f} seconds")
        return result
    
    def handle_failure(self, error: Dict, demo_state: Dict) -> Dict:
        """Handle demo failure and cleanup."""
        logger.error(f"Handling demo failure: {error}")
        
        try:
            # Attempt to cleanup ECS service
            cleanup_result = self._cleanup_ecs_service()
            
            # Update demo state
            demo_state["end_time"] = datetime.utcnow().isoformat()
            demo_state["status"] = "failed"
            demo_state["error"] = error
            
            # Publish failure metrics
            self._publish_demo_metrics("DemoFailed", 1, demo_state)
            
            result = {
                "status": "failure_handled",
                "cleanup_result": cleanup_result,
                "error": error,
                "demo_state": demo_state,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info("Demo failure handled and resources cleaned up")
            return result
            
        except Exception as cleanup_error:
            logger.error(f"Error during failure cleanup: {cleanup_error}")
            return {
                "status": "cleanup_failed",
                "original_error": error,
                "cleanup_error": str(cleanup_error),
                "demo_state": demo_state,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_demo_status(self, execution_arn: str = None) -> Dict:
        """Get current demo status from Step Functions execution."""
        try:
            if execution_arn:
                # Get status from Step Functions execution
                stepfunctions_client = boto3.client('stepfunctions')
                execution = stepfunctions_client.describe_execution(executionArn=execution_arn)
                
                return {
                    "execution_arn": execution_arn,
                    "status": execution["status"],
                    "start_date": execution["startDate"].isoformat(),
                    "state_machine_arn": execution["stateMachineArn"],
                    "input": json.loads(execution.get("input", "{}")),
                    "output": json.loads(execution.get("output", "{}")) if execution.get("output") else None
                }
            else:
                return {
                    "status": "no_execution_specified",
                    "message": "Provide execution ARN to get specific demo status"
                }
                
        except Exception as e:
            logger.error(f"Error getting demo status: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _redeploy_ecs_service_with_phase(self, phase_number: int, task_count: int, total_target_tps: int) -> Dict:
        """Redeploy ECS service with new phase environment variable and task count."""
        try:
            logger.info(f"Redeploying ECS service {self.service_name} for phase {phase_number} with {task_count} tasks")
            
            # Get current task definition
            current_service = ecs_client.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )['services'][0]
            
            current_task_def_arn = current_service['taskDefinition']
            
            # Get current task definition details
            task_def_response = ecs_client.describe_task_definition(
                taskDefinition=current_task_def_arn
            )
            
            current_task_def = task_def_response['taskDefinition']
            
            # Create new task definition with updated environment variables
            new_task_def = self._create_updated_task_definition(current_task_def, phase_number, total_target_tps, task_count)
            
            # Register new task definition
            new_task_def_response = ecs_client.register_task_definition(**new_task_def)
            new_task_def_arn = new_task_def_response['taskDefinition']['taskDefinitionArn']
            
            logger.info(f"Registered new task definition: {new_task_def_arn}")
            
            # Update service with new task definition and desired count
            response = ecs_client.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                taskDefinition=new_task_def_arn,
                desiredCount=task_count,
                forceNewDeployment=True  # Force redeployment even if task def is the same
            )
            
            deployment_id = response['service']['deployments'][0]['id']
            
            logger.info(f"ECS service redeployment initiated successfully. Deployment ID: {deployment_id}")
            
            return {
                "success": True,
                "phase_number": phase_number,
                "task_count": task_count,
                "new_task_definition_arn": new_task_def_arn,
                "deployment_id": deployment_id,
                "service_arn": response['service']['serviceArn']
            }
            
        except ClientError as e:
            logger.error(f"Failed to redeploy ECS service: {e}")
            return {
                "success": False,
                "error": str(e),
                "phase_number": phase_number,
                "task_count": task_count
            }
    
    def _create_updated_task_definition(self, current_task_def: Dict, phase_number: int, target_tps: int, task_count: int) -> Dict:
        """Create updated task definition with new phase environment variable."""
        # Remove read-only fields
        new_task_def = {
            'family': current_task_def['family'],
            'taskRoleArn': current_task_def.get('taskRoleArn'),
            'executionRoleArn': current_task_def.get('executionRoleArn'),
            'networkMode': current_task_def.get('networkMode'),
            'requiresCompatibilities': current_task_def.get('requiresCompatibilities', []),
            'cpu': current_task_def.get('cpu'),
            'memory': current_task_def.get('memory'),
            'containerDefinitions': []
        }
        
        # Remove None values
        new_task_def = {k: v for k, v in new_task_def.items() if v is not None}
        
        # Calculate per-task TPS
        per_task_tps = max(1, target_tps // task_count)
        
        # Update container definitions with new environment variables
        for container in current_task_def['containerDefinitions']:
            new_container = container.copy()
            
            # Update environment variables
            environment = new_container.get('environment', [])
            
            # Remove existing DEMO_PHASE and TARGET_TPS if they exist
            environment = [env for env in environment if env['name'] not in ['DEMO_PHASE', 'TARGET_TPS']]
            
            # Add new environment variables
            environment.append({
                'name': 'DEMO_PHASE',
                'value': str(phase_number)
            })
            
            environment.append({
                'name': 'TARGET_TPS',
                'value': str(per_task_tps)
            })
            
            new_container['environment'] = environment
            new_task_def['containerDefinitions'].append(new_container)
        
        return new_task_def
    
    def _cleanup_ecs_service(self) -> Dict:
        """Scale ECS service to 0 tasks for cleanup."""
        try:
            logger.info(f"Scaling down ECS service {self.service_name} to 0 tasks")
            
            response = ecs_client.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                desiredCount=0
            )
            
            logger.info(f"ECS service scaled down successfully")
            return {
                "success": True,
                "desired_count": 0,
                "service_arn": response['service']['serviceArn']
            }
            
        except ClientError as e:
            logger.error(f"Failed to scale down ECS service: {e}")
            return {
                "success": False,
                "error": str(e),
                "desired_count": 0
            }
    
    def _publish_demo_metrics(self, metric_name: str, value: float, demo_state: Dict) -> None:
        """Publish demo metrics to CloudWatch."""
        try:
            cloudwatch_client.put_metric_data(
                Namespace='KinesisOnDemandDemo/StepFunctions',
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'DemoId', 'Value': demo_state.get('demo_id', 'unknown')},
                            {'Name': 'ClusterName', 'Value': self.cluster_name},
                            {'Name': 'ServiceName', 'Value': self.service_name}
                        ]
                    }
                ]
            )
            
        except Exception as e:
            logger.error(f"Failed to publish metric {metric_name}: {e}")
    



def lambda_handler(event, context):
    """
    Lambda handler for Step Functions demo controller operations.
    
    This function is called by Step Functions state machine for each operation.
    State is managed by Step Functions, not by this Lambda function.
    
    Supported operations:
    - initialize_demo: Initialize demo and return initial state
    - start_phase: Start a specific demo phase
    - cleanup_demo: Clean up demo resources
    - handle_failure: Handle demo failure
    - get_status: Get demo status (when called directly)
    """
    
    logger.info(f"Lambda handler called with event: {json.dumps(event, default=str)}")
    
    # Get configuration from environment variables
    import os
    cluster_name = os.getenv('CLUSTER_NAME', 'kinesis-demo-cluster')
    service_name = os.getenv('SERVICE_NAME', 'kinesis-ondemand-demo-service')
    
    controller = StepFunctionsDemoController(cluster_name, service_name)
    
    # Get operation from event
    operation = event.get('operation')
    logger.info(f"Processing operation: {operation}")
    
    try:
        if operation == 'initialize_demo':
            demo_config = event.get('demo_config', {})
            result = controller.initialize_demo(demo_config)
            
        elif operation == 'start_phase':
            phase_number = event.get('phase_number')
            demo_state = event.get('demo_state', {})
            
            if not phase_number:
                raise ValueError("Missing phase_number")
            
            # Handle nested demo_state from Step Functions
            if 'demo_state' in demo_state:
                demo_state = demo_state['demo_state']
                
            result = controller.start_phase(phase_number, demo_state)
            
        elif operation == 'cleanup_demo':
            demo_state = event.get('demo_state', {})
            
            # Handle nested demo_state from Step Functions
            if 'demo_state' in demo_state:
                demo_state = demo_state['demo_state']
                
            result = controller.cleanup_demo(demo_state)
            
        elif operation == 'handle_failure':
            error = event.get('error', {})
            demo_state = event.get('demo_state', {})
            
            # Handle nested demo_state from Step Functions
            if 'demo_state' in demo_state:
                demo_state = demo_state['demo_state']
                
            result = controller.handle_failure(error, demo_state)
            
        elif operation == 'get_status':
            execution_arn = event.get('execution_arn')
            result = controller.get_demo_status(execution_arn)
            
        else:
            result = {"error": f"Unknown operation: {operation}"}
            
        return result
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        return {
            'errorType': type(e).__name__,
            'errorMessage': str(e),
            'operation': operation,
            'event': event
        }


if __name__ == "__main__":
    # For local testing
    import os
    os.environ['CLUSTER_NAME'] = 'kinesis-demo-cluster'
    os.environ['SERVICE_NAME'] = 'kinesis-ondemand-demo-service'
    
    # Test initialize demo (matching state machine configuration)
    event = {
        'operation': 'initialize_demo',
        'demo_config': {
            'phases': [
                {'phase_number': 1, 'target_tps': 1000, 'duration_seconds': 120},
                {'phase_number': 2, 'target_tps': 100000, 'duration_seconds': 1200},
                {'phase_number': 3, 'target_tps': 500000, 'duration_seconds': 1200},
                {'phase_number': 4, 'target_tps': 1000, 'duration_seconds': 120}
            ]
        }
    }
    context = {}
    
    result = lambda_handler(event, context)
    print(json.dumps(result, indent=2))