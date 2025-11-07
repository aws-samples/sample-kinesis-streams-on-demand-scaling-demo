#!/bin/bash
set -e

# CDK Deployment Script for Kinesis On-Demand Demo
# This script deploys the complete infrastructure stack using AWS CDK

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '')}"

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

Deploy Kinesis On-Demand Demo Infrastructure using AWS CDK

Options:
    -r, --region REGION         AWS region (default: us-east-1)
    -e, --environment ENV       Environment name (default: production)
    -a, --account ACCOUNT       AWS account ID (auto-detected if not provided)
    --bootstrap                 Bootstrap CDK in the target account/region
    --diff                      Show differences before deployment
    --destroy                   Destroy the stack instead of deploying
    --no-approval               Skip approval prompts during deployment
    --build-only                Only build TypeScript, don't deploy
    --test                      Run unit tests before deployment
    -h, --help                  Show this help message

Environment Variables:
    AWS_REGION                  AWS region
    ENVIRONMENT                 Environment name
    AWS_ACCOUNT_ID              AWS account ID

Examples:
    # Deploy to production
    $0 --environment production --region us-east-1

    # Deploy to staging with diff preview
    $0 --environment staging --diff

    # Bootstrap CDK and deploy
    $0 --bootstrap --environment production

    # Run tests and deploy
    $0 --test --environment production

    # Destroy infrastructure
    $0 --destroy --environment staging

EOF
}

# Function to validate prerequisites
validate_prerequisites() {
    log_info "Validating prerequisites..."
    
    # Check Node.js
    if ! command -v node >/dev/null 2>&1; then
        log_error "Node.js is not installed"
        exit 1
    fi
    
    # Check npm
    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm is not installed"
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws >/dev/null 2>&1; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        log_error "AWS credentials not configured"
        exit 1
    fi
    
    # Get account ID if not provided
    if [[ -z "$AWS_ACCOUNT_ID" ]]; then
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        log_info "Detected AWS Account ID: $AWS_ACCOUNT_ID"
    fi
    
    log_success "Prerequisites validated"
}

# Function to install dependencies
install_dependencies() {
    log_info "Installing dependencies..."
    
    cd "$PROJECT_ROOT"
    
    if [[ ! -d "node_modules" ]] || [[ "package.json" -nt "node_modules" ]]; then
        npm install
        log_success "Dependencies installed"
    else
        log_info "Dependencies already up to date"
    fi
}

# Function to build TypeScript
build_typescript() {
    log_info "Building TypeScript..."
    
    cd "$PROJECT_ROOT"
    npm run build
    
    log_success "TypeScript build completed"
}

# Function to run tests
run_tests() {
    log_info "Running unit tests..."
    
    cd "$PROJECT_ROOT"
    npm test
    
    log_success "All tests passed"
}

# Function to bootstrap CDK
bootstrap_cdk() {
    log_info "Bootstrapping CDK in account $AWS_ACCOUNT_ID, region $AWS_REGION..."
    
    cd "$PROJECT_ROOT"
    npx cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION
    
    log_success "CDK bootstrap completed"
}

# Function to show diff
show_diff() {
    log_info "Showing deployment differences..."
    
    cd "$PROJECT_ROOT"
    npx cdk diff \
        --context environment="$ENVIRONMENT" \
        --context region="$AWS_REGION" \
        --context account="$AWS_ACCOUNT_ID"
}

# Function to deploy stack
deploy_stack() {
    local approval_flag=""
    if [[ "$NO_APPROVAL" == "true" ]]; then
        approval_flag="--require-approval never"
    fi
    
    log_info "Deploying Kinesis On-Demand Demo infrastructure..."
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Account: $AWS_ACCOUNT_ID"
    
    cd "$PROJECT_ROOT"
    npx cdk deploy \
        --context environment="$ENVIRONMENT" \
        --context region="$AWS_REGION" \
        --context account="$AWS_ACCOUNT_ID" \
        $approval_flag
    
    log_success "Deployment completed successfully!"
    
    # Get stack outputs
    log_info "Getting stack outputs..."
    local stack_name="kinesis-ondemand-demo-${ENVIRONMENT}"
    
    local outputs=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs' \
        --output table 2>/dev/null || echo "Could not retrieve outputs")
    
    echo "$outputs"
}

