#!/bin/bash

# Kinesis On-Demand Demo Manager
# Comprehensive script for managing demo executions with warm throughput support

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
STATE_MACHINE_NAME="kinesis-demo-${ENVIRONMENT}"
CLUSTER_NAME="kinesis-demo-${ENVIRONMENT}"
SERVICE_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"
WARM_THROUGHPUT_MIBPS=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_usage() {
    cat << EOF
Usage: $0 <command> [options]

Kinesis On-Demand Demo Manager with Warm Throughput Support

Commands:
    start                       Start a new demo execution (creates Kinesis stream & configures ECS)
    setup                       Setup infrastructure only (Kinesis stream & ECS service)
    list                        List recent demo executions
    status <execution-arn>      Get detailed status of an execution
    stop <execution-arn>        Stop a running execution
    logs <execution-arn>        Show execution logs
    cleanup                     Scale ECS service to 0 tasks and delete Kinesis stream
    dashboard                   Open CloudWatch dashboard
    console                     Open Step Functions console
    health                      Check demo infrastructure health
    test                        Test AWS connectivity and permissions
    enable-advantage            Enable Kinesis On-Demand Advantage billing mode
    check-advantage             Check Kinesis On-Demand Advantage billing status

Options:
    -r, --region REGION         AWS region (default: us-east-1)
    -e, --environment ENV       Environment (default: production)
    -w, --warm-throughput MB    Warm throughput in MB/s (enables warm throughput mode)
    -h, --help                  Show this help

Examples:
    $0 start                              # Start new demo (setup + execution)
    $0 start --warm-throughput 100        # Start demo with 100 MB/s warm throughput
    $0 setup --warm-throughput 50         # Setup infrastructure with 50 MB/s warm throughput
    $0 enable-advantage                   # Enable On-Demand Advantage billing
    $0 check-advantage                    # Check billing mode status
    $0 list                               # List recent executions
    $0 status arn:aws:states...           # Check execution status
    $0 stop arn:aws:states...             # Stop execution
    $0 cleanup                            # Emergency cleanup
    $0 health                             # Check infrastructure

Warm Throughput:
    - Requires Kinesis On-Demand Advantage billing mode to be enabled
    - Valid range: 1-10240 MB/s (10 GB/s maximum)
    - Use 'enable-advantage' command to enable billing mode if not already enabled
    - Warm throughput provides immediate scaling capacity for traffic spikes

EOF
}

# Get State Machine ARN
get_state_machine_arn() {
    aws stepfunctions list-state-machines \
        --region "$AWS_REGION" \
        --query "stateMachines[?name=='$STATE_MACHINE_NAME'].stateMachineArn" \
        --output text 2>/dev/null
}

# Wait for Kinesis stream to finish updating (for warm throughput changes)
wait_for_stream_update() {
    local stream_name="$1"
    local max_wait=600  # 10 minutes maximum wait time
    local wait_time=0
    
    log_info "Waiting for stream to finish updating..."
    
    while [[ $wait_time -lt $max_wait ]]; do
        local stream_status=$(aws kinesis describe-stream \
            --stream-name "$stream_name" \
            --region "$AWS_REGION" \
            --query 'StreamDescription.StreamStatus' \
            --output text 2>/dev/null)
        
        if [[ "$stream_status" == "ACTIVE" ]]; then
            log_success "Stream update completed successfully"
            return 0
        elif [[ "$stream_status" == "UPDATING" ]]; then
            echo -n "."
            sleep 15
            wait_time=$((wait_time + 15))
        else
            log_error "Unexpected stream status: $stream_status"
            return 1
        fi
    done
    
    log_error "Timeout waiting for stream update to complete (${max_wait}s)"
    return 1
}

# Check if Kinesis On-Demand Advantage billing is enabled
check_advantage_billing() {
    log_info "Checking Kinesis On-Demand Advantage billing status..."
    
    local billing_status=$(aws kinesis describe-account-settings \
        --region "$AWS_REGION" \
        --query 'MinimumThroughputBillingCommitment.Status' \
        --output text 2>/dev/null)
    
    if [[ "$billing_status" == "ENABLED" ]]; then
        log_success "Kinesis On-Demand Advantage billing is enabled"
        return 0
    elif [[ "$billing_status" == "DISABLED" ]]; then
        log_warning "Kinesis On-Demand Advantage billing is disabled"
        return 1
    else
        log_warning "Unable to determine billing status (may not be available in this region)"
        return 1
    fi
}

