#!/bin/bash

# Kinesis On-Demand Demo - Invoke and Monitor Script
# This script can start a new demo execution and monitor its progress

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
CLUSTER_NAME="kinesis-demo-${ENVIRONMENT}"
SERVICE_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"
STATE_MACHINE_NAME="kinesis-demo-${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
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

log_phase() {
    echo -e "${PURPLE}[PHASE]${NC} $1"
}

log_metrics() {
    echo -e "${CYAN}[METRICS]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] [EXECUTION_ARN]

Kinesis On-Demand Demo - Invoke and Monitor Script

Options:
    -s, --start                 Start a new demo execution
    -m, --monitor EXECUTION_ARN Monitor existing execution
    -r, --region REGION         AWS region (default: us-east-1)
    -e, --environment ENV       Environment name (default: production)
    --interval SECONDS          Monitoring interval in seconds (default: 30)
    --detailed                  Show detailed metrics and logs
    -h, --help                  Show this help message

Examples:
    # Start a new demo and monitor it
    $0 --start

    # Monitor an existing execution
    $0 --monitor arn:aws:states:us-east-1:123456789012:execution:kinesis-demo-production:demo-123

    # Start with custom environment
    $0 --start --environment staging --region us-west-2

    # Monitor with detailed output every 15 seconds
    $0 --start --detailed --interval 15

EOF
}

# Function to get State Machine ARN
get_state_machine_arn() {
    local state_machine_arn=$(aws stepfunctions list-state-machines \
        --region "$AWS_REGION" \
        --query "stateMachines[?name=='$STATE_MACHINE_NAME'].stateMachineArn" \
        --output text 2>/dev/null)
    
    if [[ -z "$state_machine_arn" || "$state_machine_arn" == "None" ]]; then
        log_error "State machine '$STATE_MACHINE_NAME' not found in region $AWS_REGION"
        log_info "Available state machines:"
        aws stepfunctions list-state-machines \
            --region "$AWS_REGION" \
            --query 'stateMachines[].{Name:name,Status:status}' \
            --output table 2>/dev/null || echo "  No state machines found"
        exit 1
    fi
    
    echo "$state_machine_arn"
}

# Function to start a new demo execution
start_demo_execution() {
    log_info "Starting new Kinesis On-Demand Demo execution..."
    
    local state_machine_arn=$(get_state_machine_arn)
    local execution_name="demo-$(date +%s)"
    
    log_info "State Machine: $state_machine_arn"
    log_info "Execution Name: $execution_name"
    
    local execution_arn=$(aws stepfunctions start-execution \
        --state-machine-arn "$state_machine_arn" \
        --name "$execution_name" \
        --input '{}' \
        --region "$AWS_REGION" \
        --query 'executionArn' \
        --output text 2>/dev/null)
    
    if [[ $? -eq 0 && -n "$execution_arn" ]]; then
        log_success "Demo execution started successfully!"
        log_info "Execution ARN: $execution_arn"
        echo "$execution_arn"
    else
        log_error "Failed to start demo execution"
        exit 1
    fi
}

# Function to get current phase information
get_current_phase() {
    local execution_arn="$1"
    
    # Get the latest state from execution history
    local current_state=$(aws stepfunctions get-execution-history \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --max-items 10 \
        --query 'events[?stateEnteredEventDetails.name != null] | [-1].stateEnteredEventDetails.name' \
        --output text 2>/dev/null)
    
    # Map state names to phase information
    case "$current_state" in
        "InitializeDemo")
            echo "Initializing|0|Preparing demo environment"
            ;;
        "StartPhase1"|"WaitPhase1Duration")
            echo "Phase 1|1|Baseline Traffic (100 TPS, 1 task)"
            ;;
        "StartPhase2"|"WaitPhase2Duration")
            echo "Phase 2|2|Moderate Load (10K TPS, 10 tasks)"
            ;;
        "StartPhase3"|"WaitPhase3Duration")
            echo "Phase 3|3|Peak Load (50K TPS, 50 tasks)"
            ;;
        "StartPhase4"|"WaitPhase4Duration")
            echo "Phase 4|4|Cooldown (100 TPS, 1 task)"
            ;;
        "CleanupDemo")
            echo "Cleanup|5|Scaling down to 0 tasks"
            ;;
        "DemoCompleted")
            echo "Completed|6|Demo finished successfully"
            ;;
        *)
            echo "Unknown|0|$current_state"
            ;;
    esac
}

