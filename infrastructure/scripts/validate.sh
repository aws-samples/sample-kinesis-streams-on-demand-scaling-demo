#!/bin/bash
set -e

# Infrastructure Validation Script for Kinesis On-Demand Demo
# This script validates that the deployed infrastructure is working correctly

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
STACK_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Validate Kinesis On-Demand Demo Infrastructure

Options:
    -r, --region REGION         AWS region (default: us-east-1)
    -e, --environment ENV       Environment name (default: production)
    --quick                     Run quick validation only
    --full                      Run full validation including demo test
    -h, --help                  Show this help message

Environment Variables:
    AWS_REGION                  AWS region
    ENVIRONMENT                 Environment name

Examples:
    # Quick validation
    $0 --environment production --quick

    # Full validation with demo test
    $0 --environment production --full

EOF
}

# Function to validate stack exists and is healthy
validate_stack() {
    log_info "Validating CloudFormation stack: $STACK_NAME"
    
    local stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "STACK_NOT_FOUND")
    
    if [[ "$stack_status" == "CREATE_COMPLETE" ]] || [[ "$stack_status" == "UPDATE_COMPLETE" ]]; then
        log_success "Stack is healthy: $stack_status"
        return 0
    else
        log_error "Stack is in unexpected state: $stack_status"
        return 1
    fi
}

# Function to get stack outputs
get_stack_outputs() {
    log_info "Retrieving stack outputs..."
    
    # Get all outputs as JSON
    local outputs=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs' \
        --output json 2>/dev/null || echo "[]")
    
    # Extract specific outputs
    KINESIS_STREAM_NAME=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="KinesisStreamName") | .OutputValue' 2>/dev/null || echo "")
    ECS_CLUSTER_NAME=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="EcsClusterName") | .OutputValue' 2>/dev/null || echo "")
    ECS_SERVICE_NAME=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="EcsServiceName") | .OutputValue' 2>/dev/null || echo "")
    STATE_MACHINE_ARN=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="StateMachineArn") | .OutputValue' 2>/dev/null || echo "")
    API_ENDPOINT=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="ApiEndpoint") | .OutputValue' 2>/dev/null || echo "")
    DASHBOARD_URL=$(echo "$outputs" | jq -r '.[] | select(.OutputKey=="DashboardUrl") | .OutputValue' 2>/dev/null || echo "")
    
    log_info "Stack outputs retrieved successfully"
}