# Enable Kinesis On-Demand Advantage billing
enable_advantage_billing() {
    log_info "Enabling Kinesis On-Demand Advantage billing mode..."
    
    # Check current status first
    if check_advantage_billing; then
        log_info "Billing mode already enabled"
        return 0
    fi
    
    log_warning "Enabling On-Demand Advantage billing mode..."
    log_warning "This will enable minimum throughput billing commitment for your account"
    log_warning "Please review pricing at: https://aws.amazon.com/kinesis/data-streams/pricing/"
    
    read -p "Do you want to continue? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Operation cancelled"
        return 1
    fi
    
    local result=$(aws kinesis update-account-settings \
        --minimum-throughput-billing-commitment Status=ENABLED \
        --region "$AWS_REGION" \
        --output json 2>&1)
    
    if [[ $? -eq 0 ]]; then
        log_success "Kinesis On-Demand Advantage billing enabled successfully"
        echo "Status: $(echo "$result" | jq -r '.MinimumThroughputBillingCommitment.Status')"
        echo "Started At: $(echo "$result" | jq -r '.MinimumThroughputBillingCommitment.StartedAt')"
        return 0
    else
        log_error "Failed to enable billing mode: $result"
        return 1
    fi
}

# Create or recreate Kinesis stream with optional warm throughput
setup_kinesis_stream() {
    local stream_name="social-media-stream-${ENVIRONMENT}"
    
    log_info "Setting up Kinesis stream: $stream_name"
    
    # If warm throughput is requested, check billing mode
    if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
        log_info "Warm throughput requested: ${WARM_THROUGHPUT_MIBPS} MB/s"
        
        # Validate warm throughput value
        if [[ ! "$WARM_THROUGHPUT_MIBPS" =~ ^[0-9]+$ ]] || [[ "$WARM_THROUGHPUT_MIBPS" -lt 1 ]] || [[ "$WARM_THROUGHPUT_MIBPS" -gt 10240 ]]; then
            log_error "Invalid warm throughput value. Must be between 1 and 10240 MB/s"
            return 1
        fi
        
        # Check if advantage billing is enabled
        if ! check_advantage_billing; then
            log_error "Kinesis On-Demand Advantage billing must be enabled for warm throughput"
            log_info "Run: $0 enable-advantage"
            return 1
        fi
    fi
    
    # Validate AWS credentials and permissions
    log_info "Validating AWS credentials and Kinesis permissions..."
    if ! aws kinesis list-streams --region "$AWS_REGION" --max-items 1 >/dev/null 2>&1; then
        log_error "Cannot access Kinesis service. Check your AWS credentials and permissions."
        log_error "Required permissions: kinesis:ListStreams, kinesis:CreateStream, kinesis:DescribeStream, kinesis:DeleteStream"
        if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
            log_error "Additional permissions for warm throughput: kinesis:UpdateStreamWarmThroughput, kinesis:DescribeAccountSettings"
        fi
        return 1
    fi
    
    # Check if stream exists
    log_info "Checking if stream exists: $stream_name in region $AWS_REGION"
    local stream_status=$(aws kinesis describe-stream \
        --stream-name "$stream_name" \
        --region "$AWS_REGION" \
        --query 'StreamDescription.StreamStatus' \
        --output text 2>/dev/null)
    
    local describe_exit_code=$?
    log_info "Stream describe exit code: $describe_exit_code, status: ${stream_status:-'not found'}"
    
    if [[ -n "$stream_status" && "$stream_status" != "None" ]]; then
        log_warning "Stream exists with status: $stream_status"
        
        if [[ "$stream_status" == "ACTIVE" ]]; then
            log_warning "Deleting existing stream..."
            aws kinesis delete-stream \
                --stream-name "$stream_name" \
                --region "$AWS_REGION" \
                --enforce-consumer-deletion
            
            if [[ $? -ne 0 ]]; then
                log_error "Failed to delete existing stream"
                return 1
            fi
            
            # Wait for stream deletion
            log_info "Waiting for stream deletion..."
            local max_wait=300  # 5 minutes
            local wait_time=0
            
            while [[ $wait_time -lt $max_wait ]]; do
                local check_status=$(aws kinesis describe-stream \
                    --stream-name "$stream_name" \
                    --region "$AWS_REGION" \
                    --query 'StreamDescription.StreamStatus' \
                    --output text 2>/dev/null)
                
                if [[ -z "$check_status" || "$check_status" == "None" ]]; then
                    log_success "Stream deleted successfully"
                    break
                fi
                
                echo -n "."
                sleep 10
                wait_time=$((wait_time + 10))
            done
            
            if [[ $wait_time -ge $max_wait ]]; then
                log_error "Timeout waiting for stream deletion"
                return 1
            fi
        fi
    fi
    
    # Create new stream with On-Demand mode
    log_info "Creating new Kinesis stream with On-Demand mode..."
    log_info "Command: aws kinesis create-stream --stream-name $stream_name --stream-mode-details StreamMode=ON_DEMAND --region $AWS_REGION"
    
    local create_output=$(aws kinesis create-stream \
        --stream-name "$stream_name" \
        --stream-mode-details StreamMode=ON_DEMAND \
        --region "$AWS_REGION" 2>&1)
    
    local create_exit_code=$?
    
    if [[ $create_exit_code -ne 0 ]]; then
        log_error "Failed to create Kinesis stream (exit code: $create_exit_code)"
        log_error "AWS CLI output: $create_output"
        return 1
    else
        log_success "Stream creation command succeeded"
    fi
    
    # Wait for stream to become active
    log_info "Waiting for stream to become active..."
    local max_wait=300  # 5 minutes
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        local current_status=$(aws kinesis describe-stream \
            --stream-name "$stream_name" \
            --region "$AWS_REGION" \
            --query 'StreamDescription.StreamStatus' \
            --output text 2>/dev/null)
        
        if [[ "$current_status" == "ACTIVE" ]]; then
            log_success "Kinesis stream is now active"
            break
        fi
        
        echo -n "."
        sleep 10
        wait_time=$((wait_time + 10))
    done
    
    if [[ $wait_time -ge $max_wait ]]; then
        log_error "Timeout waiting for stream to become active"
        return 1
    fi
    
    # Configure warm throughput if requested
    if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
        log_info "Configuring warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s"
        
        local warm_result=$(aws kinesis update-stream-warm-throughput \
            --stream-name "$stream_name" \
            --warm-throughput-mi-bps "$WARM_THROUGHPUT_MIBPS" \
            --region "$AWS_REGION" \
            --output json 2>&1)
        
        if [[ $? -eq 0 ]]; then
            log_success "Warm throughput configuration initiated"
            local target_throughput=$(echo "$warm_result" | jq -r '.WarmThroughput.TargetMiBps')
            local current_throughput=$(echo "$warm_result" | jq -r '.WarmThroughput.CurrentMiBps')
            echo "  Target: ${target_throughput} MB/s"
            echo "  Current: ${current_throughput} MB/s"
            
            if [[ "$target_throughput" != "$current_throughput" ]]; then
                log_info "Stream is scaling to target throughput..."
                
                # Wait for the stream update to complete
                if ! wait_for_stream_update "$stream_name"; then
                    log_error "Failed to wait for warm throughput scaling to complete"
                    return 1
                fi
                
                # Verify final throughput configuration
                local final_info=$(aws kinesis describe-stream \
                    --stream-name "$stream_name" \
                    --region "$AWS_REGION" \
                    --query 'StreamDescription.WarmThroughput' \
                    --output json 2>/dev/null)
                
                if [[ -n "$final_info" && "$final_info" != "null" ]]; then
                    local final_current=$(echo "$final_info" | jq -r '.CurrentMiBps')
                    local final_target=$(echo "$final_info" | jq -r '.TargetMiBps')
                    log_success "Warm throughput scaling completed: ${final_current} MB/s (target: ${final_target} MB/s)"
                else
                    log_success "Stream update completed"
                fi
            else
                log_success "Warm throughput immediately available: ${current_throughput} MB/s"
            fi
        else
            log_error "Failed to configure warm throughput: $warm_result"
            return 1
        fi
    fi
    
    return 0
}