# Function to destroy stack
destroy_stack() {
    log_warning "This will destroy all infrastructure for environment: $ENVIRONMENT"
    
    if [[ "$NO_APPROVAL" != "true" ]]; then
        read -p "Are you sure you want to continue? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    fi
    
    log_info "Destroying Kinesis On-Demand Demo infrastructure..."
    
    cd "$PROJECT_ROOT"
    npx cdk destroy \
        --context environment="$ENVIRONMENT" \
        --context region="$AWS_REGION" \
        --context account="$AWS_ACCOUNT_ID" \
        --force
    
    log_success "Infrastructure destroyed successfully"
}

# Function to validate stack after deployment
validate_deployment() {
    log_info "Validating deployment..."
    
    local stack_name="kinesis-ondemand-demo-${ENVIRONMENT}"
    
    # Check if stack exists and is in good state
    local stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "STACK_NOT_FOUND")
    
    if [[ "$stack_status" == "CREATE_COMPLETE" ]] || [[ "$stack_status" == "UPDATE_COMPLETE" ]]; then
        log_success "Stack is in healthy state: $stack_status"
        
        # Get key resource information
        local kinesis_stream=$(aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`KinesisStreamName`].OutputValue' \
            --output text 2>/dev/null || echo "Not found")
        
        local api_endpoint=$(aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
            --output text 2>/dev/null || echo "Not found")
        
        log_info "Key Resources:"
        log_info "  Kinesis Stream: $kinesis_stream"
        log_info "  API Endpoint: $api_endpoint"
        
        # Test API endpoint if available
        if [[ "$api_endpoint" != "Not found" ]] && [[ "$api_endpoint" != "" ]]; then
            log_info "Testing API endpoint..."
            local api_test=$(curl -s -o /dev/null -w "%{http_code}" "${api_endpoint}demo" || echo "000")
            if [[ "$api_test" == "200" ]] || [[ "$api_test" == "400" ]]; then
                log_success "API endpoint is responding"
            else
                log_warning "API endpoint test returned HTTP $api_test"
            fi
        fi
        
    else
        log_error "Stack is in unexpected state: $stack_status"
        return 1
    fi
}

# Parse command line arguments
BOOTSTRAP=false
SHOW_DIFF=false
DESTROY=false
NO_APPROVAL=false
BUILD_ONLY=false
RUN_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -a|--account)
            AWS_ACCOUNT_ID="$2"
            shift 2
            ;;
        --bootstrap)
            BOOTSTRAP=true
            shift
            ;;
        --diff)
            SHOW_DIFF=true
            shift
            ;;
        --destroy)
            DESTROY=true
            shift
            ;;
        --no-approval)
            NO_APPROVAL=true
            shift
            ;;
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --test)
            RUN_TESTS=true
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

# Main deployment process
main() {
    log_info "Starting CDK deployment process"
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Account: $AWS_ACCOUNT_ID"
    
    # Validate prerequisites
    validate_prerequisites
    
    # Install dependencies
    install_dependencies
    
    # Run tests if requested
    if [[ "$RUN_TESTS" == "true" ]]; then
        run_tests
    fi
    
    # Build TypeScript
    build_typescript
    
    # Exit if build-only mode
    if [[ "$BUILD_ONLY" == "true" ]]; then
        log_success "Build completed successfully"
        return 0
    fi
    
    # Bootstrap CDK if requested
    if [[ "$BOOTSTRAP" == "true" ]]; then
        bootstrap_cdk
    fi
    
    # Show diff if requested
    if [[ "$SHOW_DIFF" == "true" ]]; then
        show_diff
    fi
    
    # Deploy or destroy
    if [[ "$DESTROY" == "true" ]]; then
        destroy_stack
    else
        deploy_stack
        validate_deployment
        
        log_success "Kinesis On-Demand Demo deployment completed successfully!"
        log_info ""
        log_info "Next Steps:"
        log_info "1. Build and push your container image to ECR"
        log_info "2. Update the ECS task definition with your image URI"
        log_info "3. Start a demo via the API endpoint or Step Functions console"
        log_info ""
        log_info "Useful Commands:"
        log_info "  Start demo: curl -X POST \${API_ENDPOINT}demo"
        log_info "  View dashboard: Check CloudWatch Dashboard URL in outputs"
        log_info "  Monitor Step Functions: Check Step Functions Console URL in outputs"
    fi
}

# Run main function
main "$@"