# Function to validate Kinesis stream
validate_kinesis_stream() {
    log_info "Validating Kinesis stream: $KINESIS_STREAM_NAME"
    
    if [[ -z "$KINESIS_STREAM_NAME" ]]; then
        log_error "Kinesis stream name not found in stack outputs"
        return 1
    fi
    
    local stream_status=$(aws kinesis describe-stream \
        --stream-name "$KINESIS_STREAM_NAME" \
        --region "$AWS_REGION" \
        --query 'StreamDescription.StreamStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$stream_status" == "ACTIVE" ]]; then
        log_success "Kinesis stream is active"
        
        # Check stream mode
        local stream_mode=$(aws kinesis describe-stream \
            --stream-name "$KINESIS_STREAM_NAME" \
            --region "$AWS_REGION" \
            --query 'StreamDescription.StreamModeDetails.StreamMode' \
            --output text 2>/dev/null || echo "UNKNOWN")
        
        if [[ "$stream_mode" == "ON_DEMAND" ]]; then
            log_success "Stream is in On-Demand mode"
        else
            log_warning "Stream is not in On-Demand mode: $stream_mode"
        fi
        
        return 0
    else
        log_error "Kinesis stream is not active: $stream_status"
        return 1
    fi
}

# Function to validate ECS resources
validate_ecs_resources() {
    log_info "Validating ECS resources..."
    
    if [[ -z "$ECS_CLUSTER_NAME" ]] || [[ -z "$ECS_SERVICE_NAME" ]]; then
        log_error "ECS cluster or service name not found in stack outputs"
        return 1
    fi
    
    # Check cluster status
    local cluster_status=$(aws ecs describe-clusters \
        --clusters "$ECS_CLUSTER_NAME" \
        --region "$AWS_REGION" \
        --query 'clusters[0].status' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$cluster_status" == "ACTIVE" ]]; then
        log_success "ECS cluster is active"
    else
        log_error "ECS cluster is not active: $cluster_status"
        return 1
    fi
    
    # Check service status
    local service_status=$(aws ecs describe-services \
        --cluster "$ECS_CLUSTER_NAME" \
        --services "$ECS_SERVICE_NAME" \
        --region "$AWS_REGION" \
        --query 'services[0].status' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$service_status" == "ACTIVE" ]]; then
        log_success "ECS service is active"
        
        # Check running tasks
        local running_count=$(aws ecs describe-services \
            --cluster "$ECS_CLUSTER_NAME" \
            --services "$ECS_SERVICE_NAME" \
            --region "$AWS_REGION" \
            --query 'services[0].runningCount' \
            --output text 2>/dev/null || echo "0")
        
        local desired_count=$(aws ecs describe-services \
            --cluster "$ECS_CLUSTER_NAME" \
            --services "$ECS_SERVICE_NAME" \
            --region "$AWS_REGION" \
            --query 'services[0].desiredCount' \
            --output text 2>/dev/null || echo "0")
        
        log_info "ECS service tasks: $running_count/$desired_count running"
        
        if [[ "$running_count" -eq "$desired_count" ]] && [[ "$running_count" -gt 0 ]]; then
            log_success "ECS service has correct number of running tasks"
        else
            log_warning "ECS service task count mismatch or no tasks running"
        fi
        
        return 0
    else
        log_error "ECS service is not active: $service_status"
        return 1
    fi
}

# Function to validate Lambda functions
validate_lambda_functions() {
    log_info "Validating Lambda functions..."
    
    local functions=(
        "kinesis-demo-message-processor-${ENVIRONMENT}"
        "kinesis-demo-cost-calculator-${ENVIRONMENT}"
        "kinesis-demo-stepfunctions-controller-${ENVIRONMENT}"
    )
    
    local all_healthy=true
    
    for function_name in "${functions[@]}"; do
        local function_state=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$AWS_REGION" \
            --query 'Configuration.State' \
            --output text 2>/dev/null || echo "NOT_FOUND")
        
        if [[ "$function_state" == "Active" ]]; then
            log_success "Lambda function $function_name is active"
        else
            log_error "Lambda function $function_name is not active: $function_state"
            all_healthy=false
        fi
    done
    
    if [[ "$all_healthy" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

# Function to validate Step Functions state machine
validate_step_functions() {
    log_info "Validating Step Functions state machine..."
    
    if [[ -z "$STATE_MACHINE_ARN" ]]; then
        log_error "State machine ARN not found in stack outputs"
        return 1
    fi
    
    local state_machine_status=$(aws stepfunctions describe-state-machine \
        --state-machine-arn "$STATE_MACHINE_ARN" \
        --region "$AWS_REGION" \
        --query 'status' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$state_machine_status" == "ACTIVE" ]]; then
        log_success "Step Functions state machine is active"
        return 0
    else
        log_error "Step Functions state machine is not active: $state_machine_status"
        return 1
    fi
}

# Function to validate API Gateway
validate_api_gateway() {
    log_info "Validating API Gateway..."
    
    if [[ -z "$API_ENDPOINT" ]]; then
        log_error "API endpoint not found in stack outputs"
        return 1
    fi
    
    # Test API endpoint
    local api_response=$(curl -s -o /dev/null -w "%{http_code}" "${API_ENDPOINT}demo" 2>/dev/null || echo "000")
    
    # API Gateway returns 400 for POST without body, which is expected
    if [[ "$api_response" == "400" ]] || [[ "$api_response" == "403" ]]; then
        log_success "API Gateway is responding (HTTP $api_response)"
        return 0
    elif [[ "$api_response" == "200" ]]; then
        log_success "API Gateway is responding (HTTP $api_response)"
        return 0
    else
        log_error "API Gateway is not responding correctly (HTTP $api_response)"
        return 1
    fi
}

# Function to validate CloudWatch resources
validate_cloudwatch_resources() {
    log_info "Validating CloudWatch resources..."
    
    # Check dashboard
    local dashboard_name="kinesis-ondemand-demo-${ENVIRONMENT}"
    local dashboard_exists=$(aws cloudwatch get-dashboard \
        --dashboard-name "$dashboard_name" \
        --region "$AWS_REGION" \
        --query 'DashboardName' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$dashboard_exists" == "$dashboard_name" ]]; then
        log_success "CloudWatch dashboard exists"
    else
        log_error "CloudWatch dashboard not found"
        return 1
    fi
    
    # Check log groups
    local log_groups=(
        "/ecs/kinesis-ondemand-demo"
        "/aws/lambda/kinesis-demo-message-processor-${ENVIRONMENT}"
        "/aws/lambda/kinesis-demo-cost-calculator-${ENVIRONMENT}"
        "/aws/lambda/kinesis-demo-stepfunctions-controller-${ENVIRONMENT}"
        "/aws/stepfunctions/kinesis-demo-${ENVIRONMENT}"
    )
    
    local all_log_groups_exist=true
    
    for log_group in "${log_groups[@]}"; do
        local log_group_exists=$(aws logs describe-log-groups \
            --log-group-name-prefix "$log_group" \
            --region "$AWS_REGION" \
            --query 'logGroups[?logGroupName==`'"$log_group"'`].logGroupName' \
            --output text 2>/dev/null || echo "")
        
        if [[ -n "$log_group_exists" ]]; then
            log_success "Log group exists: $log_group"
        else
            log_warning "Log group not found: $log_group"
            all_log_groups_exist=false
        fi
    done
    
    if [[ "$all_log_groups_exist" == "true" ]]; then
        return 0
    else
        log_warning "Some log groups are missing (they may be created on first use)"
        return 0  # Don't fail validation for missing log groups
    fi
}

# Function to run a quick demo test
run_demo_test() {
    log_info "Running demo test..."
    
    if [[ -z "$STATE_MACHINE_ARN" ]]; then
        log_error "State machine ARN not available for demo test"
        return 1
    fi
    
    # Start a test execution
    local execution_name="validation-test-$(date +%s)"
    local execution_arn=$(aws stepfunctions start-execution \
        --state-machine-arn "$STATE_MACHINE_ARN" \
        --name "$execution_name" \
        --input '{"test": true, "validation": true}' \
        --region "$AWS_REGION" \
        --query 'executionArn' \
        --output text 2>/dev/null || echo "")
    
    if [[ -z "$execution_arn" ]]; then
        log_error "Failed to start demo test execution"
        return 1
    fi
    
    log_info "Started test execution: $execution_name"
    log_info "Execution ARN: $execution_arn"
    
    # Wait a moment and check status
    sleep 10
    
    local execution_status=$(aws stepfunctions describe-execution \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --query 'status' \
        --output text 2>/dev/null || echo "UNKNOWN")
    
    log_info "Test execution status: $execution_status"
    
    if [[ "$execution_status" == "RUNNING" ]]; then
        log_success "Demo test execution started successfully"
        log_info "Stopping test execution to avoid full demo run..."
        
        # Stop the test execution
        aws stepfunctions stop-execution \
            --execution-arn "$execution_arn" \
            --region "$AWS_REGION" >/dev/null 2>&1 || true
        
        log_success "Demo test completed successfully"
        return 0
    elif [[ "$execution_status" == "SUCCEEDED" ]]; then
        log_success "Demo test execution completed successfully"
        return 0
    else
        log_error "Demo test execution failed: $execution_status"
        return 1
    fi
}

# Function to display validation summary
display_summary() {
    log_info "Validation Summary:"
    log_info "==================="
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Stack: $STACK_NAME"
    log_info ""
    log_info "Key Resources:"
    log_info "  Kinesis Stream: $KINESIS_STREAM_NAME"
    log_info "  ECS Cluster: $ECS_CLUSTER_NAME"
    log_info "  ECS Service: $ECS_SERVICE_NAME"
    log_info "  API Endpoint: $API_ENDPOINT"
    log_info "  Dashboard: $DASHBOARD_URL"
    log_info ""
    log_info "Next Steps:"
    log_info "1. Build and push container image to ECR"
    log_info "2. Update ECS task definition with image URI"
    log_info "3. Start demo: curl -X POST $API_ENDPOINT"demo""
    log_info "4. Monitor: $DASHBOARD_URL"
}

# Parse command line arguments
QUICK_MODE=false
FULL_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            STACK_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"
            shift 2
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --full)
            FULL_MODE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main validation process
main() {
    log_info "Starting infrastructure validation"
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Stack: $STACK_NAME"
    
    local validation_failed=false
    
    # Validate prerequisites
    if ! command -v aws >/dev/null 2>&1; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        log_error "jq is not installed"
        exit 1
    fi
    
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        log_error "AWS credentials not configured"
        exit 1
    fi
    
    # Core validations
    validate_stack || validation_failed=true
    get_stack_outputs || validation_failed=true
    validate_kinesis_stream || validation_failed=true
    validate_ecs_resources || validation_failed=true
    validate_lambda_functions || validation_failed=true
    validate_step_functions || validation_failed=true
    validate_api_gateway || validation_failed=true
    validate_cloudwatch_resources || validation_failed=true
    
    # Full mode includes demo test
    if [[ "$FULL_MODE" == "true" ]]; then
        run_demo_test || validation_failed=true
    fi
    
    # Display summary
    display_summary
    
    # Final result
    if [[ "$validation_failed" == "true" ]]; then
        log_error "Infrastructure validation failed"
        exit 1
    else
        log_success "Infrastructure validation completed successfully"
        exit 0
    fi
}

# Run main function
main "$@"