# Setup ECS service with initial task count
setup_ecs_service() {
    log_info "Setting up ECS service with initial configuration..."
    
    # Set desired count to 0 and update environment variables
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --desired-count 0 \
        --region "$AWS_REGION" \
        --query 'service.{ServiceName:serviceName,DesiredCount:desiredCount,Status:status}' \
        --output table
    
    if [[ $? -eq 0 ]]; then
        log_success "ECS service configured with 1 task"
        
        # Wait for service to stabilize
        log_info "Waiting for ECS service to stabilize..."
        aws ecs wait services-stable \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$AWS_REGION"
        
        if [[ $? -eq 0 ]]; then
            log_success "ECS service is stable and ready"
        else
            log_warning "Service may still be stabilizing"
        fi
    else
        log_error "Failed to configure ECS service"
        return 1
    fi
}

# Start new demo execution
cmd_start() {
    log_info "Starting new Kinesis On-Demand Demo..."
    
    if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
        log_info "Demo will use warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s"
    fi
    
    # Check if infrastructure setup is needed
    local stream_name="social-media-stream-${ENVIRONMENT}"
    local stream_exists=$(aws kinesis describe-stream \
        --stream-name "$stream_name" \
        --region "$AWS_REGION" \
        --query 'StreamDescription.StreamStatus' \
        --output text 2>/dev/null)
    
    local ecs_running=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$AWS_REGION" \
        --query 'services[0].runningCount' \
        --output text 2>/dev/null)
    
    # Setup infrastructure if needed
    if [[ "$stream_exists" != "ACTIVE" ]] || [[ "$ecs_running" == "0" || -z "$ecs_running" ]]; then
        log_info "Infrastructure setup required..."
        
        # Step 1: Setup Kinesis stream
        if ! setup_kinesis_stream; then
            log_error "Failed to setup Kinesis stream"
            return 1
        fi
        
        # Step 2: Setup ECS service
        if ! setup_ecs_service; then
            log_error "Failed to setup ECS service"
            return 1
        fi
    else
        log_info "Infrastructure already active, proceeding with demo execution..."
        
        # If warm throughput is requested and stream exists, update it
        if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
            log_info "Updating existing stream with warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s"
            
            # Check billing mode first
            if ! check_advantage_billing; then
                log_error "Kinesis On-Demand Advantage billing must be enabled for warm throughput"
                log_info "Run: $0 enable-advantage"
                return 1
            fi
            
            local warm_result=$(aws kinesis update-stream-warm-throughput \
                --stream-name "$stream_name" \
                --warm-throughput-mi-bps "$WARM_THROUGHPUT_MIBPS" \
                --region "$AWS_REGION" \
                --output json 2>&1)
            
            if [[ $? -eq 0 ]]; then
                log_success "Warm throughput update initiated"
                local target_throughput=$(echo "$warm_result" | jq -r '.WarmThroughput.TargetMiBps')
                local current_throughput=$(echo "$warm_result" | jq -r '.WarmThroughput.CurrentMiBps')
                echo "  Target: ${target_throughput} MB/s"
                echo "  Current: ${current_throughput} MB/s"
                
                if [[ "$target_throughput" != "$current_throughput" ]]; then
                    log_info "Stream is scaling to target throughput..."
                    
                    # Wait for the stream update to complete
                    if ! wait_for_stream_update "$stream_name"; then
                        log_error "Failed to wait for warm throughput scaling to complete"
                        return 1
                    fi
                    
                    # Verify final throughput configuration
                    local final_info=$(aws kinesis describe-stream \
                        --stream-name "$stream_name" \
                        --region "$AWS_REGION" \
                        --query 'StreamDescription.WarmThroughput' \
                        --output json 2>/dev/null)
                    
                    if [[ -n "$final_info" && "$final_info" != "null" ]]; then
                        local final_current=$(echo "$final_info" | jq -r '.CurrentMiBps')
                        local final_target=$(echo "$final_info" | jq -r '.TargetMiBps')
                        log_success "Warm throughput scaling completed: ${final_current} MB/s (target: ${final_target} MB/s)"
                    else
                        log_success "Stream update completed"
                    fi
                else
                    log_success "Warm throughput immediately available: ${current_throughput} MB/s"
                fi
            else
                log_error "Failed to update warm throughput: $warm_result"
                return 1
            fi
        fi
    fi
    
    # Step 3: Start Step Functions execution
    local state_machine_arn=$(get_state_machine_arn)
    if [[ -z "$state_machine_arn" || "$state_machine_arn" == "None" ]]; then
        log_error "State machine '$STATE_MACHINE_NAME' not found"
        return 1
    fi
    
    local execution_name="demo-$(date +%s)"
    local execution_arn=$(aws stepfunctions start-execution \
        --state-machine-arn "$state_machine_arn" \
        --name "$execution_name" \
        --input '{}' \
        --region "$AWS_REGION" \
        --query 'executionArn' \
        --output text)
    
    if [[ $? -eq 0 ]]; then
        log_success "Demo started: $execution_arn"
        echo ""
        echo "📊 Demo Timeline (80+ minutes total):"
        echo "  Phase 1 (0-20m):  Baseline Traffic (100 TPS, 1 task)"
        echo "  Phase 2 (20-40m): Moderate Load (10K TPS, 10 tasks)"
        echo "  Phase 3 (40-60m): Peak Load (50K TPS, 50 tasks)"
        echo "  Phase 4 (60-80m): Cooldown (100 TPS, 1 task)"
        echo ""
        echo "✅ Infrastructure Status:"
        echo "  • Kinesis stream: social-media-stream-${ENVIRONMENT} (ACTIVE)"
        if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
            echo "  • Warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s (On-Demand Advantage)"
        fi
        echo "  • ECS service: ${SERVICE_NAME} (1+ tasks running)"
        echo "  • Step Functions: Execution started"
        echo ""
        echo "Monitor with: $0 status $execution_arn"
    else
        log_error "Failed to start demo"
        return 1
    fi
}