# Function to get execution progress
get_execution_progress() {
    local execution_arn="$1"
    local start_time="$2"
    
    local current_time=$(date +%s)
    local elapsed_seconds=$((current_time - start_time))
    local elapsed_minutes=$((elapsed_seconds / 60))
    
    # Total expected duration: ~85 minutes (4 phases * 20 min + overhead)
    local total_minutes=85
    local progress_percent=$((elapsed_minutes * 100 / total_minutes))
    
    if [[ $progress_percent -gt 100 ]]; then
        progress_percent=100
    fi
    
    echo "${elapsed_minutes}m|${progress_percent}%"
}

# Function to get detailed metrics
get_detailed_metrics() {
    local show_detailed="$1"
    
    if [[ "$show_detailed" != "true" ]]; then
        return
    fi
    
    # Get ECS service metrics
    local ecs_metrics=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$AWS_REGION" \
        --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:length(deployments)}' \
        --output text 2>/dev/null)
    
    # Get recent CloudWatch metrics (if available)
    local cw_metrics=""
    local end_time=$(date -u +%Y-%m-%dT%H:%M:%S)
    local start_time=$(date -u -v-5M +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null || echo "")
    
    if [[ -n "$start_time" ]]; then
        cw_metrics=$(aws cloudwatch get-metric-statistics \
            --namespace "KinesisOnDemandDemo/${ENVIRONMENT}" \
            --metric-name "MessagesPerSecond" \
            --start-time "$start_time" \
            --end-time "$end_time" \
            --period 300 \
            --statistics Average \
            --region "$AWS_REGION" \
            --query 'Datapoints[-1].Average' \
            --output text 2>/dev/null || echo "N/A")
    fi
    
    log_metrics "ECS: $ecs_metrics | TPS: ${cw_metrics:-N/A}"
}

