#!/bin/bash

# Quick Start Script for Kinesis On-Demand Demo
# This is a simplified script to quickly start and monitor the demo

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
STATE_MACHINE_NAME="kinesis-demo-${ENVIRONMENT}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🚀 Kinesis On-Demand Demo - Quick Start${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

# Get State Machine ARN
echo -e "${BLUE}[INFO]${NC} Finding Step Functions state machine..."
STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines \
    --region "$AWS_REGION" \
    --query "stateMachines[?name=='$STATE_MACHINE_NAME'].stateMachineArn" \
    --output text 2>/dev/null)

if [[ -z "$STATE_MACHINE_ARN" || "$STATE_MACHINE_ARN" == "None" ]]; then
    echo -e "${YELLOW}[ERROR]${NC} State machine '$STATE_MACHINE_NAME' not found!"
    echo "Available state machines:"
    aws stepfunctions list-state-machines \
        --region "$AWS_REGION" \
        --query 'stateMachines[].{Name:name,Status:status}' \
        --output table 2>/dev/null
    exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} Found state machine: $STATE_MACHINE_ARN"

# Start execution
echo -e "${BLUE}[INFO]${NC} Starting demo execution..."
EXECUTION_NAME="demo-$(date +%s)"

EXECUTION_ARN=$(aws stepfunctions start-execution \
    --state-machine-arn "$STATE_MACHINE_ARN" \
    --name "$EXECUTION_NAME" \
    --input '{}' \
    --region "$AWS_REGION" \
    --query 'executionArn' \
    --output text)

if [[ $? -eq 0 && -n "$EXECUTION_ARN" ]]; then
    echo -e "${GREEN}[SUCCESS]${NC} Demo started successfully!"
    echo ""
    echo "📊 Demo Information:"
    echo "  Execution ARN: $EXECUTION_ARN"
    echo "  Duration: ~80 minutes (4 phases × 20 minutes each)"
    echo "  Phases:"
    echo "    Phase 1 (0-20m):  Baseline (100 TPS, 1 task)"
    echo "    Phase 2 (20-40m): Moderate (10K TPS, 10 tasks)"
    echo "    Phase 3 (40-60m): Peak (50K TPS, 50 tasks)"
    echo "    Phase 4 (60-80m): Cooldown (100 TPS, 1 task)"
    echo ""
    echo "🔍 Monitoring URLs:"
    echo "  Step Functions: https://${AWS_REGION}.console.aws.amazon.com/states/home?region=${AWS_REGION}#/executions/details/${EXECUTION_ARN}"
    echo "  CloudWatch Dashboard: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards:name=kinesis-ondemand-demo-${ENVIRONMENT}"
    echo ""
    
    # Ask if user wants to monitor
    read -p "Would you like to monitor the demo progress? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}[INFO]${NC} Starting monitoring (press Ctrl+C to stop)..."
        echo ""
        ./monitor-demo.sh --monitor "$EXECUTION_ARN" --detailed
    else
        echo -e "${BLUE}[INFO]${NC} Demo is running in the background."
        echo "Use './monitor-demo.sh --monitor $EXECUTION_ARN' to monitor progress later."
    fi
else
    echo -e "${YELLOW}[ERROR]${NC} Failed to start demo execution"
    exit 1
fi