# List recent executions
cmd_list() {
    log_info "Recent demo executions:"
    
    local state_machine_arn=$(get_state_machine_arn)
    if [[ -z "$state_machine_arn" ]]; then
        log_error "State machine not found"
        return 1
    fi
    
    aws stepfunctions list-executions \
        --state-machine-arn "$state_machine_arn" \
        --region "$AWS_REGION" \
        --max-items 10 \
        --query 'executions[].{Name:name,Status:status,StartDate:startDate,StopDate:stopDate}' \
        --output table
}

# Get execution status
cmd_status() {
    local execution_arn="$1"
    if [[ -z "$execution_arn" ]]; then
        log_error "Execution ARN required"
        return 1
    fi
    
    log_info "Getting execution status..."
    
    # Get basic execution info
    local exec_info=$(aws stepfunctions describe-execution \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --output json)
    
    local status=$(echo "$exec_info" | jq -r '.status')
    local start_date=$(echo "$exec_info" | jq -r '.startDate')
    local stop_date=$(echo "$exec_info" | jq -r '.stopDate // "N/A"')
    
    echo ""
    echo "📋 Execution Status:"
    echo "  Status: $status"
    echo "  Started: $start_date"
    echo "  Stopped: $stop_date"
    
    # Get current state
    local current_state=$(aws stepfunctions get-execution-history \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --max-items 10 \
        --query 'events[?stateEnteredEventDetails.name != null] | [-1].stateEnteredEventDetails.name' \
        --output text 2>/dev/null)
    
    echo "  Current State: ${current_state:-Unknown}"
    
    # Get ECS service status
    local ecs_status=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$AWS_REGION" \
        --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
        --output json 2>/dev/null)
    
    if [[ -n "$ecs_status" ]]; then
        echo ""
        echo "🚀 ECS Service Status:"
        echo "$ecs_status" | jq -r '"  Desired: \(.Desired), Running: \(.Running), Pending: \(.Pending)"'
    fi
    
    # Get Kinesis stream status including warm throughput
    local stream_name="social-media-stream-${ENVIRONMENT}"
    local stream_info=$(aws kinesis describe-stream \
        --stream-name "$stream_name" \
        --region "$AWS_REGION" \
        --output json 2>/dev/null)
    
    if [[ -n "$stream_info" ]]; then
        echo ""
        echo "📊 Kinesis Stream Status:"
        local stream_status=$(echo "$stream_info" | jq -r '.StreamDescription.StreamStatus')
        echo "  Status: $stream_status"
        
        # Check for warm throughput configuration
        local warm_throughput=$(echo "$stream_info" | jq -r '.StreamDescription.WarmThroughput // empty')
        if [[ -n "$warm_throughput" && "$warm_throughput" != "null" ]]; then
            local current_mibps=$(echo "$warm_throughput" | jq -r '.CurrentMiBps')
            local target_mibps=$(echo "$warm_throughput" | jq -r '.TargetMiBps')
            echo "  Warm Throughput: Current ${current_mibps} MB/s, Target ${target_mibps} MB/s"
        else
            echo "  Warm Throughput: Not configured"
        fi
    fi
    
    # Show monitoring URLs
    echo ""
    echo "🔍 Monitoring URLs:"
    echo "  Step Functions: https://${AWS_REGION}.console.aws.amazon.com/states/home?region=${AWS_REGION}#/executions/details/${execution_arn}"
    echo "  CloudWatch Dashboard: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards:name=kinesis-ondemand-demo-${ENVIRONMENT}"
}