# Function to monitor demo execution
monitor_demo_execution() {
    local execution_arn="$1"
    local interval="${2:-30}"
    local show_detailed="${3:-false}"
    
    log_info "🚀 Monitoring Kinesis On-Demand Demo"
    log_info "Execution: $execution_arn"
    log_info "Region: $AWS_REGION"
    log_info "Environment: $ENVIRONMENT"
    log_info "Monitoring interval: ${interval}s"
    log_info "Started: $(date)"
    echo ""
    
    # Get execution start time
    local start_date=$(aws stepfunctions describe-execution \
        --execution-arn "$execution_arn" \
        --region "$AWS_REGION" \
        --query 'startDate' \
        --output text 2>/dev/null)
    
    local start_timestamp=$(date -d "$start_date" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${start_date%.*}" +%s 2>/dev/null || $(date +%s))
    
    # Monitoring loop
    local last_phase=""
    local phase_start_time=""
    
    while true; do
        local current_time=$(date '+%H:%M:%S')
        
        # Get Step Functions status
        local sf_status=$(aws stepfunctions describe-execution \
            --execution-arn "$execution_arn" \
            --region "$AWS_REGION" \
            --query 'status' \
            --output text 2>/dev/null)
        
        # Get current phase information
        local phase_info=$(get_current_phase "$execution_arn")
        IFS='|' read -r phase_name phase_num phase_desc <<< "$phase_info"
        
        # Get execution progress
        local progress_info=$(get_execution_progress "$execution_arn" "$start_timestamp")
        IFS='|' read -r elapsed progress_pct <<< "$progress_info"
        
        # Check for phase transition
        if [[ "$phase_name" != "$last_phase" ]]; then
            echo ""
            log_phase "🔄 Transitioned to: $phase_name - $phase_desc"
            last_phase="$phase_name"
            phase_start_time=$(date +%s)
        fi
        
        # Calculate phase elapsed time
        local phase_elapsed=""
        if [[ -n "$phase_start_time" ]]; then
            local phase_elapsed_sec=$(($(date +%s) - phase_start_time))
            local phase_elapsed_min=$((phase_elapsed_sec / 60))
            phase_elapsed="${phase_elapsed_min}m"
        fi
        
        # Display status line
        printf "[$current_time] Status: %-10s | Phase: %-8s (%s) | Progress: %s (%s)\n" \
            "$sf_status" "$phase_name" "$phase_elapsed" "$elapsed" "$progress_pct"
        
        # Show detailed metrics if requested
        get_detailed_metrics "$show_detailed"
        
        # Check if execution is complete
        if [[ "$sf_status" == "SUCCEEDED" ]]; then
            echo ""
            log_success "🏁 Demo execution completed successfully!"
            log_info "Total duration: $elapsed"
            log_info "Final phase: $phase_name"
            break
        elif [[ "$sf_status" == "FAILED" ]]; then
            echo ""
            log_error "❌ Demo execution failed!"
            
            # Get failure details
            local failure_details=$(aws stepfunctions describe-execution \
                --execution-arn "$execution_arn" \
                --region "$AWS_REGION" \
                --query '{Cause:cause,Error:error}' \
                --output table 2>/dev/null)
            
            if [[ -n "$failure_details" ]]; then
                echo "$failure_details"
            fi
            break
        elif [[ "$sf_status" == "ABORTED" ]]; then
            echo ""
            log_warning "⚠️  Demo execution was aborted"
            break
        elif [[ "$sf_status" == "TIMED_OUT" ]]; then
            echo ""
            log_error "⏰ Demo execution timed out"
            break
        fi
        
        sleep "$interval"
    done
    
    echo ""
    log_info "📊 Monitoring URLs:"
    log_info "Step Functions: https://${AWS_REGION}.console.aws.amazon.com/states/home?region=${AWS_REGION}#/executions/details/${execution_arn}"
    log_info "CloudWatch Dashboard: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards:name=kinesis-ondemand-demo-${ENVIRONMENT}"
    log_info "ECS Service: https://${AWS_REGION}.console.aws.amazon.com/ecs/home?region=${AWS_REGION}#/clusters/${CLUSTER_NAME}/services/${SERVICE_NAME}/details"
}

# Parse command line arguments
START_DEMO=false
MONITOR_EXECUTION=""
EXECUTION_ARN=""
INTERVAL=30
SHOW_DETAILED=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--start)
            START_DEMO=true
            shift
            ;;
        -m|--monitor)
            MONITOR_EXECUTION="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            CLUSTER_NAME="kinesis-demo-${ENVIRONMENT}"
            SERVICE_NAME="kinesis-ondemand-demo-${ENVIRONMENT}"
            STATE_MACHINE_NAME="kinesis-demo-${ENVIRONMENT}"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --detailed)
            SHOW_DETAILED=true
            shift
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

# Validate AWS CLI and credentials
if ! command -v aws >/dev/null 2>&1; then
    log_error "AWS CLI is not installed"
    exit 1
fi

if ! aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
    log_error "AWS credentials not configured or invalid"
    exit 1
fi

# Main execution logic
main() {
    if [[ "$START_DEMO" == true ]]; then
        # Start new demo execution
        EXECUTION_ARN=$(start_demo_execution)
        echo ""
        monitor_demo_execution "$EXECUTION_ARN" "$INTERVAL" "$SHOW_DETAILED"
    elif [[ -n "$MONITOR_EXECUTION" ]]; then
        # Monitor specified execution
        monitor_demo_execution "$MONITOR_EXECUTION" "$INTERVAL" "$SHOW_DETAILED"
    elif [[ -n "$EXECUTION_ARN" ]]; then
        # Monitor execution ARN provided as argument
        monitor_demo_execution "$EXECUTION_ARN" "$INTERVAL" "$SHOW_DETAILED"
    else
        log_error "Please specify either --start to start a new demo or --monitor with an execution ARN"
        echo ""
        show_usage
        exit 1
    fi
}

# Run main function
main "$@"