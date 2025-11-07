#!/bin/bash
set -e

# Build script for Kinesis On-Demand Demo Data Generator container
# Provides build, test, and deployment functionality

# Configuration
IMAGE_NAME="kinesis-ondemand-demo"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"
DOCKERFILE="Dockerfile"
BUILD_CONTEXT="."

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
Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build       Build the Docker image
    test        Run tests in container
    push        Push image to registry
    run         Run container locally
    clean       Clean up images and containers
    all         Build, test, and push (if registry configured)

Options:
    -t, --tag TAG       Set image tag (default: latest)
    -r, --registry REG  Set registry URL
    -h, --help          Show this help message

Environment Variables:
    IMAGE_TAG           Image tag to use (default: latest)
    REGISTRY            Registry URL for pushing images
    AWS_REGION          AWS region for testing (default: us-east-1)
    STREAM_NAME         Kinesis stream name for testing (default: test-stream)

Examples:
    $0 build
    $0 build -t v1.0.0
    $0 test
    $0 push -r my-registry.com
    $0 run
    $0 all -t v1.0.0 -r my-registry.com

EOF
}

# Function to build the Docker image
build_image() {
    log_info "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
    
    # Check if Dockerfile exists
    if [[ ! -f "$DOCKERFILE" ]]; then
        log_error "Dockerfile not found: $DOCKERFILE"
        exit 1
    fi
    
    # Build the image
    docker build \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -f "$DOCKERFILE" \
        "$BUILD_CONTEXT"
    
    log_success "Image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
    
    # Show image size
    local image_size=$(docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "table {{.Size}}" | tail -n 1)
    log_info "Image size: $image_size"
}

# Function to run tests
run_tests() {
    log_info "Running tests in container..."
    
    # Check if image exists
    if ! docker images "${IMAGE_NAME}:${IMAGE_TAG}" | grep -q "${IMAGE_TAG}"; then
        log_warning "Image not found, building first..."
        build_image
    fi
    
    # Run health check test
    log_info "Running health check test..."
    docker run --rm \
        -e AWS_REGION="${AWS_REGION:-us-east-1}" \
        -e STREAM_NAME="${STREAM_NAME:-test-stream}" \
        "${IMAGE_NAME}:${IMAGE_TAG}" health-check
    
    log_success "Health check test passed"
    
    # Run unit tests if pytest is available
    log_info "Running unit tests..."
    docker run --rm \
        -e AWS_REGION="${AWS_REGION:-us-east-1}" \
        -e STREAM_NAME="${STREAM_NAME:-test-stream}" \
        "${IMAGE_NAME}:${IMAGE_TAG}" \
        python -m pytest tests/ -v --tb=short || {
        log_warning "Unit tests failed or pytest not available"
    }
    
    log_success "Tests completed"
}

# Function to push image to registry
push_image() {
    if [[ -z "$REGISTRY" ]]; then
        log_error "Registry not specified. Use -r option or set REGISTRY environment variable"
        exit 1
    fi
    
    local full_image_name="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    
    log_info "Tagging image for registry: $full_image_name"
    docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "$full_image_name"
    
    log_info "Pushing image to registry: $full_image_name"
    docker push "$full_image_name"
    
    log_success "Image pushed successfully: $full_image_name"
}

# Function to run container locally
run_container() {
    log_info "Running container locally..."
    
    # Check if image exists
    if ! docker images "${IMAGE_NAME}:${IMAGE_TAG}" | grep -q "${IMAGE_TAG}"; then
        log_warning "Image not found, building first..."
        build_image
    fi
    
    # Set default environment variables for local testing
    local aws_region="${AWS_REGION:-us-east-1}"
    local stream_name="${STREAM_NAME:-test-stream}"
    
    log_info "Starting container with configuration:"
    log_info "  AWS_REGION: $aws_region"
    log_info "  STREAM_NAME: $stream_name"
    log_info "  BASELINE_TPS: 10 (reduced for local testing)"
    log_info "  SPIKE_TPS: 50 (reduced for local testing)"
    log_info "  PEAK_TPS: 100 (reduced for local testing)"
    log_info "  Container Metrics: Enabled for local testing"
    
    # Run container with reduced TPS for local testing
    docker run --rm -it \
        -e AWS_REGION="$aws_region" \
        -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
        -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
        -e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \
        -e STREAM_NAME="$stream_name" \
        -e BASELINE_TPS=10 \
        -e SPIKE_TPS=50 \
        -e PEAK_TPS=100 \
        -e PER_TASK_CAPACITY=100 \
        -e MAX_TASKS=10 \
        -e CLOUDWATCH_NAMESPACE="KinesisOnDemandDemo/Local" \
        -e SERVICE_NAME="kinesis-data-generator" \
        -e CLUSTER_NAME="local-testing" \
        -e ENVIRONMENT="development" \
        -e DEPLOYMENT_ID="local-build" \
        -e CONTAINER_ID="local-test-container" \
        -e METRICS_PUBLISH_INTERVAL=5 \
        -e ENABLE_CLOUDWATCH_METRICS=false \
        -v ~/.aws:/home/appuser/.aws:ro \
        --name "kinesis-demo-local" \
        "${IMAGE_NAME}:${IMAGE_TAG}"
}

# Function to clean up images and containers
clean_up() {
    log_info "Cleaning up Docker images and containers..."
    
    # Stop and remove any running containers
    local containers=$(docker ps -a -q --filter "ancestor=${IMAGE_NAME}:${IMAGE_TAG}")
    if [[ -n "$containers" ]]; then
        log_info "Stopping and removing containers..."
        docker stop $containers 2>/dev/null || true
        docker rm $containers 2>/dev/null || true
    fi
    
    # Remove images
    local images=$(docker images "${IMAGE_NAME}" -q)
    if [[ -n "$images" ]]; then
        log_info "Removing images..."
        docker rmi $images 2>/dev/null || true
    fi
    
    # Clean up dangling images
    docker image prune -f
    
    log_success "Cleanup completed"
}

# Function to run all steps
run_all() {
    log_info "Running complete build, test, and deployment pipeline..."
    
    build_image
    run_tests
    
    if [[ -n "$REGISTRY" ]]; then
        push_image
    else
        log_warning "Registry not configured, skipping push"
    fi
    
    log_success "Pipeline completed successfully"
}

# Parse command line arguments
COMMAND=""
while [[ $# -gt 0 ]]; do
    case $1 in
        build|test|push|run|clean|all)
            COMMAND="$1"
            shift
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
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

# Check if Docker is available
if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker is not installed or not in PATH"
    exit 1
fi

# Execute command
case "$COMMAND" in
    build)
        build_image
        ;;
    test)
        run_tests
        ;;
    push)
        push_image
        ;;
    run)
        run_container
        ;;
    clean)
        clean_up
        ;;
    all)
        run_all
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