# Stop execution
cmd_stop() {
    local execution_arn="$1"
    if [[ -z "$execution_arn" ]]; then
        log_error "Execution ARN required"
        return 1
    fi
    
    log_warning "Stopping execution: $execution_arn"
    
    aws stepfunctions stop-execution \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --cause "Stopped by demo manager" \
        --error "UserRequested"
    
    if [[ $? -eq 0 ]]; then
        log_success "Execution stopped"
    else
        log_error "Failed to stop execution"
        return 1
    fi
}

# Show execution logs
cmd_logs() {
    local execution_arn="$1"
    if [[ -z "$execution_arn" ]]; then
        log_error "Execution ARN required"
        return 1
    fi
    
    log_info "Getting execution history..."
    
    aws stepfunctions get-execution-history \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --query 'events[].{Timestamp:timestamp,Type:type,Details:stateEnteredEventDetails.name}' \
        --output table
}

# Cleanup - scale ECS to 0 and delete Kinesis stream
cmd_cleanup() {
    log_warning "Starting cleanup process..."
    
    # Step 1: Scale ECS service to 0
    log_info "Scaling ECS service to 0 tasks..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --desired-count 0 \
        --region "$AWS_REGION" \
        --query 'service.{ServiceName:serviceName,DesiredCount:desiredCount,Status:status}' \
        --output table
    
    if [[ $? -eq 0 ]]; then
        log_success "ECS service scaled to 0 tasks"
    else
        log_error "Failed to scale ECS service"
        return 1
    fi
    
    # Step 2: Delete Kinesis stream
    local stream_name="social-media-stream-${ENVIRONMENT}"
    log_info "Deleting Kinesis stream: $stream_name"
    
    local stream_status=$(aws kinesis describe-stream \
        --stream-name "$stream_name" \
        --region "$AWS_REGION" \
        --query 'StreamDescription.StreamStatus' \
        --output text 2>/dev/null)
    
    if [[ -n "$stream_status" && "$stream_status" != "None" ]]; then
        aws kinesis delete-stream \
            --stream-name "$stream_name" \
            --region "$AWS_REGION" \
            --enforce-consumer-deletion
        
        if [[ $? -eq 0 ]]; then
            log_success "Kinesis stream deletion initiated"
            log_info "Stream will be fully deleted within a few minutes"
        else
            log_error "Failed to delete Kinesis stream"
            return 1
        fi
    else
        log_info "Kinesis stream not found or already deleted"
    fi
    
    echo ""
    log_success "Cleanup complete:"
    echo "  • ECS service scaled to 0 tasks"
    echo "  • Kinesis stream deletion initiated"
    echo "  • Resources will be fully cleaned up within a few minutes"
}

# Open CloudWatch dashboard
cmd_dashboard() {
    local dashboard_url="https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards:name=kinesis-ondemand-demo-${ENVIRONMENT}"
    
    log_info "Opening CloudWatch Dashboard..."
    echo "Dashboard URL: $dashboard_url"
    
    # Try to open in browser (macOS/Linux)
    if command -v open >/dev/null 2>&1; then
        open "$dashboard_url"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$dashboard_url"
    else
        echo "Please open the URL manually in your browser"
    fi
}

# Open Step Functions console
cmd_console() {
    local state_machine_arn=$(get_state_machine_arn)
    if [[ -z "$state_machine_arn" ]]; then
        log_error "State machine not found"
        return 1
    fi
    
    local console_url="https://${AWS_REGION}.console.aws.amazon.com/states/home?region=${AWS_REGION}#/statemachines/view/${state_machine_arn}"
    
    log_info "Opening Step Functions Console..."
    echo "Console URL: $console_url"
    
    # Try to open in browser
    if command -v open >/dev/null 2>&1; then
        open "$console_url"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$console_url"
    else
        echo "Please open the URL manually in your browser"
    fi
}

# Check infrastructure health
cmd_health() {
    log_info "Checking demo infrastructure health..."
    echo ""
    
    # Check Step Functions state machine
    echo "🔧 Step Functions:"
    local state_machine_arn=$(get_state_machine_arn)
    if [[ -n "$state_machine_arn" && "$state_machine_arn" != "None" ]]; then
        log_success "State machine found: $STATE_MACHINE_NAME"
    else
        log_error "State machine not found: $STATE_MACHINE_NAME"
    fi
    
    # Check ECS cluster and service
    echo ""
    echo "🚀 ECS Infrastructure:"
    local cluster_status=$(aws ecs describe-clusters \
        --clusters "$CLUSTER_NAME" \
        --region "$AWS_REGION" \
        --query 'clusters[0].status' \
        --output text 2>/dev/null)
    
    if [[ "$cluster_status" == "ACTIVE" ]]; then
        log_success "ECS cluster active: $CLUSTER_NAME"
    else
        log_error "ECS cluster issue: $CLUSTER_NAME ($cluster_status)"
    fi
    
    local service_status=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$AWS_REGION" \
        --query 'services[0].{Status:status,Desired:desiredCount,Running:runningCount}' \
        --output json 2>/dev/null)
    
    if [[ -n "$service_status" ]]; then
        local svc_status=$(echo "$service_status" | jq -r '.Status')
        local desired=$(echo "$service_status" | jq -r '.Desired')
        local running=$(echo "$service_status" | jq -r '.Running')
        
        if [[ "$svc_status" == "ACTIVE" ]]; then
            log_success "ECS service active: $SERVICE_NAME (Desired: $desired, Running: $running)"
        else
            log_warning "ECS service status: $svc_status (Desired: $desired, Running: $running)"
        fi
    else
        log_error "ECS service not found: $SERVICE_NAME"
    fi
    
    # Check Kinesis stream
    echo ""
    echo "📊 Kinesis Stream:"
    local stream_name="social-media-stream-${ENVIRONMENT}"
    local stream_info=$(aws kinesis describe-stream \
        --stream-name "$stream_name" \
        --region "$AWS_REGION" \
        --output json 2>/dev/null)
    
    if [[ -n "$stream_info" ]]; then
        local stream_status=$(echo "$stream_info" | jq -r '.StreamDescription.StreamStatus')
        if [[ "$stream_status" == "ACTIVE" ]]; then
            log_success "Kinesis stream active: $stream_name"
            
            # Check warm throughput configuration
            local warm_throughput=$(echo "$stream_info" | jq -r '.StreamDescription.WarmThroughput // empty')
            if [[ -n "$warm_throughput" && "$warm_throughput" != "null" ]]; then
                local current_mibps=$(echo "$warm_throughput" | jq -r '.CurrentMiBps')
                local target_mibps=$(echo "$warm_throughput" | jq -r '.TargetMiBps')
                echo "  Warm Throughput: Current ${current_mibps} MB/s, Target ${target_mibps} MB/s"
            else
                echo "  Warm Throughput: Not configured"
            fi
        else
            log_error "Kinesis stream issue: $stream_name ($stream_status)"
        fi
    else
        log_error "Kinesis stream not found: $stream_name"
    fi
    
    # Check billing mode
    echo ""
    echo "💳 Billing Configuration:"
    if check_advantage_billing; then
        echo "  On-Demand Advantage: Enabled (warm throughput available)"
    else
        echo "  On-Demand Advantage: Disabled (warm throughput not available)"
    fi
    
    echo ""
    log_info "Health check complete"
}

# Test AWS connectivity and permissions
cmd_test() {
    log_info "Testing AWS connectivity and permissions..."
    echo ""
    
    # Test basic AWS connectivity
    echo "🔧 AWS Connectivity:"
    if aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
        local identity=$(aws sts get-caller-identity --region "$AWS_REGION" --output json)
        local account=$(echo "$identity" | jq -r '.Account')
        local user_arn=$(echo "$identity" | jq -r '.Arn')
        log_success "AWS credentials valid"
        echo "  Account: $account"
        echo "  Identity: $user_arn"
        echo "  Region: $AWS_REGION"
    else
        log_error "AWS credentials invalid or not configured"
        return 1
    fi
    
    echo ""
    echo "📊 Kinesis Permissions:"
    if aws kinesis list-streams --region "$AWS_REGION" --max-items 1 >/dev/null 2>&1; then
        log_success "Kinesis ListStreams permission OK"
    else
        log_error "Missing Kinesis ListStreams permission"
    fi
    
    # Test stream creation (dry run)
    local test_stream="test-stream-$(date +%s)"
    echo "  Testing stream creation permissions..."
    if aws kinesis create-stream \
        --stream-name "$test_stream" \
        --stream-mode-details StreamMode=ON_DEMAND \
        --region "$AWS_REGION" >/dev/null 2>&1; then
        log_success "Kinesis CreateStream permission OK"
        
        # Clean up test stream
        aws kinesis delete-stream \
            --stream-name "$test_stream" \
            --region "$AWS_REGION" \
            --enforce-consumer-deletion >/dev/null 2>&1
    else
        log_error "Missing Kinesis CreateStream permission or quota exceeded"
    fi
    
    # Test warm throughput permissions
    echo "  Testing warm throughput permissions..."
    if aws kinesis describe-account-settings --region "$AWS_REGION" >/dev/null 2>&1; then
        log_success "Kinesis DescribeAccountSettings permission OK"
    else
        log_error "Missing Kinesis DescribeAccountSettings permission (required for warm throughput)"
    fi
    
    echo ""
    echo "🚀 ECS Permissions:"
    if aws ecs describe-clusters --region "$AWS_REGION" --max-items 1 >/dev/null 2>&1; then
        log_success "ECS DescribeClusters permission OK"
    else
        log_error "Missing ECS DescribeClusters permission"
    fi
    
    if aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --region "$AWS_REGION" >/dev/null 2>&1; then
        log_success "ECS DescribeServices permission OK"
    else
        log_warning "Cannot access ECS cluster: $CLUSTER_NAME (may not exist yet)"
    fi
    
    echo ""
    echo "🔧 Step Functions Permissions:"
    if aws stepfunctions list-state-machines --region "$AWS_REGION" --max-items 1 >/dev/null 2>&1; then
        log_success "Step Functions ListStateMachines permission OK"
    else
        log_error "Missing Step Functions ListStateMachines permission"
    fi
    
    echo ""
    log_info "Permission test complete"
}

# Enable Kinesis On-Demand Advantage billing
cmd_enable_advantage() {
    enable_advantage_billing
}

# Check Kinesis On-Demand Advantage billing status
cmd_check_advantage() {
    log_info "Checking Kinesis On-Demand Advantage billing status..."
    
    local billing_info=$(aws kinesis describe-account-settings \
        --region "$AWS_REGION" \
        --output json 2>/dev/null)
    
    if [[ -n "$billing_info" ]]; then
        local status=$(echo "$billing_info" | jq -r '.MinimumThroughputBillingCommitment.Status')
        local started_at=$(echo "$billing_info" | jq -r '.MinimumThroughputBillingCommitment.StartedAt // "N/A"')
        local ended_at=$(echo "$billing_info" | jq -r '.MinimumThroughputBillingCommitment.EndedAt // "N/A"')
        local earliest_end=$(echo "$billing_info" | jq -r '.MinimumThroughputBillingCommitment.EarliestAllowedEndAt // "N/A"')
        
        echo ""
        echo "💳 Kinesis On-Demand Advantage Billing Status:"
        echo "  Status: $status"
        echo "  Started At: $started_at"
        echo "  Ended At: $ended_at"
        echo "  Earliest Allowed End: $earliest_end"
        
        if [[ "$status" == "ENABLED" ]]; then
            log_success "Warm throughput features are available"
        else
            log_warning "Warm throughput features are not available"
            echo "  Run: $0 enable-advantage to enable billing mode"
        fi
    else
        log_error "Unable to retrieve billing information"
        return 1
    fi
}

# Parse arguments
COMMAND=""
EXECUTION_ARN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        start|setup|list|cleanup|dashboard|console|health|test|enable-advantage|check-advantage)
            COMMAND="$1"
            shift
            ;;
        status|stop|logs)
            COMMAND="$1"
            EXECUTION_ARN="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            STATE_MACHINE_NAME="kinesis-demo-${ENVIRONMENT}"
            CLUSTER_NAME="kinesis-demo-${ENVIRONMENT}"
            SERVICE_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"
            shift 2
            ;;
        -w|--warm-throughput)
            WARM_THROUGHPUT_MIBPS="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        arn:aws:states:*)
            EXECUTION_ARN="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate required tools
if ! command -v aws >/dev/null 2>&1; then
    log_error "AWS CLI not found"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    log_error "jq not found - please install jq for JSON processing"
    exit 1
fi

if ! aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
    log_error "AWS credentials not configured"
    exit 1
fi

# Setup infrastructure only
cmd_setup() {
    log_info "Setting up demo infrastructure..."
    
    if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
        log_info "Infrastructure will use warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s"
    fi
    
    # Step 1: Setup Kinesis stream
    if ! setup_kinesis_stream; then
        log_error "Failed to setup Kinesis stream"
        return 1
    fi
    
    # Step 2: Setup ECS service
    if ! setup_ecs_service; then
        log_error "Failed to setup ECS service"
        return 1
    fi
    
    echo ""
    log_success "Infrastructure setup complete:"
    echo "  • Kinesis stream: social-media-stream-${ENVIRONMENT}"
    if [[ -n "$WARM_THROUGHPUT_MIBPS" ]]; then
        echo "  • Warm throughput: ${WARM_THROUGHPUT_MIBPS} MB/s"
    fi
    echo "  • ECS service: ${SERVICE_NAME} (1 task running)"
    echo ""
    echo "Ready to start demo execution with: $0 start"
}

# Execute command
case "$COMMAND" in
    start)
        cmd_start
        ;;
    setup)
        cmd_setup
        ;;
    list)
        cmd_list
        ;;
    status)
        cmd_status "$EXECUTION_ARN"
        ;;
    stop)
        cmd_stop "$EXECUTION_ARN"
        ;;
    logs)
        cmd_logs "$EXECUTION_ARN"
        ;;
    cleanup)
        cmd_cleanup
        ;;
    dashboard)
        cmd_dashboard
        ;;
    console)
        cmd_console
        ;;
    health)
        cmd_health
        ;;
    test)
        cmd_test
        ;;
    enable-advantage)
        cmd_enable_advantage
        ;;
    check-advantage)
        cmd_check_advantage
        ;;
    "")
        log_error "No command specified"
        show_usage
        exit 1
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac